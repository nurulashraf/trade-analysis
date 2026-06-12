"""App configuration. Everything has a safe default so the app runs offline."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# The AI-curated watchlist (mirrors the "better watchlist" idea from the post:
# US mega-cap tech + AI supply chain + quantum + Malaysia/ASEAN + defensives).
DEFAULT_WATCHLIST = [
    "META", "AVGO", "TSLA", "MSFT", "AMD", "INTC", "NVDA", "AAPL",
    "TSM", "ASML", "MRVL", "SMH", "VRT",            # AI supply chain
    "IONQ", "QBTS", "RGTI",                          # speculative quantum
    "5347.KL", "1023.KL",                            # Malaysia: Tenaga, CIMB
    "LLY", "JPM", "COST", "GEV",                     # defensives / power
]

COMPANY_NAMES = {
    "META": "Meta Platforms", "AVGO": "Broadcom", "TSLA": "Tesla",
    "MSFT": "Microsoft", "AMD": "AMD", "INTC": "Intel", "NVDA": "NVIDIA",
    "AAPL": "Apple", "TSM": "TSMC", "ASML": "ASML", "MRVL": "Marvell",
    "SMH": "VanEck Semiconductor ETF", "VRT": "Vertiv", "IONQ": "IonQ",
    "QBTS": "D-Wave Quantum", "RGTI": "Rigetti", "5347.KL": "Tenaga Nasional",
    "1023.KL": "CIMB Group", "LLY": "Eli Lilly", "JPM": "JPMorgan",
    "COST": "Costco", "GEV": "GE Vernova",
}


@dataclass
class Settings:
    # --- data ---
    data_provider: str = os.environ.get("DATA_PROVIDER", "mock")  # mock | yfinance
    watchlist: list[str] = field(default_factory=lambda: (
        os.environ.get("WATCHLIST", "").split(",")
        if os.environ.get("WATCHLIST") else list(DEFAULT_WATCHLIST)
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
