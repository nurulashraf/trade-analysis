"""App configuration. Everything has a safe default so the app runs offline."""
# Watchlists are grouped by asset class: stocks / commodities / forex.
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str) -> list[str] | None:
    raw = os.environ.get(name, "").strip()
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else None


def _build_watchlists() -> dict[str, list[str]]:
    legacy = _env_list("WATCHLIST")
    if legacy:  # flat legacy list: classify each symbol by suffix
        out: dict[str, list[str]] = {"stocks": [], "commodities": [], "forex": []}
        for s in legacy:
            out[asset_class(s)].append(s)
        return out
    return {
        "stocks": _env_list("WATCHLIST_STOCKS") or list(DEFAULT_WATCHLISTS["stocks"]),
        "commodities": _env_list("WATCHLIST_COMMODITIES") or list(DEFAULT_WATCHLISTS["commodities"]),
        "forex": _env_list("WATCHLIST_FOREX") or list(DEFAULT_WATCHLISTS["forex"]),
    }


# Watchlists by asset class. Symbols use Yahoo Finance conventions so the
# yfinance provider works unchanged: futures end in "=F", forex in "=X".
DEFAULT_WATCHLISTS = {
    # US mega-cap tech + AI supply chain + quantum + Malaysia/ASEAN + defensives
    "stocks": [
        "META", "AVGO", "TSLA", "MSFT", "AMD", "INTC", "NVDA", "AAPL",
        "TSM", "ASML", "MRVL", "SMH", "VRT",            # AI supply chain
        "IONQ", "QBTS", "RGTI",                          # speculative quantum
        "5347.KL", "1023.KL",                            # Malaysia: Tenaga, CIMB
        "LLY", "JPM", "COST", "GEV",                     # defensives / power
    ],
    "commodities": ["GC=F", "SI=F", "CL=F", "NG=F", "HG=F"],
    "forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDMYR=X"],
}

DEFAULT_WATCHLIST = [s for syms in DEFAULT_WATCHLISTS.values() for s in syms]


def asset_class(symbol: str) -> str:
    """Classify a symbol by Yahoo Finance suffix convention."""
    if symbol.endswith("=F"):
        return "commodities"
    if symbol.endswith("=X"):
        return "forex"
    return "stocks"


COMPANY_NAMES = {
    "META": "Meta Platforms", "AVGO": "Broadcom", "TSLA": "Tesla",
    "MSFT": "Microsoft", "AMD": "AMD", "INTC": "Intel", "NVDA": "NVIDIA",
    "AAPL": "Apple", "TSM": "TSMC", "ASML": "ASML", "MRVL": "Marvell",
    "SMH": "VanEck Semiconductor ETF", "VRT": "Vertiv", "IONQ": "IonQ",
    "QBTS": "D-Wave Quantum", "RGTI": "Rigetti", "5347.KL": "Tenaga Nasional",
    "1023.KL": "CIMB Group", "LLY": "Eli Lilly", "JPM": "JPMorgan",
    "COST": "Costco", "GEV": "GE Vernova",
    # commodities (front-month futures)
    "GC=F": "Gold", "SI=F": "Silver", "CL=F": "Crude Oil WTI",
    "NG=F": "Natural Gas", "HG=F": "Copper",
    # forex
    "EURUSD=X": "Euro / US Dollar", "GBPUSD=X": "British Pound / US Dollar",
    "USDJPY=X": "US Dollar / Japanese Yen", "AUDUSD=X": "Australian Dollar / US Dollar",
    "USDMYR=X": "US Dollar / Malaysian Ringgit",
}


@dataclass
class Settings:
    # --- data ---
    data_provider: str = os.environ.get("DATA_PROVIDER", "mock")  # mock | yfinance
    # Per-class lists, each overridable: WATCHLIST_STOCKS / _COMMODITIES / _FOREX.
    # Legacy WATCHLIST (flat, comma-separated) still works; symbols are
    # auto-classified by suffix (=F commodities, =X forex, else stocks).
    watchlists: dict[str, list[str]] = field(default_factory=lambda: _build_watchlists())
    watchlist: list[str] = field(default_factory=lambda: (
        [s for syms in _build_watchlists().values() for s in syms]
    ))

    # --- brains (the two AIs that must agree) ---
    # Comma-separated brain specs. Supported:
    #   rule:momentum, rule:meanrev            (offline, deterministic)
    #   anthropic:<model>                      (needs ANTHROPIC_API_KEY)
    #   openai-compat:<base_url>|<model>       (Kimi, DeepSeek, OpenAI, ...)
    brains: str = os.environ.get("BRAINS", "rule:momentum,rule:meanrev")
    # How many brains must agree before the bot acts (N-of-M consensus).
    required_agreement: int = int(os.environ.get("REQUIRED_AGREEMENT", "2"))

    # --- trading & risk ---
    broker: str = os.environ.get("BROKER", "paper")  # paper | moomoo
    starting_cash: float = float(os.environ.get("STARTING_CASH", "10000"))
    max_position_pct: float = float(os.environ.get("MAX_POSITION_PCT", "0.15"))
    max_daily_loss_pct: float = float(os.environ.get("MAX_DAILY_LOSS_PCT", "0.03"))
    trade_cooldown_sec: int = int(os.environ.get("TRADE_COOLDOWN_SEC", "120"))
    min_confidence: float = float(os.environ.get("MIN_CONFIDENCE", "0.6"))

    # Live trading is OFF unless BOTH flags are set. Paper is the default and
    # the only mode this repo will run without explicit, deliberate opt-in.
    live_trading_enabled: bool = _env_bool("LIVE_TRADING_ENABLED", False)
    live_trading_confirm: str = os.environ.get("LIVE_TRADING_CONFIRM", "")

    # --- bot loop ---
    tick_seconds: float = float(os.environ.get("TICK_SECONDS", "4"))

    # --- API keys (all optional) ---
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    moonshot_api_key: str = os.environ.get("MOONSHOT_API_KEY", "")
    deepseek_api_key: str = os.environ.get("DEEPSEEK_API_KEY", "")

    @property
    def live_armed(self) -> bool:
        return self.live_trading_enabled and self.live_trading_confirm == "I-UNDERSTAND-REAL-MONEY"


settings = Settings()
