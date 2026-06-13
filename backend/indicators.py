"""Pure-Python technical indicators. No numpy required."""
from __future__ import annotations

import math


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        return out
    acc = 0.0
    for i, v in enumerate(values):
        acc += v
        if i >= period:
            acc -= values[i - period]
        if i >= period - 1:
            out[i] = acc / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if not values or period <= 0:
        return out
    k = 2.0 / (period + 1)
    prev: float | None = None
    for i, v in enumerate(values):
        if i == period - 1:
            prev = sum(values[:period]) / period
            out[i] = prev
        elif prev is not None:
            prev = v * k + prev * (1 - k)
            out[i] = prev
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(d, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0.0)) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram)."""
    ef, es = ema(values, fast), ema(values, slow)
    line: list[float | None] = [
        (f - s) if f is not None and s is not None else None for f, s in zip(ef, es)
    ]
    compact = [v for v in line if v is not None]
    sig_compact = ema(compact, signal)
    sig: list[float | None] = [None] * len(values)
    j = 0
    for i, v in enumerate(line):
        if v is not None:
            sig[i] = sig_compact[j]
            j += 1
    hist = [
        (l - s) if l is not None and s is not None else None for l, s in zip(line, sig)
    ]
    return line, sig, hist


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    prev = sum(trs[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(closes)):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


def annualized_volatility(closes: list[float], lookback: int = 60) -> float:
    """Annualized stdev of daily log returns, as a fraction (0.84 = 84%/yr)."""
    closes = closes[-(lookback + 1):]
    if len(closes) < 3:
        return 0.0
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
    return math.sqrt(var) * math.sqrt(252)


def max_drawdown(equity: list[float]) -> float:
    """Max peak-to-trough drawdown as a negative fraction."""
    peak, mdd = float("-inf"), 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    return mdd


def support_resistance(closes: list[float], lookback: int = 60) -> tuple[float, float]:
    """Crude floor/ceiling: 10th/90th percentile of recent closes."""
    window = sorted(closes[-lookback:])
    if not window:
        return 0.0, 0.0
    lo = window[max(0, int(len(window) * 0.10) - 1)]
    hi = window[min(len(window) - 1, int(len(window) * 0.90))]
    return lo, hi
