"""The multi-agent pipeline.

Researcher  -> gathers news & sentiment for a symbol
Analyst     -> turns raw candles into a structured technical report
Brains      -> independent decision makers (rule-based or real LLMs)
Consensus   -> the "two brains must agree" debate engine (N-of-M)
RiskManager -> position sizing, kill-switch, cooldowns (the upgrade the
               original app didn't have)
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
from dataclasses import dataclass, field, asdict

from .config import COMPANY_NAMES, Settings
from .indicators import (
    annualized_volatility, atr, macd, rsi, sma, support_resistance,
)
from .market import Candle, mock_news

HOLD, BUY, SELL = "HOLD", "BUY", "SELL"


# ---------------------------------------------------------------------------
# Researcher
# ---------------------------------------------------------------------------
@dataclass
class ResearchReport:
    symbol: str
    headlines: list[dict]
    sentiment: float  # -1 .. 1

    def as_dict(self) -> dict:
        return asdict(self)


class Researcher:
    """News & sentiment agent. Offline it uses the deterministic mock feed."""

    def run(self, symbol: str) -> ResearchReport:
        items = mock_news(symbol)
        sent = sum(i["sentiment"] for i in items) / max(len(items), 1)
        return ResearchReport(symbol=symbol, headlines=items, sentiment=round(sent, 3))


# ---------------------------------------------------------------------------
# Analyst
# ---------------------------------------------------------------------------
@dataclass
class AnalystReport:
    symbol: str
    price: float
    change_pct: float
    sma20: float | None
    sma50: float | None
    rsi14: float | None
    macd_hist: float | None
    atr14: float | None
    ann_vol: float
    floor: float
    ceiling: float
    high_52w: float
    low_52w: float
    health: int          # 0-100 composite score
    risk: str            # Calm | Normal | Wild
    trend: str           # up | down | sideways
    bullets: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


class Analyst:
    """Turns candles into a structured report + plain-English bullets."""

    def run(self, symbol: str, candles: list[Candle], last_price: float) -> AnalystReport:
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        s20 = sma(closes, 20)[-1]
        s50 = sma(closes, 50)[-1]
        r = rsi(closes, 14)[-1]
        _, _, hist = macd(closes)
        h = hist[-1]
        a = atr(highs, lows, closes, 14)[-1]
        vol = annualized_volatility(closes)
        floor, ceiling = support_resistance(closes)
        hi52, lo52 = max(highs), min(lows)
        prev_close = closes[-2] if len(closes) > 1 else last_price
        change = (last_price / prev_close - 1) * 100 if prev_close else 0.0

        trend = "sideways"
        if s20 and s50:
            if last_price > s20 > s50:
                trend = "up"
            elif last_price < s20 < s50:
                trend = "down"

        health = 50
        if trend == "up":
            health += 20
        elif trend == "down":
            health -= 20
        if r is not None:
            if 45 <= r <= 65:
                health += 10
            elif r > 75 or r < 25:
                health -= 10
        if h is not None:
            health += 5 if h > 0 else -5
        if last_price > hi52 * 0.92:
            health += 10
        health = max(0, min(100, health))

        risk = "Calm" if vol < 0.30 else ("Normal" if vol < 0.55 else "Wild")

        name = COMPANY_NAMES.get(symbol, symbol)
        bullets = []
        if trend == "up":
            bullets.append(f"Trend: up. Price is above both its 20-day and 50-day averages — buyers have been in control recently.")
        elif trend == "down":
            bullets.append(f"Trend: down. Price sits below its 20-day and 50-day averages — sellers are in charge for now.")
        else:
            bullets.append(f"Trend: sideways. Price is tangled in its moving averages — no clear winner between buyers and sellers.")
        if r is not None:
            if r > 70:
                bullets.append(f"Overheated momentum: RSI {r:.0f} — the stock has run hard and could cool off.")
            elif r < 30:
                bullets.append(f"Washed-out momentum: RSI {r:.0f} — heavily sold; bounces often start near here.")
            else:
                bullets.append(f"Healthy momentum: RSI {r:.0f} — {'rising, but not overheated' if h and h > 0 else 'cooling, not yet oversold'}.")
        if h is not None:
            bullets.append("Momentum is building (MACD above signal) — the recent move has force behind it." if h > 0
                           else "Momentum is fading (MACD crossed down) — the recent move is losing force.")
        bullets.append(f"How wild is it? It swings about {vol*100:.0f}% a year (annualised) — "
                       + ("treat any forecast with extra caution." if vol > 0.55 else "a fairly typical large-cap ride." if vol < 0.35 else "expect meaningful day-to-day swings."))
        bullets.append(f"Floor & ceiling: it tends to find a floor near {floor:.2f} and struggles to break past {ceiling:.2f} — handy for picking entries/exits.")
        if last_price > hi52 * 0.95:
            bullets.append(f"Near its 1-year high — strength, but also where profit-taking happens.")
        elif last_price < lo52 * 1.10:
            bullets.append(f"Near its 1-year low — cheap-looking, but falling knives are sharp.")

        return AnalystReport(
            symbol=symbol, price=last_price, change_pct=round(change, 2),
            sma20=s20, sma50=s50, rsi14=r, macd_hist=h, atr14=a,
            ann_vol=round(vol, 4), floor=round(floor, 2), ceiling=round(ceiling, 2),
            high_52w=round(hi52, 2), low_52w=round(lo52, 2),
            health=health, risk=risk, trend=trend, bullets=bullets,
        )


# ---------------------------------------------------------------------------
# Brains
# ---------------------------------------------------------------------------
@dataclass
class Decision:
    brain: str
    action: str         # BUY | SELL | HOLD
    confidence: float   # 0..1
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class Brain:
    name = "brain"

    def decide(self, analysis: AnalystReport, research: ResearchReport, position_qty: float) -> Decision:
        raise NotImplementedError


class MomentumBrain(Brain):
    """Trend-follower: buy strength, cut weakness."""

    name = "Momentum"

    def decide(self, a: AnalystReport, r: ResearchReport, position_qty: float) -> Decision:
        if a.trend == "up" and (a.rsi14 or 50) < 70 and r.sentiment >= -0.2:
            return Decision(self.name, BUY, min(0.9, 0.6 + (a.health - 50) / 100),
                            f"Uptrend intact, RSI {a.rsi14:.0f}, sentiment {r.sentiment:+.2f} — ride the trend.")
        if position_qty > 0 and (a.trend == "down" or (a.rsi14 or 50) > 78):
            return Decision(self.name, SELL, 0.75,
                            f"Trend {a.trend}, RSI {a.rsi14:.0f} — protect gains, exit.")
        return Decision(self.name, HOLD, 0.55, f"No edge: trend {a.trend}, RSI {a.rsi14:.0f}.")


class MeanReversionBrain(Brain):
    """Contrarian: buy fear near the floor, sell greed near the ceiling."""

    name = "MeanRev"

    def decide(self, a: AnalystReport, r: ResearchReport, position_qty: float) -> Decision:
        near_floor = a.price <= a.floor * 1.03
        near_ceiling = a.price >= a.ceiling * 0.97
        if (a.rsi14 or 50) < 35 and near_floor:
            return Decision(self.name, BUY, 0.7,
                            f"RSI {a.rsi14:.0f} near floor {a.floor} — oversold bounce setup.")
        if position_qty > 0 and (a.rsi14 or 50) > 68 and near_ceiling:
            return Decision(self.name, SELL, 0.7,
                            f"RSI {a.rsi14:.0f} near ceiling {a.ceiling} — take profit into strength.")
        # A mean-reverter can still agree with a healthy, non-frothy uptrend.
        # (In a steady uptrend price always hugs the recent ceiling, so the
        # ceiling veto applies only when RSI is also stretched.)
        if a.trend == "up" and 40 <= (a.rsi14 or 50) <= 66 and r.sentiment > -0.1:
            return Decision(self.name, BUY, 0.62,
                            f"Uptrend but not frothy (RSI {a.rsi14:.0f}) — acceptable entry.")
        return Decision(self.name, HOLD, 0.6, f"Price mid-range (RSI {a.rsi14:.0f}) — wait for an extreme.")


_LLM_PROMPT = """You are one of several independent trading brains in a paper-trading bot.
Given this JSON snapshot, reply with ONLY a JSON object:
{{"action": "BUY"|"SELL"|"HOLD", "confidence": 0.0-1.0, "reason": "<one sentence>"}}

Snapshot:
{snapshot}
Current position quantity: {qty}
Rules: be decisive but honest; HOLD when there is no edge."""


class LLMBrain(Brain):
    """Calls any chat-completions style API (Kimi, DeepSeek, OpenAI) or Anthropic.

    Falls back to HOLD on any error so one flaky API can never force a trade.
    """

    def __init__(self, name: str, kind: str, base_url: str, model: str, api_key: str):
        self.name = name
        self.kind = kind  # "anthropic" | "openai-compat"
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def decide(self, a: AnalystReport, r: ResearchReport, position_qty: float) -> Decision:
        snapshot = json.dumps({"analysis": a.as_dict(), "research": r.as_dict()}, default=str)
        prompt = _LLM_PROMPT.format(snapshot=snapshot, qty=position_qty)
        try:
            text = self._call(prompt)
            start, end = text.find("{"), text.rfind("}")
            obj = json.loads(text[start:end + 1])
            action = str(obj.get("action", HOLD)).upper()
            if action not in (BUY, SELL, HOLD):
                action = HOLD
            conf = max(0.0, min(1.0, float(obj.get("confidence", 0.5))))
            return Decision(self.name, action, conf, str(obj.get("reason", ""))[:300])
        except Exception as exc:  # network/parse errors must never crash the bot
            return Decision(self.name, HOLD, 0.0, f"brain unavailable ({type(exc).__name__}) — defaulting to HOLD")

    def _call(self, prompt: str) -> str:
        if self.kind == "anthropic":
            req = urllib.request.Request(
                f"{self.base_url}/v1/messages",
                data=json.dumps({
                    "model": self.model, "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}],
                }).encode(),
                headers={"content-type": "application/json",
                         "x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            return data["content"][0]["text"]
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps({
                "model": self.model, "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            }).encode(),
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]


def build_brains(cfg: Settings) -> list[Brain]:
    brains: list[Brain] = []
    for spec in [s.strip() for s in cfg.brains.split(",") if s.strip()]:
        kind, _, rest = spec.partition(":")
        if kind == "rule":
            brains.append(MomentumBrain() if rest == "momentum" else MeanReversionBrain())
        elif kind == "anthropic" and cfg.anthropic_api_key:
            brains.append(LLMBrain("Claude", "anthropic", "https://api.anthropic.com",
                                   rest or "claude-haiku-4-5-20251001", cfg.anthropic_api_key))
        elif kind == "kimi" and cfg.moonshot_api_key:
            brains.append(LLMBrain("Kimi", "openai-compat", "https://api.moonshot.ai/v1",
                                   rest or "kimi-k2-0905-preview", cfg.moonshot_api_key))
        elif kind == "deepseek" and cfg.deepseek_api_key:
            brains.append(LLMBrain("DeepSeek", "openai-compat", "https://api.deepseek.com",
                                   rest or "deepseek-chat", cfg.deepseek_api_key))
        elif kind == "openai-compat":
            base_url, _, model = rest.partition("|")
            if cfg.openai_api_key:
                brains.append(LLMBrain(model or "LLM", "openai-compat", base_url, model, cfg.openai_api_key))
    if len(brains) < 2:  # always have a working two-brain consensus
        brains = [MomentumBrain(), MeanReversionBrain()]
    return brains


# ---------------------------------------------------------------------------
# Consensus — the debate
# ---------------------------------------------------------------------------
@dataclass
class Verdict:
    action: str
    confidence: float
    agreed: bool
    votes: list[Decision]
    transcript: list[str]

    def as_dict(self) -> dict:
        return {"action": self.action, "confidence": self.confidence,
                "agreed": self.agreed, "votes": [v.as_dict() for v in self.votes],
                "transcript": self.transcript}


class Consensus:
    """Trades only when >= required brains agree on the same non-HOLD action."""

    def __init__(self, required: int):
        self.required = required

    def deliberate(self, votes: list[Decision]) -> Verdict:
        transcript = [f"{v.brain} {v.action} ({v.confidence:.2f}) — {v.reason}" for v in votes]
        for action in (BUY, SELL):
            backers = [v for v in votes if v.action == action]
            if len(backers) >= min(self.required, len(votes)):
                conf = sum(v.confidence for v in backers) / len(backers)
                transcript.append(f"{len(backers)} brain(s) AGREED on {action} → acting")
                return Verdict(action, round(conf, 3), True, votes, transcript)
        transcript.append("No agreement found — holding steady.")
        return Verdict(HOLD, 0.0, False, votes, transcript)


# ---------------------------------------------------------------------------
# Risk manager — the safety upgrade
# ---------------------------------------------------------------------------
class RiskManager:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self._last_trade: dict[str, float] = {}
        self.kill_switch = False
        self.kill_reason = ""

    def check_kill_switch(self, equity: float, day_start_equity: float) -> bool:
        if self.kill_switch:
            return True
        if day_start_equity > 0 and (equity / day_start_equity - 1) < -self.cfg.max_daily_loss_pct:
            self.kill_switch = True
            self.kill_reason = (f"daily loss exceeded {self.cfg.max_daily_loss_pct:.0%} "
                                f"({equity / day_start_equity - 1:.2%}) — trading halted for safety")
            return True
        return False

    def approve(self, symbol: str, verdict: Verdict, price: float,
                equity: float, position_value: float, cash: float) -> tuple[float, str]:
        """Returns (quantity, reason). quantity == 0 means rejected."""
        if self.kill_switch:
            return 0.0, f"kill-switch active: {self.kill_reason}"
        if verdict.confidence < self.cfg.min_confidence:
            return 0.0, f"confidence {verdict.confidence:.2f} below floor {self.cfg.min_confidence:.2f}"
        now = time.time()
        last = self._last_trade.get(symbol, 0)
        if now - last < self.cfg.trade_cooldown_sec:
            return 0.0, f"cooldown: traded {symbol} {now - last:.0f}s ago (min {self.cfg.trade_cooldown_sec}s)"

        if verdict.action == BUY:
            max_value = equity * self.cfg.max_position_pct
            budget = min(max_value - position_value, cash)
            if budget < price or budget <= 0:
                return 0.0, (f"position cap reached ({self.cfg.max_position_pct:.0%} of equity)"
                             if position_value > 0 else "insufficient cash")
            qty = math.floor(budget / price)
            self._last_trade[symbol] = now
            return float(qty), f"sized to {qty} shares (cap {self.cfg.max_position_pct:.0%} of equity)"

        if verdict.action == SELL:
            if position_value <= 0:
                return 0.0, "nothing to sell"
            self._last_trade[symbol] = now
            return -1.0, "closing full position"  # broker interprets -1 as 'all'
        return 0.0, "hold"
