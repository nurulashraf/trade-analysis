# KONSENSUS

**Multi-asset, multi-agent trading terminal with dual-AI consensus execution.**

KONSENSUS is a self-hosted research and paper-trading platform. Independent
AI agents analyse a multi-asset watchlist — equities, commodity futures, and
currency pairs — and orders are simulated only when a configurable quorum of
decision agents independently reaches the same conclusion. A dedicated risk
layer enforces position limits, drawdown controls, and trade cooldowns.

```
┌─────────────────────────────────────────────────────────────────┐
│ Researcher agent ──► Analyst agent ──► Brain A ─┐               │
│  (news, sentiment)    (RSI, SMA, MACD,          ├─► Consensus   │
│                        vol, health score)       │   (N-of-M     │
│                                       Brain B ──┘    must agree)│
│                                                       │         │
│                              Risk manager ◄───────────┘         │
│                   (position caps, kill-switch, cooldowns)       │
│                                │                                │
│                       Broker (paper / moomoo)                   │
└─────────────────────────────────────────────────────────────────┘
```

## Features

- **Multi-asset coverage** — equities, commodity futures, and FX pairs in
  separate watchlist tabs; the trading engine operates across the combined
  universe. Symbols follow Yahoo Finance conventions (`GC=F`, `EURUSD=X`).
- **Terminal interface** — candlestick chart with SMA20/50 overlays, RSI and
  volume panels, volatility projection cone, live quote tape, per-symbol
  health and risk scoring, and a plain-language analyst summary.
- **Consensus execution** — decision agents ("brains") vote independently;
  the engine acts only when `REQUIRED_AGREEMENT` agents concur. Agent
  failures degrade to HOLD — a faulty API can never force a trade.
- **Pluggable decision agents** — deterministic rule-based agents (momentum,
  mean-reversion) run offline by default; Anthropic, Kimi, DeepSeek, or any
  OpenAI-compatible endpoint can be configured per agent.
- **Risk management** — per-position cap (15% of equity), daily-loss
  kill-switch (−3% halts trading), per-symbol cooldowns, and a minimum
  confidence floor.
- **Economic calendar** — this week's macro releases with impact rating,
  forecast, and prior values (sourced from the free Forex Factory weekly
  feed; deterministic offline fallback).
- **Backtesting** — one-click rule strategy vs. buy-and-hold per symbol:
  returns, win rate, trade count, max drawdown, and equity curves.
- **Deliberation log** — every agent vote and risk decision is streamed to
  the UI over WebSocket in real time.

## Quick start

Runs fully offline by default with deterministic demo market data — no API
keys or internet connection required.

```powershell
python -m venv .venv          # one-time: isolated environment
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run.bat                     # or: .\run.ps1, or: uvicorn backend.main:app --port 8000
```

Open http://localhost:8000 and press START AUTO-TRADER.

`run.bat` is a double-clickable wrapper around `run.ps1`, which loads `.env`
(if present), locates the project venv, and starts the server. On
Linux/macOS use `./run.sh`.

## Configuration

All settings are environment variables (or entries in `.env` — see
`.env.example` for the full annotated reference).

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_PROVIDER` | `mock` | `mock` (offline demo) or `yfinance` (real daily candles; `pip install yfinance`) |
| `WATCHLIST_STOCKS` | curated list | Equities tab (comma-separated Yahoo symbols) |
| `WATCHLIST_COMMODITIES` | `GC=F,SI=F,CL=F,NG=F,HG=F` | Commodities tab (futures, `=F`) |
| `WATCHLIST_FOREX` | `EURUSD=X,…,USDMYR=X` | FX tab (pairs, `=X`) |
| `BRAINS` | `rule:momentum,rule:meanrev` | Decision agents (see below) |
| `REQUIRED_AGREEMENT` | `2` | Votes required before the engine acts |
| `STARTING_CASH` | `10000` | Paper account opening balance |
| `MAX_POSITION_PCT` | `0.15` | Max share of equity per position |
| `MAX_DAILY_LOSS_PCT` | `0.03` | Daily drawdown kill-switch |
| `TRADE_COOLDOWN_SEC` | `120` | Minimum interval between trades per symbol |
| `MIN_CONFIDENCE` | `0.6` | Confidence floor for any execution |

### Decision agents

```powershell
$env:MOONSHOT_API_KEY = "..."    # Kimi
$env:DEEPSEEK_API_KEY = "..."
$env:BRAINS = "kimi:,deepseek:"
.\run.ps1
```

Supported specs: `rule:momentum`, `rule:meanrev`,
`anthropic:<model>` (requires `ANTHROPIC_API_KEY`), `kimi:<model>`,
`deepseek:<model>`, and `openai-compat:<base_url>|<model>` (requires
`OPENAI_API_KEY`). Any mix is valid.

## Live trading

The platform defaults to paper trading and will not place real orders
unless all of the following hold:

1. `moomoo-api` is installed and a [moomoo OpenD](https://openapi.moomoo.com/) gateway is running;
2. `LIVE_TRADING_ENABLED=true`;
3. `LIVE_TRADING_CONFIRM=I-UNDERSTAND-REAL-MONEY`.

Validate any strategy on paper over an extended period before considering
live execution. This software is provided for research and education; it is
not financial advice, and automated strategies can lose real money.

## Tests

```bash
pytest
```

## Project layout

```
backend/
  config.py      # env-driven settings; per-asset-class watchlists
  market.py      # data providers: mock (offline) + yfinance
  indicators.py  # SMA/EMA/RSI/MACD/ATR/vol/drawdown — pure Python
  agents.py      # researcher, analyst, decision agents, consensus, risk
  econcal.py     # economic calendar: weekly feed + offline fallback
  broker.py      # paper broker + (gated) moomoo live adapter
  bot.py         # orchestrator loop + websocket event bus
  backtest.py    # rule strategy vs buy & hold
  main.py        # FastAPI app: REST + WS + serves frontend
frontend/        # zero-dependency vanilla JS terminal UI
tests/           # pytest suite
run.ps1 / run.bat / run.sh   # launchers (Windows / Unix)
```
