"""Backtest the rule strategy (not the LLM brains) on daily closes.
No fees/slippage. Past performance does not predict future results.
"""
from __future__ import annotations

from .indicators import max_drawdown, rsi, sma
from .market import Candle


def run_backtest(candles: list[Candle], starting_cash: float = 10_000.0) -> dict:
    closes = [c.close for c in candles]
    times = [c.time for c in candles]
    s20, s50 = sma(closes, 20), sma(closes, 50)
    r14 = rsi(closes, 14)

    cash, qty = starting_cash, 0.0
    entry = 0.0
    wins = losses = trades = 0
    equity_curve: list[dict] = []
    bh_qty = starting_cash / closes[0] if closes and closes[0] > 0 else 0.0

    for i, px in enumerate(closes):
        in_pos = qty > 0
        if s20[i] is not None and s50[i] is not None and r14[i] is not None:
            uptrend = px > s20[i] > s50[i]
            if not in_pos and uptrend and r14[i] < 70:
                qty = cash / px
                cash, entry = 0.0, px
            elif in_pos and (px < s20[i] or r14[i] > 78):
                cash = qty * px
                trades += 1
                if px > entry:
                    wins += 1
                else:
                    losses += 1
                qty = 0.0
        equity_curve.append({
            "time": times[i],
            "strategy": round(cash + qty * px, 2),
            "buy_hold": round(bh_qty * px, 2),
        })

    final = equity_curve[-1] if equity_curve else {"strategy": starting_cash, "buy_hold": starting_cash}
    strat_ret = final["strategy"] / starting_cash - 1
    bh_ret = final["buy_hold"] / starting_cash - 1
    return {
        "strategy_return": round(strat_ret, 4),
        "buy_hold_return": round(bh_ret, 4),
        "edge": round(strat_ret - bh_ret, 4),
        "win_rate": round(wins / trades, 4) if trades else 0.0,
        "trades": trades,
        "max_drawdown": round(max_drawdown([p["strategy"] for p in equity_curve]), 4),
        "equity_curve": equity_curve,
        "starting_cash": starting_cash,
        "note": ("Tests the RULE strategy (not the AI brains) on daily closes; "
                 "no fees/slippage. Past performance does not predict future results."),
    }
