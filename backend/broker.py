"""Brokers. PaperBroker is the default; MoomooBroker wraps the official
moomoo OpenAPI SDK and only activates with explicit, deliberate opt-in.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_cost: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Trade:
    time: float
    symbol: str
    side: str
    qty: float
    price: float
    reason: str
    pnl: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PaperBroker:
    """In-memory simulated account. Fills at the quoted price."""

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    realized_pnl: float = 0.0

    name = "paper"

    def position(self, symbol: str) -> Position:
        return self.positions.get(symbol, Position(symbol))

    def equity(self, prices: dict[str, float]) -> float:
        value = self.cash
        for sym, pos in self.positions.items():
            value += pos.qty * prices.get(sym, pos.avg_cost)
        return value

    def buy(self, symbol: str, qty: float, price: float, reason: str) -> Trade:
        cost = qty * price
        if cost > self.cash + 1e-9:
            raise ValueError("insufficient cash")
        pos = self.positions.setdefault(symbol, Position(symbol))
        total_cost = pos.avg_cost * pos.qty + cost
        pos.qty += qty
        pos.avg_cost = total_cost / pos.qty
        self.cash -= cost
        trade = Trade(time.time(), symbol, "BUY", qty, price, reason)
        self.trades.append(trade)
        return trade

    def sell(self, symbol: str, qty: float, price: float, reason: str) -> Trade:
        pos = self.positions.get(symbol)
        if not pos or pos.qty <= 0:
            raise ValueError("no position")
        if qty < 0 or qty > pos.qty:  # -1 (or anything out of range) = close all
            qty = pos.qty
        pnl = (price - pos.avg_cost) * qty
        pos.qty -= qty
        self.cash += qty * price
        self.realized_pnl += pnl
        if pos.qty == 0:
            del self.positions[symbol]
        trade = Trade(time.time(), symbol, "SELL", qty, price, reason, pnl=round(pnl, 2))
        self.trades.append(trade)
        return trade

    def snapshot(self, prices: dict[str, float]) -> dict:
        equity = self.equity(prices)
        unrealized = sum(
            (prices.get(s, p.avg_cost) - p.avg_cost) * p.qty for s, p in self.positions.items()
        )
        return {
            "broker": self.name,
            "cash": round(self.cash, 2),
            "equity": round(equity, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "positions": [
                {**p.as_dict(), "last": prices.get(s, p.avg_cost),
                 "value": round(p.qty * prices.get(s, p.avg_cost), 2)}
                for s, p in self.positions.items()
            ],
            "trades": [t.as_dict() for t in self.trades[-50:]],
        }


class MoomooBroker:
    """Live trading through moomoo OpenD. Requires:
      1. `pip install moomoo-api` and a running OpenD gateway,
      2. LIVE_TRADING_ENABLED=true,
      3. LIVE_TRADING_CONFIRM=I-UNDERSTAND-REAL-MONEY.
    Until all three are true the app refuses to construct this broker.
    """

    name = "moomoo-live"

    def __init__(self, host: str = "127.0.0.1", port: int = 11111):
        from moomoo import OpenSecTradeContext, TrdMarket, SecurityFirm  # type: ignore
        self._ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US, host=host, port=port,
            security_firm=SecurityFirm.FUTUINC,
        )

    # The live implementation mirrors PaperBroker's interface; order placement
    # uses ctx.place_order(...). Deliberately not fleshed out further here —
    # wire it up only after you have validated the strategy on paper.
