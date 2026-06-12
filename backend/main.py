"""SAHAM PRO++ — FastAPI app: REST + WebSocket + static frontend.

Run:  uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agents import Analyst, Researcher
from .backtest import run_backtest
from .bot import EventBus, TradingBot
from .broker import PaperBroker
from .config import COMPANY_NAMES, settings
from .market import make_provider

app = FastAPI(title="SAHAM PRO++", version="1.0")

provider = make_provider(settings.data_provider)
bus = EventBus()
broker = PaperBroker(cash=settings.starting_cash)
bot = TradingBot(settings, provider, broker, bus)
analyst = Analyst()
researcher = Researcher()

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


# ----------------------------------------------------------------- REST API
@app.get("/api/config")
def get_config():
    return {
        "watchlist": settings.watchlist,
        "names": COMPANY_NAMES,
        "provider": provider.name,
        "mode": "LIVE" if settings.live_armed else "paper",
        "brains": [b.name for b in bot.brains],
        "required_agreement": settings.required_agreement,
        "starting_cash": settings.starting_cash,
    }


@app.get("/api/watchlist")
def get_watchlist():
    out = []
    for sym in settings.watchlist:
        candles = provider.history(sym, 2)
        last = provider.last_price(sym)
        prev = candles[-2].close if len(candles) > 1 else last
        out.append({
            "symbol": sym,
            "name": COMPANY_NAMES.get(sym, sym),
            "price": last,
            "change_pct": round((last / prev - 1) * 100, 2) if prev else 0.0,
        })
    return out


@app.get("/api/candles/{symbol}")
def get_candles(symbol: str, days: int = 90):
    candles = provider.history(symbol, days)
    if not candles:
        raise HTTPException(404, f"no data for {symbol}")
    return [c.as_dict() for c in candles]


@app.get("/api/analysis/{symbol}")
def get_analysis(symbol: str):
    candles = provider.history(symbol)
    if not candles:
        raise HTTPException(404, f"no data for {symbol}")
    price = provider.last_price(symbol)
    report = analyst.run(symbol, candles, price)
    research = researcher.run(symbol)
    return {
        "analysis": report.as_dict(),
        "research": research.as_dict(),
        "last_verdict": bot.last_verdicts.get(symbol),
    }


@app.get("/api/portfolio")
def get_portfolio():
    prices = {s: provider.last_price(s) for s in
              set(settings.watchlist) | set(broker.positions.keys())}
    return broker.snapshot(prices)


@app.post("/api/bot/start")
async def bot_start():
    bot.start()
    return bot.status()


@app.post("/api/bot/stop")
async def bot_stop():
    bot.stop()
    return bot.status()


@app.get("/api/bot/status")
def bot_status():
    return bot.status()


@app.post("/api/backtest/{symbol}")
def backtest(symbol: str):
    candles = provider.history(symbol, 500)
    if len(candles) < 60:
        raise HTTPException(404, f"not enough data for {symbol}")
    return {"symbol": symbol, **run_backtest(candles, settings.starting_cash)}


# ---------------------------------------------------------------- WebSocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    q = bus.subscribe()
    try:
        for ev in bus.history[-50:]:  # replay recent log so the UI isn't blank
            await ws.send_json(ev)
        while True:
            ev = await q.get()
            await ws.send_json(ev)
    except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
        pass
    finally:
        bus.unsubscribe(q)


# ------------------------------------------------------------------- static
@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
