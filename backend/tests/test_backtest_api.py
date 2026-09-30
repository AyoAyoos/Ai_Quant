from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Conversation, Strategy, User
from conftest import db_reachable

FIXTURES = Path(__file__).parent / "fixtures"
NIFTY_CSV = str((FIXTURES / "nifty50.csv").resolve())

pytestmark = pytest.mark.skipif(
    not db_reachable(),
    reason="Postgres not reachable — run `docker compose up -d db` first",
)


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


def _seed_strategy(generated_code: str | None = None) -> str:
    default_code = (FIXTURES / "buy_hold.py").read_text()
    code = default_code if generated_code is None else generated_code
    with SessionLocal() as session:
        user = User(email="test@local")
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


class TestBacktestEndpoint:
    def test_backtest_success(self, client, db):
        strategy_id = _seed_strategy()
        resp = client.post(f"/strategies/{strategy_id}/backtest", json={"data_path": NIFTY_CSV})
        assert resp.status_code == 200
        body = resp.json()
        assert body["strategy_id"] == strategy_id
        assert body["status"] == "backtested"
        assert body["total_return_pct"] == pytest.approx(15.79, abs=1.0)
        assert body["cagr_pct"] is not None
        assert body["num_trades"] == 0
        assert body["start_date"] and body["end_date"]

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

    def test_backtest_without_code_returns_422(self, client, db):
        strategy_id = _seed_strategy(generated_code="")
        resp = client.post(f"/strategies/{strategy_id}/backtest", json={"data_path": NIFTY_CSV})
        assert resp.status_code == 422

    def test_backtest_rejects_guardrail_violation(self, client, db):
        malicious = (
            "import backtrader as bt\n"
            "open('enemy.txt')\n"
            "class GeneratedStrategy(bt.Strategy):\n"
            "    def next(self):\n"
            "        self.buy()\n"
        )
        strategy_id = _seed_strategy(generated_code=malicious)
        resp = client.post(f"/strategies/{strategy_id}/backtest", json={"data_path": NIFTY_CSV})
        assert resp.status_code == 422
        assert "refused" in resp.json()["detail"].lower()

    def test_backtest_rejects_invalid_params(self, client, db):
        strategy_id = _seed_strategy()
        resp = client.post(
            f"/strategies/{strategy_id}/backtest",
            json={"data_path": NIFTY_CSV, "cash": -500},
        )
        assert resp.status_code == 422

    def test_backtest_active_strategy_reports_trades(self, client, db):
        strategy_id = _seed_strategy(
            generated_code=(FIXTURES / "swing_churn.py").read_text()
        )
        resp = client.post(f"/strategies/{strategy_id}/backtest", json={"data_path": NIFTY_CSV})
        assert resp.status_code == 200
        body = resp.json()
        assert body["num_trades"] > 0
        assert "no_trades" not in body["warnings"]


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
    def test_trades_and_equity_curve_present(self, client, db):
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