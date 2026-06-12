"""The auto-trader orchestrator: round-robins the watchlist, runs the agent
pipeline on each symbol, and executes approved trades on the broker.
Publishes every step to an event bus that the UI streams over WebSocket.
"""
from __future__ import annotations

import asyncio
import time

from .agents import (
    Analyst, Consensus, Researcher, RiskManager, build_brains, BUY, SELL,
)
from .broker import PaperBroker
from .config import Settings


class EventBus:
    """Fan-out queue: each WebSocket client gets its own asyncio.Queue."""

    def __init__(self, history: int = 200):
        self._subs: set[asyncio.Queue] = set()
        self.history: list[dict] = []
        self._max_history = history
        self.loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self) -> asyncio.Queue:
        self.loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: dict) -> None:
        """Safe to call from any thread (bot steps run in an executor)."""
        event.setdefault("ts", time.time())
        if event.get("type") == "log":
            self.history.append(event)
            self.history = self.history[-self._max_history:]
        try:
            on_loop = asyncio.get_running_loop() is self.loop
        except RuntimeError:
            on_loop = False
        if on_loop or self.loop is None:
            self._fanout(event)
        else:
            self.loop.call_soon_threadsafe(self._fanout, event)

    def _fanout(self, event: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow client: drop rather than block the bot


class TradingBot:
    def __init__(self, cfg: Settings, provider, broker: PaperBroker, bus: EventBus):
        self.cfg = cfg
        self.provider = provider
        self.broker = broker
        self.bus = bus
        self.researcher = Researcher()
        self.analyst = Analyst()
        self.brains = build_brains(cfg)
        self.consensus = Consensus(cfg.required_agreement)
        self.risk = RiskManager(cfg)
        self.running = False
        self.started_at: float | None = None
        self.day_start_equity = broker.cash
        self.last_verdicts: dict[str, dict] = {}
        self._task: asyncio.Task | None = None
        self._idx = 0

    # ------------------------------------------------------------------ API
    def status(self) -> dict:
        return {
            "running": self.running,
            "started_at": self.started_at,
            "brains": [b.name for b in self.brains],
            "required_agreement": self.cfg.required_agreement,
            "mode": "paper" if not self.cfg.live_armed else "LIVE",
            "kill_switch": self.risk.kill_switch,
            "kill_reason": self.risk.kill_reason,
            "trades": len(self.broker.trades),
            "symbols_held": sorted(self.broker.positions.keys()),
        }

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.started_at = time.time()
        self.day_start_equity = self.broker.equity(self._prices())
        loop = asyncio.get_running_loop()
        self.bus.loop = loop
        self._task = loop.create_task(self._loop())
        names = " + ".join(b.name for b in self.brains)
        self.log(f"BOT STARTED — {len(self.brains)} brains ({names}), "
                 f"{self.cfg.required_agreement} must agree. Mode: "
                 f"{'LIVE' if self.cfg.live_armed else 'PAPER (fake money, safe to watch)'}")

    def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self.log("BOT STOPPED by user.")

    def log(self, msg: str, kind: str = "info") -> None:
        self.bus.publish({"type": "log", "kind": kind, "msg": msg})

    # ----------------------------------------------------------------- loop
    def _prices(self) -> dict[str, float]:
        return {s: self.provider.last_price(s) for s in
                set(self.cfg.watchlist) | set(self.broker.positions.keys())}

    async def _loop(self) -> None:
        self.log(f"Two AI brains reading {len(self.cfg.watchlist)} stocks + news…")
        while self.running:
            try:
                symbol = self.cfg.watchlist[self._idx % len(self.cfg.watchlist)]
                self._idx += 1
                await asyncio.get_running_loop().run_in_executor(None, self._step, symbol)
                self.bus.publish({"type": "portfolio", "data": self.broker.snapshot(self._prices())})
            except Exception as exc:
                self.log(f"step error on {symbol}: {exc!r}", kind="error")
            await asyncio.sleep(self.cfg.tick_seconds)

    def _step(self, symbol: str) -> None:
        candles = self.provider.history(symbol)
        if len(candles) < 60:
            return
        price = self.provider.last_price(symbol)
        research = self.researcher.run(symbol)
        analysis = self.analyst.run(symbol, candles, price)
        pos = self.broker.position(symbol)
        votes = [b.decide(analysis, research, pos.qty) for b in self.brains]
        verdict = self.consensus.deliberate(votes)
        self.last_verdicts[symbol] = verdict.as_dict()
        self.bus.publish({"type": "decision", "symbol": symbol, "verdict": verdict.as_dict()})

        if not verdict.agreed:
            if any(v.action in (BUY, SELL) for v in votes):
                self.log(f"{symbol}: brains disagree ({', '.join(v.brain + ' ' + v.action for v in votes)}) — holding steady.")
            return

        prices = self._prices()
        equity = self.broker.equity(prices)
        if self.risk.check_kill_switch(equity, self.day_start_equity):
            self.log(f"KILL-SWITCH: {self.risk.kill_reason}", kind="error")
            return
        pos_value = pos.qty * price
        qty, why = self.risk.approve(symbol, verdict, price, equity, pos_value, self.broker.cash)
        if qty == 0:
            self.log(f"{symbol}: brains agreed {verdict.action} but risk manager said no — {why}.")
            return

        reason = f"{verdict.action} consensus ({verdict.confidence:.2f}): " + " | ".join(
            v.reason for v in verdict.votes if v.action == verdict.action)
        if verdict.action == BUY:
            trade = self.broker.buy(symbol, qty, price, reason)
            self.log(f"🟢 BOUGHT {trade.qty:g} {symbol} @ {price:.2f} — {why}", kind="trade")
        else:
            trade = self.broker.sell(symbol, qty, price, reason)
            self.log(f"🔴 SOLD {trade.qty:g} {symbol} @ {price:.2f} (P/L {trade.pnl:+.2f}) — {why}", kind="trade")
