"""Core unit tests: indicators, consensus, risk, broker, backtest, API."""
import math

from backend.agents import (
    Analyst, Consensus, Decision, MeanReversionBrain, MomentumBrain,
    Researcher, RiskManager, BUY, HOLD, SELL,
)
from backend.backtest import run_backtest
from backend.broker import PaperBroker
from backend.config import Settings
from backend.indicators import macd, max_drawdown, rsi, sma
from backend.market import MockProvider


def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_rsi_bounds():
    prices = [100 + math.sin(i / 3) * 5 + i * 0.1 for i in range(100)]
    vals = [v for v in rsi(prices) if v is not None]
    assert vals and all(0 <= v <= 100 for v in vals)


def test_rsi_all_gains_is_100():
    assert rsi(list(range(1, 40)))[-1] == 100.0


def test_macd_alignment():
    prices = [float(i) for i in range(1, 80)]
    line, sig, hist = macd(prices)
    assert len(line) == len(sig) == len(hist) == 79
    assert hist[-1] is not None


def test_max_drawdown():
    assert max_drawdown([100, 120, 60, 90]) == 60 / 120 - 1


def test_mock_provider_deterministic():
    p1, p2 = MockProvider(), MockProvider()
    a, b = p1.history("NVDA"), p2.history("NVDA")
    assert [c.close for c in a] == [c.close for c in b]
    assert len(a) == 260
    assert all(c.low <= c.open <= c.high and c.low <= c.close <= c.high for c in a)


def test_consensus_requires_agreement():
    c = Consensus(required=2)
    votes = [Decision("A", BUY, 0.9, "x"), Decision("B", HOLD, 0.6, "y")]
    v = c.deliberate(votes)
    assert v.action == HOLD and not v.agreed

    votes = [Decision("A", BUY, 0.8, "x"), Decision("B", BUY, 0.6, "y")]
    v = c.deliberate(votes)
    assert v.action == BUY and v.agreed and abs(v.confidence - 0.7) < 1e-9


def test_paper_broker_roundtrip():
    b = PaperBroker(cash=1000)
    b.buy("XYZ", 4, 100, "test")
    assert b.cash == 600 and b.position("XYZ").qty == 4
    t = b.sell("XYZ", -1, 110, "test")  # -1 = close all
    assert t.qty == 4 and b.cash == 1040 and b.realized_pnl == 40
    assert "XYZ" not in b.positions


def test_risk_manager_caps_position():
    cfg = Settings()
    cfg.max_position_pct = 0.10
    cfg.min_confidence = 0.5
    rm = RiskManager(cfg)
    from backend.agents import Verdict
    v = Verdict(BUY, 0.9, True, [], [])
    qty, why = rm.approve("NVDA", v, price=100, equity=10000, position_value=0, cash=10000)
    assert qty == 10  # 10% of 10k / $100
    # Cooldown blocks an immediate second trade.
    qty2, why2 = rm.approve("NVDA", v, price=100, equity=10000, position_value=1000, cash=9000)
    assert qty2 == 0 and "cooldown" in why2


def test_risk_kill_switch():
    cfg = Settings()
    cfg.max_daily_loss_pct = 0.03
    rm = RiskManager(cfg)
    assert not rm.check_kill_switch(equity=9800, day_start_equity=10000)
    assert rm.check_kill_switch(equity=9600, day_start_equity=10000)
    assert rm.kill_switch


def test_brains_and_analyst_pipeline():
    provider = MockProvider()
    candles = provider.history("INTC")
    analyst, researcher = Analyst(), Researcher()
    report = analyst.run("INTC", candles, candles[-1].close)
    research = researcher.run("INTC")
    assert 0 <= report.health <= 100
    assert report.risk in ("Calm", "Normal", "Wild")
    assert report.bullets
    for brain in (MomentumBrain(), MeanReversionBrain()):
        d = brain.decide(report, research, position_qty=0)
        assert d.action in (BUY, SELL, HOLD)
        assert 0 <= d.confidence <= 1


def test_backtest_outputs():
    candles = MockProvider().history("NVDA")
    bt = run_backtest(candles, 10000)
    assert bt["equity_curve"][0]["buy_hold"] == 10000
    assert bt["max_drawdown"] <= 0
    assert 0 <= bt["win_rate"] <= 1


def test_api_smoke():
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
    assert client.get("/api/config").status_code == 200
    wl = client.get("/api/watchlist").json()
    assert len(wl) > 10
    sym = wl[0]["symbol"]
    assert client.get(f"/api/candles/{sym}").status_code == 200
    analysis = client.get(f"/api/analysis/{sym}").json()
    assert "bullets" in analysis["analysis"]
    assert client.post(f"/api/backtest/{sym}").status_code == 200
    status = client.get("/api/bot/status").json()
    assert status["mode"] == "paper"
