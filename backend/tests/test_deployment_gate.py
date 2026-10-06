"""Tests for the paper-trading deployment gate.

Covers the full lifecycle: draft -> backtested -> approved -> paper_trading,
plus rejection and stop transitions. Backtest rows are inserted directly —
the gate reads stored results, so re-running backtests here would only add
minutes for no extra coverage.
"""
import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import BacktestResult, Conversation, Strategy, StrategyStatus, User
from conftest import db_reachable

pytestmark = pytest.mark.skipif(
    not db_reachable(),
    reason="Postgres not reachable — run `docker compose up -d db` first",
)

CLEAN_CODE = (
    "import backtrader as bt\n"
    "class GeneratedStrategy(bt.Strategy):\n"
    "    def next(self):\n"
    "        self.buy()\n"
)
MALICIOUS_CODE = (
    "import backtrader as bt\n"
    "open('enemy.txt')\n"
    "class GeneratedStrategy(bt.Strategy):\n"
    "    def next(self):\n"
    "        self.buy()\n"
)


@pytest.fixture()
def client():
    return TestClient(app)


def _seed(status=StrategyStatus.draft, code=CLEAN_CODE, backtest=None) -> str:
    """Insert a strategy, optionally with a backtest result row."""
    with SessionLocal() as session:
        user = User(email="gate@local")
        session.add(user)
        session.commit()
        session.refresh(user)
        conv = Conversation(user_id=user.id, title="Gate test")
        session.add(conv)
        session.commit()
        session.refresh(conv)
        strat = Strategy(
            conversation_id=conv.id,
            name="Gate Strategy",
            description="gate fixture",
            generated_code=code,
            status=status,
        )
        session.add(strat)
        session.commit()
        session.refresh(strat)
        sid = strat.id
        if backtest is not None:
            session.add(BacktestResult(strategy_id=sid, **backtest))
            session.commit()
        return sid


GOOD_BACKTEST = {"num_trades": 12, "max_drawdown_pct": 8.5, "total_return_pct": 10.0}


class TestApprove:
    def test_approve_passing_strategy(self, client, db):
        sid = _seed(status=StrategyStatus.backtested, backtest=dict(GOOD_BACKTEST))
        resp = client.post(f"/strategies/{sid}/approve")
        assert resp.status_code == 200
        assert resp.json() == {"strategy_id": sid, "status": "approved", "status_note": None}

    def test_approve_draft_fails(self, client, db):
        sid = _seed(status=StrategyStatus.draft)
        resp = client.post(f"/strategies/{sid}/approve")
        assert resp.status_code == 422
        reasons = resp.json()["detail"]["reasons"]
        assert any("backtested" in r for r in reasons)
        assert any("no backtest" in r for r in reasons)

    def test_approve_zero_trades_fails(self, client, db):
        sid = _seed(
            status=StrategyStatus.backtested,
            backtest={"num_trades": 0, "max_drawdown_pct": 0.0},
        )
        resp = client.post(f"/strategies/{sid}/approve")
        assert resp.status_code == 422
        assert any("trade" in r for r in resp.json()["detail"]["reasons"])

    def test_approve_extreme_drawdown_fails(self, client, db):
        sid = _seed(
            status=StrategyStatus.backtested,
            backtest={"num_trades": 20, "max_drawdown_pct": 75.0},
        )
        resp = client.post(f"/strategies/{sid}/approve")
        assert resp.status_code == 422
        assert any("drawdown" in r for r in resp.json()["detail"]["reasons"])

    def test_approve_unknown_strategy_404(self, client, db):
        resp = client.post("/strategies/00000000-0000-0000-0000-000000000000/approve")
        assert resp.status_code == 404


class TestReject:
    def test_reject_draft_with_reason(self, client, db):
        sid = _seed(status=StrategyStatus.draft)
        resp = client.post(f"/strategies/{sid}/reject", json={"reason": "overfit"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["status_note"] == "overfit"

    def test_reject_needs_reason(self, client, db):
        sid = _seed(status=StrategyStatus.draft)
        resp = client.post(f"/strategies/{sid}/reject", json={"reason": "no"})
        assert resp.status_code == 422  # min_length=3

    def test_reject_paper_trading_fails(self, client, db):
        sid = _seed(status=StrategyStatus.approved, backtest=dict(GOOD_BACKTEST))
        client.post(f"/strategies/{sid}/approve")
        client.post(f"/strategies/{sid}/deploy", json={})
        resp = client.post(f"/strategies/{sid}/reject", json={"reason": "changed mind"})
        assert resp.status_code == 422


class TestDeploy:
    def test_full_lifecycle(self, client, db):
        sid = _seed(status=StrategyStatus.backtested, backtest=dict(GOOD_BACKTEST))
        assert client.post(f"/strategies/{sid}/approve").status_code == 200

        resp = client.post(f"/strategies/{sid}/deploy", json={"cash": 50000})
        assert resp.status_code == 200
        dep = resp.json()
        assert dep["strategy_id"] == sid
        assert dep["status"] == "active"
        assert dep["cash"] == 50000
        assert dep["deployed_at"]
        assert dep["stopped_at"] is None

        # Second deploy while active is refused.
        resp = client.post(f"/strategies/{sid}/deploy", json={})
        assert resp.status_code == 422

        # Stop returns to approved and closes the record.
        resp = client.post(f"/strategies/{sid}/stop", json={"reason": "done"})
        assert resp.status_code == 200
        stopped = resp.json()
        assert stopped["status"] == "stopped"
        assert stopped["stopped_at"]
        assert stopped["stop_reason"] == "done"

        # History shows the closed deployment.
        resp = client.get(f"/strategies/{sid}/deployments")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Detail reflects the return to approved.
        assert client.get(f"/strategies/{sid}").json()["status"] == "approved"

    def test_deploy_unapproved_fails(self, client, db):
        sid = _seed(status=StrategyStatus.backtested, backtest=dict(GOOD_BACKTEST))
        resp = client.post(f"/strategies/{sid}/deploy", json={})
        assert resp.status_code == 422
        assert any("approved" in r for r in resp.json()["detail"]["reasons"])

    def test_deploy_rechecks_guardrails(self, client, db):
        sid = _seed(status=StrategyStatus.approved, code=MALICIOUS_CODE)
        resp = client.post(f"/strategies/{sid}/deploy", json={})
        assert resp.status_code == 422
        assert any("guardrail" in r for r in resp.json()["detail"]["reasons"])

    def test_stop_without_deployment_fails(self, client, db):
        sid = _seed(status=StrategyStatus.approved)
        resp = client.post(f"/strategies/{sid}/stop", json={})
        assert resp.status_code == 422

    def test_redeploy_after_stop_allowed(self, client, db):
        sid = _seed(status=StrategyStatus.backtested, backtest=dict(GOOD_BACKTEST))
        client.post(f"/strategies/{sid}/approve")
        client.post(f"/strategies/{sid}/deploy", json={})
        client.post(f"/strategies/{sid}/stop", json={})
        resp = client.post(f"/strategies/{sid}/deploy", json={})
        assert resp.status_code == 200
        assert len(client.get(f"/strategies/{sid}/deployments").json()) == 2
