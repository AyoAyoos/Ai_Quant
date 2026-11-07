import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import BacktestResult, Strategy, StrategyStatus, User, Conversation
from app.database import SessionLocal
from conftest import TEST_USER_ID, db_reachable

pytestmark = pytest.mark.skipif(not db_reachable(), reason="Postgres not reachable")

client = TestClient(app)

def _seed(status=StrategyStatus.backtested, backtest=None):
    with SessionLocal() as session:
        user = session.query(User).filter(User.id == TEST_USER_ID).first()
        if not user:
            user = User(id=TEST_USER_ID, email="gate@local")
            session.add(user)
            session.commit()
        conv = Conversation(user_id=user.id, title="test")
        session.add(conv)
        session.commit()
        strat = Strategy(conversation_id=conv.id, name="S", description="d", generated_code="import backtrader as bt\nclass GeneratedStrategy(bt.Strategy): pass", status=status)
        session.add(strat)
        session.commit()
        sid = strat.id
        if backtest:
            session.add(BacktestResult(strategy_id=sid, **backtest))
            session.commit()
        return sid

def test_min_trades_0():
    sid = _seed(backtest={"num_trades":0, "max_drawdown_pct":5, "win_rate_pct":50, "raw_metrics":{"sharpe":1.0}})
    resp = client.post(f"/strategies/{sid}/approve")
    assert resp.status_code == 422
    assert any("Approval requires at least 10 closed trades" in r for r in resp.json()["detail"]["reasons"])

def test_min_trades_9():
    sid = _seed(backtest={"num_trades":9, "max_drawdown_pct":5, "win_rate_pct":50, "raw_metrics":{"sharpe":1.0}})
    resp = client.post(f"/strategies/{sid}/approve")
    assert resp.status_code == 422
    assert any("Current closed trades: 9" in r for r in resp.json()["detail"]["reasons"])

def test_min_trades_10_eligible():
    sid = _seed(backtest={"num_trades":10, "max_drawdown_pct":10, "win_rate_pct":50, "raw_metrics":{"sharpe":0.6}})
    resp = client.post(f"/strategies/{sid}/approve")
    assert resp.status_code == 200

def test_open_positions_not_counted():
    # num_trades counts closed only; we just ensure prerequisite uses num_trades
    sid = _seed(backtest={"num_trades":5, "max_drawdown_pct":10, "win_rate_pct":50, "raw_metrics":{"sharpe":1.0}})
    resp = client.post(f"/strategies/{sid}/approve")
    assert resp.status_code == 422

def test_two_of_four_approve():
    sid = _seed(backtest={"num_trades":12, "max_drawdown_pct":20, "win_rate_pct":30, "raw_metrics":{"sharpe":0.4}})
    # passes: drawdown, trades ; sharpe fails, win_rate fails => 2 passes
    resp = client.post(f"/strategies/{sid}/approve")
    assert resp.status_code == 200

def test_two_of_four_reject_one():
    sid = _seed(backtest={"num_trades":12, "max_drawdown_pct":30, "win_rate_pct":30, "raw_metrics":{"sharpe":0.4}})
    # passes: trades only => 1 pass
    resp = client.post(f"/strategies/{sid}/approve")
    assert resp.status_code == 422

def test_two_of_four_reject_zero():
    sid = _seed(backtest={"num_trades":5, "max_drawdown_pct":30, "win_rate_pct":30, "raw_metrics":{"sharpe":0.4}})
    resp = client.post(f"/strategies/{sid}/approve")
    assert resp.status_code == 422

def test_four_pass():
    sid = _seed(backtest={"num_trades":12, "max_drawdown_pct":10, "win_rate_pct":50, "raw_metrics":{"sharpe":1.0}})
    resp = client.post(f"/strategies/{sid}/approve")
    assert resp.status_code == 200

def test_combined_less_than_10_even_if_criteria_pass():
    sid = _seed(backtest={"num_trades":9, "max_drawdown_pct":10, "win_rate_pct":50, "raw_metrics":{"sharpe":1.0}})
    resp = client.post(f"/strategies/{sid}/approve")
    assert resp.status_code == 422

def test_deploy_requires_approval():
    sid = _seed(status=StrategyStatus.backtested, backtest={"num_trades":12, "max_drawdown_pct":10, "win_rate_pct":50, "raw_metrics":{"sharpe":1.0}})
    resp = client.post(f"/strategies/{sid}/deploy", json={})
    assert resp.status_code == 422
    # approve then deploy
    client.post(f"/strategies/{sid}/approve")
    resp2 = client.post(f"/strategies/{sid}/deploy", json={})
    assert resp2.status_code == 200
