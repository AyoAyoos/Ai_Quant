"""Integration tests for the strategy builder endpoint (requires DB and mocked LLM)."""
from pathlib import Path
import pytest
import json
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Conversation, Strategy, User

FIXTURES = Path(__file__).parent / "fixtures"
NIFTY_CSV = str((FIXTURES / "nifty50.csv").resolve())


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


def _mock_llm_success(monkeypatch):
    """Mock the LLM to return a valid strategy."""
    # Test-only dummy key: HTTP is fully mocked below, so no real LLM call
    # occurs. This only satisfies the empty-key guard in strategy_builder.
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "groq_api_key", "test-dummy-key")
    mock_llm_resp = json.dumps({
        "name": "EMA RSI Strategy",
        "description": "Buys when EMA 20 crosses above EMA 50 and RSI is below 30. Sells on opposite signal or risk management exits.",
        "code": '''import backtrader as bt

class GeneratedStrategy(bt.Strategy):
    params = (
        ("ema_fast_period", 20),
        ("ema_slow_period", 50),
        ("rsi_period", 14),
        ("rsi_oversold", 30),
        ("rsi_overbought", 70),
        ("stop_loss_pct", 1.0),
        ("take_profit_pct", 2.0),
        ("trailing_stop_pct", 0.5),
        ("max_trades_per_day", 3),
    )

    def __init__(self):
        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.p.ema_fast_period)
        self.ema_slow = bt.indicators.EMA(self.data.close, period=self.p.ema_slow_period)
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)
        self.trade_count = 0
        self.last_trade_date = None
        self.entry_price = None
        self.highest_price = None

    def next(self):
        current_date = self.data.datetime.date(0)
        if self.last_trade_date != current_date:
            self.trade_count = 0
            self.last_trade_date = current_date
        if self.trade_count >= self.p.max_trades_per_day:
            return
        ema_cross_up = self.ema_fast[0] > self.ema_slow[0] and self.ema_fast[-1] <= self.ema_slow[-1]
        rsi_oversold = self.rsi[0] < self.p.rsi_oversold
        if not self.position and ema_cross_up and rsi_oversold:
            self.buy()
            self.trade_count += 1
            self.entry_price = self.data.close[0]
            self.highest_price = self.data.close[0]
            return
        if self.position:
            ema_cross_down = self.ema_fast[0] < self.ema_slow[0] and self.ema_fast[-1] >= self.ema_slow[-1]
            rsi_overbought = self.rsi[0] > self.p.rsi_overbought
            exit_opposite = ema_cross_down or rsi_overbought
            current_price = self.data.close[0]
            self.highest_price = max(self.highest_price, current_price)
            stop_loss_hit = (self.entry_price - current_price) / self.entry_price * 100 >= self.p.stop_loss_pct
            take_profit_hit = (current_price - self.entry_price) / self.entry_price * 100 >= self.p.take_profit_pct
            trailing_stop_hit = (self.highest_price - current_price) / self.highest_price * 100 >= self.p.trailing_stop_pct
            if exit_opposite or stop_loss_hit or take_profit_hit or trailing_stop_hit:
                self.sell()
                self.entry_price = None
                self.highest_price = None'''
    })

    async def mock_post(*args, **kwargs):
        class MockResponse:
            def raise_for_status(self):
                pass
            def json(self):
                return {
                    "choices": [{"message": {"content": mock_llm_resp}}]
                }
        return MockResponse()

    monkeypatch.setattr("app.services.strategy_builder.httpx.AsyncClient.post", mock_post)


class TestBuilderEndpoint:
    def test_generate_strategy_success(self, client, db, monkeypatch):
        """Test successful strategy generation via builder endpoint."""
        _mock_llm_success(monkeypatch)

        spec = {
            "market": "NIFTY50",
            "trading_style": "intraday",
            "timeframe": "15m",
            "indicators": [
                {"name": "EMA", "parameters": {"fast": 20, "slow": 50}},
                {"name": "RSI", "parameters": {"period": 14, "oversold": 30, "overbought": 70}},
            ],
            "entry_conditions": ["EMA 20 crosses above EMA 50", "RSI is below 30"],
            "exit_conditions": ["Exit on opposite signal"],
            "risk_management": {
                "stop_loss_percent": 1,
                "take_profit_percent": 2,
                "trailing_stop_percent": 0.5,
                "max_trades_per_day": 3,
            },
        }

        resp = client.post("/strategies/builder", json=spec)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        body = resp.json()

        assert "strategy_id" in body
        assert body["name"] == "EMA RSI Strategy"
        assert "EMA" in body["generated_code"]
        assert "RSI" in body["generated_code"]
        assert body["status"] == "draft"
        assert body["strategy_specification"]["market"] == "NIFTY50"

    def test_generate_strategy_invalid_indicator_params(self, client, db):
        """Test that invalid indicator parameters are rejected before LLM call."""
        spec = {
            "market": "NIFTY50",
            "trading_style": "intraday",
            "timeframe": "15m",
            "indicators": [
                {"name": "EMA", "parameters": {"fast": 20}},  # missing slow
            ],
            "entry_conditions": ["EMA crossover"],
            "exit_conditions": ["EMA crossunder"],
            "risk_management": {
                "stop_loss_percent": 1,
                "take_profit_percent": 2,
            },
        }

        resp = client.post("/strategies/builder", json=spec)
        assert resp.status_code == 422
        body = resp.json()
        assert "errors" in body["detail"]
        assert any("slow" in e for e in body["detail"]["errors"])


class TestBuilderBacktestFlow:
    def test_generate_then_backtest(self, client, db, monkeypatch):
        """Test full flow: generate strategy then backtest it."""
        _mock_llm_success(monkeypatch)

        # Generate strategy
        spec = {
            "market": "NIFTY50",
            "trading_style": "intraday",
            "timeframe": "15m",
            "indicators": [
                {"name": "EMA", "parameters": {"fast": 20, "slow": 50}},
                {"name": "RSI", "parameters": {"period": 14, "oversold": 30, "overbought": 70}},
            ],
            "entry_conditions": ["EMA 20 crosses above EMA 50", "RSI is below 30"],
            "exit_conditions": ["Exit on opposite signal"],
            "risk_management": {
                "stop_loss_percent": 1,
                "take_profit_percent": 2,
                "trailing_stop_percent": 0.5,
                "max_trades_per_day": 3,
            },
        }

        gen_resp = client.post("/strategies/builder", json=spec)
        assert gen_resp.status_code == 200
        gen_body = gen_resp.json()
        strategy_id = gen_body["strategy_id"]

        # Now backtest the generated strategy
        def mock_backtest(*args, **kwargs):
            return {
                "start_date": "2023-09-18",
                "end_date": "2024-09-17",
                "value_start": 100000.0,
                "value_end": 115790.0,
                "total_return_pct": 15.79,
                "benchmark_return_pct": 12.34,
                "sharpe": 1.23,
                "sortino": 1.45,
                "cagr_pct": 15.79,
                "num_trades": 15,
                "trades": [
                    {
                        "entry_date": "2023-10-01",
                        "exit_date": "2023-10-05",
                        "entry_price": 19500.0,
                        "exit_price": 19800.0,
                        "size": 5,
                        "direction": "long",
                        "bars_held": 4,
                        "pnl": 1500.0,
                        "pnl_net": 1490.0,
                        "won": True,
                    }
                ] * 15,
                "trades_truncated": 0,
                "equity_curve": [["2023-09-18", 100000.0], ["2024-09-17", 115790.0]],
                "warnings": [],
                "win_rate_pct": 60.0,
                "profit_factor": 1.5,
                "avg_win": 1200.0,
                "avg_loss": -800.0,
                "closed_pnl": 6000.0,
                "max_drawdown_pct": 8.5,
                "max_drawdown_duration_bars": 12,
            }
        
        monkeypatch.setattr("app.routers.strategies.run_backtest_sandboxed", mock_backtest)

        bt_resp = client.post(
            f"/strategies/{strategy_id}/backtest",
            json={"data_path": NIFTY_CSV}
        )
        assert bt_resp.status_code == 200
        bt_body = bt_resp.json()
        
        assert bt_body["strategy_id"] == strategy_id
        assert bt_body["status"] == "backtested"
        assert bt_body["num_trades"] == 15
        assert bt_body["total_return_pct"] == pytest.approx(15.79, abs=1.0)
        assert len(bt_body["trades"]) == 15


class TestBuilderValidation:
    def test_invalid_market_rejected(self, client, db):
        spec = {
            "market": "INVALID_MARKET",
            "trading_style": "intraday",
            "timeframe": "15m",
            "indicators": [{"name": "EMA", "parameters": {"fast": 20, "slow": 50}}],
            "entry_conditions": ["EMA crossover"],
            "exit_conditions": ["EMA crossunder"],
            "risk_management": {"stop_loss_percent": 1, "take_profit_percent": 2},
        }
        resp = client.post("/strategies/builder", json=spec)
        assert resp.status_code == 422

    def test_invalid_trading_style_rejected(self, client, db):
        spec = {
            "market": "NIFTY50",
            "trading_style": "invalid_style",
            "timeframe": "15m",
            "indicators": [{"name": "EMA", "parameters": {"fast": 20, "slow": 50}}],
            "entry_conditions": ["EMA crossover"],
            "exit_conditions": ["EMA crossunder"],
            "risk_management": {"stop_loss_percent": 1, "take_profit_percent": 2},
        }
        resp = client.post("/strategies/builder", json=spec)
        assert resp.status_code == 422

    def test_incompatible_timeframe_rejected(self, client, db):
        # Scalping only supports 5m, 15m
        spec = {
            "market": "NIFTY50",
            "trading_style": "scalping",
            "timeframe": "1d",  # Not compatible
            "indicators": [{"name": "EMA", "parameters": {"fast": 20, "slow": 50}}],
            "entry_conditions": ["EMA crossover"],
            "exit_conditions": ["EMA crossunder"],
            "risk_management": {"stop_loss_percent": 1, "take_profit_percent": 2},
        }
        resp = client.post("/strategies/builder", json=spec)
        assert resp.status_code == 422

    def test_duplicate_indicators_rejected(self, client, db):
        spec = {
            "market": "NIFTY50",
            "trading_style": "intraday",
            "timeframe": "15m",
            "indicators": [
                {"name": "EMA", "parameters": {"fast": 20, "slow": 50}},
                {"name": "EMA", "parameters": {"fast": 10, "slow": 30}},  # Duplicate
            ],
            "entry_conditions": ["EMA crossover"],
            "exit_conditions": ["EMA crossunder"],
            "risk_management": {"stop_loss_percent": 1, "take_profit_percent": 2},
        }
        resp = client.post("/strategies/builder", json=spec)
        assert resp.status_code == 422

    def test_empty_entry_conditions_rejected(self, client, db):
        spec = {
            "market": "NIFTY50",
            "trading_style": "intraday",
            "timeframe": "15m",
            "indicators": [{"name": "EMA", "parameters": {"fast": 20, "slow": 50}}],
            "entry_conditions": [],  # Empty
            "exit_conditions": ["EMA crossunder"],
            "risk_management": {"stop_loss_percent": 1, "take_profit_percent": 2},
        }
        resp = client.post("/strategies/builder", json=spec)
        assert resp.status_code == 422

    def test_empty_exit_conditions_rejected(self, client, db):
        spec = {
            "market": "NIFTY50",
            "trading_style": "intraday",
            "timeframe": "15m",
            "indicators": [{"name": "EMA", "parameters": {"fast": 20, "slow": 50}}],
            "entry_conditions": ["EMA crossover"],
            "exit_conditions": [],  # Empty
            "risk_management": {"stop_loss_percent": 1, "take_profit_percent": 2},
        }
        resp = client.post("/strategies/builder", json=spec)
        assert resp.status_code == 422