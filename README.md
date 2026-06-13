# SAHAM PRO++ — Multi-Agent AI Trading Terminal

A self-hosted replica (and upgrade) of the viral "AI auto-trader" concept:
a terminal-style dashboard where **multiple AI agents research, analyse,
debate, and paper-trade a watchlist on their own** — and only execute when
two independent AI "brains" agree.

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

## Quick start (60 seconds, fully offline)

```bash
pip install -r requirements.txt
./run.sh                      # or: uvicorn backend.main:app --port 8000
# open http://localhost:8000 and press ▶ START THE BOT
```

Out of the box it uses deterministic demo market data and two rule-based
brains (a momentum trader and a mean-reversion contrarian), so the entire
experience — live bot log, debates, trades, P/L, backtests — works with no
API keys and no internet.

## What's in the box

- **Terminal UI** — watchlist, candlestick chart with SMA20/50, RSI panel,
  volume, a volatility **forecast cone**, live ticker tape, plain-English
  analysis ("Bottom line: INTC is a very volatile stock in an uptrend…"),
  health & risk scores.
- **AI AUTO-TRADER** — start/stop bot that round-robins the watchlist;
  every deliberation is streamed to the **live bot log** over WebSocket:
  `Kimi BUY · DeepSeek BUY AMD → AGREED, acting ✓`
  `Two brains found no agreement — holding steady.`
- **Dual-AI consensus** — plug in real LLM brains (Kimi, DeepSeek, Claude,
  any OpenAI-compatible endpoint) via env vars; trades happen only when
  `REQUIRED_AGREEMENT` brains independently pick the same action. A flaky
  API degrades to HOLD — it can never force a trade.
- **Risk manager (the upgrade the original lacked)** — per-position cap
  (15% of equity), daily-loss kill-switch (-3% halts the bot), per-symbol
  cooldowns, minimum-confidence floor.
- **Backtester** — one click per symbol: rule strategy vs buy & hold,
  win rate, trade count, max drawdown, equity curves.
- **Paper-first safety** — paper trading is the default and the only mode
  that runs without deliberate opt-in (see below).

## Using real LLM brains

```bash
export MOONSHOT_API_KEY=...    # Kimi
export DEEPSEEK_API_KEY=...
export BRAINS=kimi:,deepseek:
./run.sh
```

Any mix works: `BRAINS=anthropic:claude-haiku-4-5-20251001,kimi:` or
`BRAINS=openai-compat:https://api.openai.com/v1|gpt-4o-mini,rule:momentum`.

## Real market data

```bash
pip install yfinance
export DATA_PROVIDER=yfinance
```

## Live trading (read this first)

This project **defaults to paper trading and stays there**. The moomoo
adapter (`backend/broker.py`) only activates when *all* of these are true:

1. `pip install moomoo-api` and a running [moomoo OpenD](https://openapi.moomoo.com/) gateway,
2. `LIVE_TRADING_ENABLED=true`,
3. `LIVE_TRADING_CONFIRM=I-UNDERSTAND-REAL-MONEY`.

Even then: validate the strategy on paper for weeks first. **This is an
educational project, not financial advice. AI brains confidently make
mistakes; markets take real money from confident mistakes.**

## Tests

```bash
pytest
```

## Layout

```
backend/
  config.py      # env-driven settings, safe defaults
  market.py      # data providers: mock (offline) + yfinance
  indicators.py  # SMA/EMA/RSI/MACD/ATR/vol/drawdown — pure Python
  agents.py      # researcher, analyst, brains, consensus, risk manager
  broker.py      # paper broker + (gated) moomoo live adapter
  bot.py         # orchestrator loop + websocket event bus
  backtest.py    # rule strategy vs buy & hold
  main.py        # FastAPI app: REST + WS + serves frontend
frontend/        # zero-dependency vanilla JS terminal UI
tests/           # pytest suite
```
