from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Conversation, Strategy, User
from conftest import TEST_USER_ID, db_reachable

pytestmark = pytest.mark.skipif(
    not db_reachable(),
    reason="Postgres not reachable — run `docker compose up -d db` first",
)

FIXTURES = Path(__file__).parent / "fixtures"
NIFTY_CSV = str((FIXTURES / "nifty50.csv").resolve())


@pytest.fixture()
def client():
    return TestClient(app)


def _seed_strategy(generated_code: str | None = None) -> str:
    default_code = (FIXTURES / "buy_hold.py").read_text()
    code = default_code if generated_code is None else generated_code
    with SessionLocal() as session:
        # Owned by the conftest auth-stub identity, else ownership checks 404.
        existing = session.query(User).filter(User.id == TEST_USER_ID).first()
        user = existing or User(id=TEST_USER_ID, email="test@local")
        session.add(user)
        session.commit()
        session.refresh(user)
        conv = Conversation(user_id=user.id, title="Backtest test")
        session.add(conv)
        session.commit()
        session.refresh(conv)
        strat = Strategy(
            conversation_id=conv.id,
            name="Buy & Hold",
            description="Fixture strategy",
            generated_code=code,
        )
        session.add(strat)
        session.commit()
        session.refresh(strat)
        return strat.id


MOCK_METRICS = {
    "start_date": "2023-09-18",
    "end_date": "2024-09-17",
    "value_start": 100000.0,
    "value_end": 115790.0,
    "total_return_pct": 15.79,
    "benchmark_return_pct": 12.34,
    "sharpe": 1.23,
    "sortino": 1.45,
    "cagr_pct": 15.79,
    "num_trades": 0,
    "trades": [],
    "trades_truncated": 0,
    "equity_curve": [["2023-09-18", 100000.0], ["2024-09-17", 115790.0]],
    "warnings": ["no_trades"],
    "win_rate_pct": None,
    "profit_factor": None,
    "avg_win": None,
    "avg_loss": None,
    "closed_pnl": 0.0,
    "max_drawdown_pct": 0.0,
    "max_drawdown_duration_bars": None,
}


def _mock_backtest(monkeypatch, metrics=None):
    """Patch run_backtest_sandboxed to return fake metrics without spawning subprocesses."""
    mock_metrics = metrics or MOCK_METRICS

    def mock_run_backtest_sandboxed(*args, **kwargs):
        return mock_metrics

    monkeypatch.setattr("app.routers.strategies.run_backtest_sandboxed", mock_run_backtest_sandboxed)


class TestBacktestEndpoint:
    def test_backtest_success(self, client, db, monkeypatch):
        _mock_backtest(monkeypatch)
        strategy_id = _seed_strategy()
        resp = client.post(f"/strategies/{strategy_id}/backtest", json={"data_path": NIFTY_CSV})
        assert resp.status_code == 200
        body = resp.json()
        assert body["strategy_id"] == strategy_id
        assert body["status"] == "backtested"
        assert body["total_return_pct"] == pytest.approx(15.79, abs=1.0)
        assert body["cagr_pct"] is not None
        assert body["num_trades"] == 0

        with SessionLocal() as session:
            strat = session.get(Strategy, strategy_id)
            assert strat.status.value == "backtested"
            assert len(strat.backtest_results) == 1
            assert strat.backtest_results[0].total_return_pct == pytest.approx(15.79, abs=1.0)

    def test_backtest_unknown_strategy_returns_404(self, client, db):
        resp = client.post(
            "/strategies/00000000-0000-0000-0000-000000000000/backtest",
            json={"data_path": NIFTY_CSV},
        )
        assert resp.status_code == 404

    def test_backtest_without_code_returns_422(self, client, db, monkeypatch):
        _mock_backtest(monkeypatch)
        strategy_id = _seed_strategy(generated_code="")
        resp = client.post(f"/strategies/{strategy_id}/backtest", json={"data_path": NIFTY_CSV})
        assert resp.status_code == 422

    def test_backtest_rejects_guardrail_violation(self, client, db, monkeypatch):
        # Guardrail errors are raised before the sandbox call, so this tests the 422 path
        # when run_backtest_sandboxed raises BacktestError with "refused"
        from app.services.backtest_service import BacktestError

        def mock_raises(*args, **kwargs):
            raise BacktestError("refused import: os")

        monkeypatch.setattr("app.routers.strategies.run_backtest_sandboxed", mock_raises)

        strategy_id = _seed_strategy()
        resp = client.post(f"/strategies/{strategy_id}/backtest", json={"data_path": NIFTY_CSV})
        assert resp.status_code == 422
        assert "refused" in resp.json()["detail"].lower()

    def test_backtest_rejects_invalid_params(self, client, db, monkeypatch):
        _mock_backtest(monkeypatch)
        strategy_id = _seed_strategy()
        resp = client.post(
            f"/strategies/{strategy_id}/backtest",
            json={"data_path": NIFTY_CSV, "cash": -500},
        )
        assert resp.status_code == 422


class TestStrategyDetail:
    def test_detail_returns_code_for_viewer(self, client, db):
        strategy_id = _seed_strategy()
        resp = client.get(f"/strategies/{strategy_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["strategy_id"] == strategy_id
        assert body["name"] == "Buy & Hold"
        assert "class GeneratedStrategy" in body["generated_code"]

    def test_detail_unknown_strategy_returns_404(self, client, db):
        resp = client.get("/strategies/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestBacktestDashboardPayload:
    def test_trades_and_equity_curve_present(self, client, db, monkeypatch):
        # Mock with trades
        metrics_with_trades = {
            **MOCK_METRICS,
            "num_trades": 5,
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
            ] * 5,
            "trades_truncated": 0,
            "equity_curve": [["2023-09-18", 100000.0], ["2024-09-17", 115790.0]],
            "warnings": [],
            "win_rate_pct": 100.0,
        }
        _mock_backtest(monkeypatch, metrics_with_trades)

        strategy_id = _seed_strategy(
            generated_code=(FIXTURES / "swing_churn.py").read_text()
        )
        resp = client.post(f"/strategies/{strategy_id}/backtest", json={"data_path": NIFTY_CSV})
        assert resp.status_code == 200
        body = resp.json()

        assert len(body["trades"]) == body["num_trades"]
        assert body["trades_truncated"] == 0
        assert len(body["equity_curve"]) > 0
        assert body["equity_curve"][-1][0] == body["end_date"]