"""Market data providers.

MockProvider generates deterministic, realistic-looking OHLCV series per
symbol so the whole app runs offline. YFinanceProvider pulls real daily
candles when `yfinance` is installed and DATA_PROVIDER=yfinance.
"""
from __future__ import annotations

import hashlib
import math
import random
import time
from dataclasses import dataclass, asdict

from .config import COMPANY_NAMES, asset_class


@dataclass
class Candle:
    time: int  # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float

    def as_dict(self) -> dict:
        return asdict(self)


# Per-symbol personality for the mock generator: (start price, annual drift, annual vol)
_PROFILES = {
    "META": (480, 0.18, 0.35), "AVGO": (300, 0.40, 0.45), "TSLA": (310, 0.10, 0.65),
    "MSFT": (410, 0.12, 0.25), "AMD": (300, 0.55, 0.60), "INTC": (45, 1.10, 0.84),
    "NVDA": (160, 0.35, 0.50), "AAPL": (250, 0.15, 0.28), "TSM": (290, 0.45, 0.40),
    "ASML": (1200, 0.50, 0.45), "MRVL": (150, 0.60, 0.62), "SMH": (420, 0.40, 0.38),
    "VRT": (200, 0.45, 0.66), "IONQ": (40, 0.40, 0.95), "QBTS": (15, 0.50, 1.10),
    "RGTI": (14, 0.45, 1.20), "5347.KL": (13, 0.12, 0.22), "1023.KL": (7, 0.08, 0.20),
    "LLY": (950, 0.20, 0.32), "JPM": (280, 0.12, 0.24), "COST": (980, 0.00, 0.22),
    "GEV": (560, 0.60, 0.55),
    # commodities (front-month futures)
    "GC=F": (3300, 0.15, 0.16), "SI=F": (38, 0.20, 0.30), "CL=F": (72, -0.05, 0.38),
    "NG=F": (3.2, 0.05, 0.60), "HG=F": (4.6, 0.10, 0.26),
    # forex — tiny drift, low vol, no meaningful volume
    "EURUSD=X": (1.09, 0.01, 0.08), "GBPUSD=X": (1.28, 0.01, 0.09),
    "USDJPY=X": (152, -0.02, 0.10), "AUDUSD=X": (0.66, 0.0, 0.10),
    "USDMYR=X": (4.45, -0.01, 0.07),
}
_DEFAULT_PROFILE = (100, 0.10, 0.40)
DAY = 86400


class MockProvider:
    """Deterministic GBM-ish candles with regime shifts; stable across restarts."""

    name = "mock"

    def __init__(self) -> None:
        self._cache: dict[str, list[Candle]] = {}

    def history(self, symbol: str, days: int = 260) -> list[Candle]:
        if symbol not in self._cache:
            self._cache[symbol] = self._generate(symbol, 260)
        return self._cache[symbol][-days:]

    def last_price(self, symbol: str) -> float:
        """History close plus a small live jitter that drifts over time."""
        base = self.history(symbol)[-1].close
        seed = int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % (2**32)
        # Jitter changes every ~5s, bounded to +-0.6%, deterministic per (symbol, bucket).
        bucket = int(time.time() // 5)
        rng = random.Random(seed ^ bucket)
        return round(base * (1 + rng.uniform(-0.006, 0.006)), 4)

    def _generate(self, symbol: str, days: int) -> list[Candle]:
        start, drift, vol = _PROFILES.get(symbol, _DEFAULT_PROFILE)
        # Volume scale by asset class: shares for stocks, contracts for
        # futures, zero for spot FX (matches what yfinance reports).
        vol_scale = {"stocks": 40_000_000, "commodities": 250_000, "forex": 0}[asset_class(symbol)]
        seed = int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        dt = 1.0 / 252
        # End the series at the most recent midnight so charts look current.
        end = int(time.time() // DAY * DAY)
        candles: list[Candle] = []
        price = float(start) / math.exp(drift * days * dt)  # walk up toward start price
        regime = 1.0
        for i in range(days):
            if rng.random() < 0.02:  # occasional regime flip: pullbacks happen
                regime = rng.choice([1.0, 1.0, -0.8, 1.5])
            shock = rng.gauss(0, 1)
            ret = (drift * regime - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * shock
            o = price
            c = max(price * math.exp(ret), 0.01)
            hi = max(o, c) * (1 + abs(rng.gauss(0, vol * 0.01)))
            lo = min(o, c) * (1 - abs(rng.gauss(0, vol * 0.01)))
            v = abs(rng.gauss(1, 0.4)) * vol_scale * (1 + 2 * abs(ret) / (vol * math.sqrt(dt) + 1e-9) * 0.1)
            t = end - (days - 1 - i) * DAY
            candles.append(Candle(t, o, hi, lo, c, round(v)))
            price = c
        # Rescale so the series ends at the profile's intended price level —
        # keeps the shape, makes quoted prices look like the real ticker.
        k = start / candles[-1].close if candles[-1].close > 0 else 1.0
        return [
            Candle(c.time, round(c.open * k, 4), round(c.high * k, 4),
                   round(c.low * k, 4), round(c.close * k, 4), c.volume)
            for c in candles
        ]


class YFinanceProvider:
    """Real daily candles via yfinance (optional dependency)."""

    name = "yfinance"

    def __init__(self) -> None:
        import yfinance  # noqa: F401 — fail fast if missing
        self._yf = yfinance
        self._cache: dict[str, tuple[float, list[Candle]]] = {}

    def history(self, symbol: str, days: int = 260) -> list[Candle]:
        now = time.time()
        cached = self._cache.get(symbol)
        if cached and now - cached[0] < 300:
            return cached[1][-days:]
        df = self._yf.Ticker(symbol).history(period="1y", interval="1d")
        candles = [
            Candle(int(ts.timestamp()), float(r["Open"]), float(r["High"]),
                   float(r["Low"]), float(r["Close"]), float(r["Volume"]))
            for ts, r in df.iterrows()
        ]
        self._cache[symbol] = (now, candles)
        return candles[-days:]

    def last_price(self, symbol: str) -> float:
        h = self.history(symbol, 2)
        return h[-1].close if h else 0.0


def make_provider(kind: str):
    if kind == "yfinance":
        try:
            return YFinanceProvider()
        except ImportError:
            pass  # fall back to mock so the app always starts
    return MockProvider()


# ---------------------------------------------------------------------------
# Mock news feed for the researcher agent (deterministic, rotates over time).
# ---------------------------------------------------------------------------
_HEADLINES = {
    "stocks": [
        ("{name} beats earnings expectations; raises full-year guidance", 0.8),
        ("Analysts upgrade {name} citing AI demand tailwinds", 0.6),
        ("{name} announces expanded data-center capacity deal", 0.5),
        ("Sector rotation puts mild pressure on {name}", -0.3),
        ("{name} faces supply-chain questions ahead of next quarter", -0.5),
        ("Regulators open review touching {name}'s market", -0.7),
        ("{name} unveils next-gen product roadmap at investor day", 0.4),
        ("Institutional buying detected in {name} options flow", 0.5),
        ("Profit-taking hits {name} after strong run", -0.4),
        ("{name} insider purchases signal management confidence", 0.3),
    ],
    "commodities": [
        ("Safe-haven demand lifts {name} as risk appetite fades", 0.6),
        ("Inventories build faster than expected, pressuring {name}", -0.6),
        ("Supply disruption fears support {name} prices", 0.5),
        ("Speculative longs in {name} hit multi-month high", 0.3),
        ("Stronger dollar weighs on {name}", -0.4),
        ("OPEC+ signals tighter supply discipline ahead", 0.4),
        ("Demand outlook for {name} cut on slowing industrial activity", -0.5),
        ("Central-bank buying underpins {name} bid", 0.5),
        ("Weather models shift, volatility expected in {name}", -0.2),
        ("Mine/field output guidance raised, capping {name} upside", -0.3),
    ],
    "forex": [
        ("Rate-differential outlook favours the base currency in {name}", 0.5),
        ("Central bank strikes hawkish tone, lifting {name}", 0.6),
        ("Soft inflation print weakens the base side of {name}", -0.5),
        ("Risk-off flows dominate {name} trading session", -0.4),
        ("Carry trade interest builds in {name}", 0.3),
        ("Intervention chatter caps moves in {name}", -0.2),
        ("Trade-balance surprise supports {name}", 0.4),
        ("Political uncertainty injects volatility into {name}", -0.4),
        ("Dovish minutes pressure the base currency in {name}", -0.5),
        ("Strong jobs data boosts the base side of {name}", 0.5),
    ],
}


def mock_news(symbol: str, n: int = 3) -> list[dict]:
    name = COMPANY_NAMES.get(symbol, symbol)
    pool = _HEADLINES[asset_class(symbol)]
    seed = int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % (2**32)
    bucket = int(time.time() // 600)  # rotate every 10 minutes
    rng = random.Random(seed ^ bucket)
    picks = rng.sample(pool, n)
    return [{"headline": h.format(name=name), "sentiment": s} for h, s in picks]
