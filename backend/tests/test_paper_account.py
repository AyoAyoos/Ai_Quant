"""Tests for the Phase 1 paper-trading virtual account.

Phase 1 builds the *foundation* only: deploying a strategy opens a virtual
balance seeded with the configured capital, and the account can be valued at a
point in time. No strategy signal is executed, no order is placed, and the
positions/trades/orders ledgers are legitimately empty straight after a deploy.

The arithmetic cases deliberately use a small round-number account
(10000 -> 10050 / 9950). They are unit tests of the account maths only — they
prove the P&L formula, not that NIFTY 50 would be deployed with that capital.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.database import Base, SessionLocal, engine
from app.ids import MAX_ECHOED_ID
from app.main import app
from app.models import (
    Conversation,
    DeploymentStatus,
    PaperDeployment,
    PaperOrder,
    PaperPosition,
    PaperTrade,
    Strategy,
    StrategyStatus,
    User,
)
from app.services.paper_engine import open_account, snapshot
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

# Capital the MVP actually deploys with: a NIFTY 50 index unit is far above
# 10000, so the default 100000 is the working figure for the real demo.
DEPLOY_CASH = 100000.0

UNKNOWN_UUID = "00000000-0000-0000-0000-000000000000"
MALFORMED_IDS = ["abc123", "not-a-uuid", "'; DROP TABLE strategies; --", "x" * 300]


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


def _seed_strategy(status=StrategyStatus.approved, name="paper@local"):
    """Insert a strategy at a given lifecycle status; return its id."""
    with SessionLocal() as session:
        user = User(email=name)
        session.add(user)
        session.commit()
        session.refresh(user)
        conv = Conversation(user_id=user.id, title="Paper test")
        session.add(conv)
        session.commit()
        session.refresh(conv)
        strat = Strategy(
            conversation_id=conv.id,
            name="Paper Strategy",
            description="paper fixture",
            generated_code=CLEAN_CODE,
            status=status,
        )
        session.add(strat)
        session.commit()
        session.refresh(strat)
        return strat.id


def _account_pair(cash=DEPLOY_CASH, balance=None, realized=0.0, email="acct@local"):
    """A strategy + active deployment pair with a balance already set.

    Built directly so a test can put the account into an arbitrary state
    (partially invested, marked up or down) without simulating fills, which
    Phase 1 deliberately does not implement.
    """
    sid = _seed_strategy(status=StrategyStatus.paper_trading, name=email)
    with SessionLocal() as session:
        dep = PaperDeployment(
            strategy_id=sid,
            status=DeploymentStatus.active,
            cash=cash,
            commission_pct=0.1,
            sizer_percents=95.0,
            balance=cash if balance is None else balance,
            realized_pnl=realized,
        )
        session.add(dep)
        session.commit()
        session.refresh(dep)
        return sid, dep.id


def _add_position(deployment_id, symbol="NIFTY50", quantity=1,
                  avg_entry_price=500.0, last_price=None):
    with SessionLocal() as session:
        pos = PaperPosition(
            deployment_id=deployment_id,
            symbol=symbol,
            quantity=quantity,
            avg_entry_price=avg_entry_price,
            last_price=last_price,
        )
        session.add(pos)
        session.commit()
        session.refresh(pos)
        return pos.id


def _snap(deployment_id):
    with SessionLocal() as session:
        dep = session.query(PaperDeployment).filter(
            PaperDeployment.id == deployment_id
        ).first()
        return snapshot(dep)


class TestDeploymentOpensAccount:
    """A. Deploying opens the virtual account from the config snapshot."""

    def test_deploy_initialises_account_state(self, client, db):
        sid = _seed_strategy()
        resp = client.post(f"/strategies/{sid}/deploy", json={"cash": DEPLOY_CASH})
        assert resp.status_code == 200

        with SessionLocal() as session:
            dep = session.query(PaperDeployment).first()
            # The config snapshot stays exactly what was requested — this is the
            # immutable initial_balance, NOT the running balance.
            assert dep.cash == DEPLOY_CASH
            # The mutable account opened fully funded, with no P&L yet.
            assert dep.balance == DEPLOY_CASH
            assert dep.realized_pnl == 0.0
            assert dep.last_bar_date is None
            assert dep.last_error is None

    def test_deploy_leaves_ledgers_empty(self, client, db):
        sid = _seed_strategy()
        assert client.post(
            f"/strategies/{sid}/deploy", json={"cash": DEPLOY_CASH}
        ).status_code == 200

        for path in ("positions", "trades", "orders"):
            resp = client.get(f"/strategies/{sid}/{path}")
            assert resp.status_code == 200, path
            assert resp.json() == [], path

    def test_deploy_response_still_reports_configured_cash(self, client, db):
        """Existing behaviour preserved: deploy echoes the requested capital."""
        sid = _seed_strategy()
        resp = client.post(f"/strategies/{sid}/deploy", json={"cash": DEPLOY_CASH})
        assert resp.status_code == 200
        body = resp.json()
        assert body["cash"] == DEPLOY_CASH
        assert body["status"] == "active"

    def test_paper_account_right_after_deploy(self, client, db):
        sid = _seed_strategy()
        client.post(f"/strategies/{sid}/deploy", json={"cash": DEPLOY_CASH})

        resp = client.get(f"/strategies/{sid}/paper-account")
        assert resp.status_code == 200
        body = resp.json()
        assert body["initial_balance"] == DEPLOY_CASH
        assert body["cash_balance"] == DEPLOY_CASH
        assert body["position_value"] == 0.0
        assert body["equity"] == DEPLOY_CASH
        assert body["realized_pnl"] == 0.0
        assert body["unrealized_pnl"] == 0.0
        assert body["total_pnl"] == 0.0
        assert body["total_return_pct"] == 0.0
        assert body["open_positions"] == 0
        assert body["closed_trades"] == 0

    def test_redeploy_after_stop_opens_a_fresh_account(self, client, db):
        """A new deployment is a new account; the stopped row keeps its history."""
        sid = _seed_strategy()
        client.post(f"/strategies/{sid}/deploy", json={"cash": DEPLOY_CASH})
        client.post(f"/strategies/{sid}/stop", json={"reason": "done"})

        assert client.post(
            f"/strategies/{sid}/deploy", json={"cash": 50000.0}
        ).status_code == 200

        body = client.get(f"/strategies/{sid}/paper-account").json()
        assert body["initial_balance"] == 50000.0
        assert body["cash_balance"] == 50000.0
        assert body["total_pnl"] == 0.0


class TestOpenAccountHelper:
    """open_account() seeding contract, in isolation."""

    def test_copies_cash_into_balance_and_clears_derived_state(self):
        class FakeDeployment:
            cash = 75000.0
            balance = -1.0
            realized_pnl = 12.5
            last_bar_date = "stale"
            last_error = "boom"

        dep = open_account(FakeDeployment())
        assert dep.balance == 75000.0
        assert dep.realized_pnl == 0.0
        assert dep.last_bar_date is None
        assert dep.last_error is None


class TestSnapshotArithmetic:
    """B/C. The P&L maths — profit and loss cases as unit tests of the formula."""

    def test_profit_case_buy_500_sell_550(self, client, db):
        """10000 start -> 9500 cash after buying 1 unit at 500, marked at 550."""
        _sid, did = _account_pair(cash=10000.0, balance=9500.0)
        _add_position(did, quantity=1, avg_entry_price=500.0, last_price=550.0)

        snap = _snap(did)
        assert snap.position_value == 550.0
        assert snap.unrealized_pnl == 50.0
        assert snap.equity == 10050.0
        assert snap.total_pnl == 50.0
        assert snap.total_return_pct == pytest.approx(0.5)
        assert snap.realized_pnl == 0.0

    def test_loss_case_buy_500_sell_450(self, client, db):
        """10000 start -> 9500 cash after buying 1 unit at 500, marked at 450."""
        _sid, did = _account_pair(cash=10000.0, balance=9500.0)
        _add_position(did, quantity=1, avg_entry_price=500.0, last_price=450.0)

        snap = _snap(did)
        assert snap.position_value == 450.0
        assert snap.unrealized_pnl == -50.0
        assert snap.equity == 9950.0
        assert snap.total_pnl == -50.0
        assert snap.total_return_pct == pytest.approx(-0.5)
        assert snap.realized_pnl == 0.0

    def test_realised_pnl_is_separate_from_unrealised(self, client, db):
        """A closed trade books profit into cash *and* into realized_pnl."""
        _sid, did = _account_pair(cash=10000.0, balance=10050.0, realized=50.0)

        snap = _snap(did)
        assert snap.position_value == 0.0
        assert snap.unrealized_pnl == 0.0
        assert snap.realized_pnl == 50.0
        assert snap.equity == 10050.0
        assert snap.total_pnl == 50.0
        assert snap.total_return_pct == pytest.approx(0.5)

    def test_unmarked_position_is_valued_at_entry(self, client, db):
        """A never-marked position contributes cost basis and zero unrealised."""
        _sid, did = _account_pair(cash=10000.0, balance=9500.0)
        _add_position(did, quantity=1, avg_entry_price=500.0, last_price=None)

        snap = _snap(did)
        assert snap.position_value == 500.0
        assert snap.unrealized_pnl == 0.0
        assert snap.equity == 10000.0
        assert snap.total_pnl == 0.0

    def test_multiple_positions_are_summed(self, client, db):
        _sid, did = _account_pair(cash=10000.0, balance=8500.0)
        _add_position(did, symbol="NIFTY50", quantity=1, avg_entry_price=500.0, last_price=550.0)
        _add_position(did, symbol="BANKNIFTY", quantity=2, avg_entry_price=1000.0, last_price=1200.0)

        snap = _snap(did)
        assert snap.position_value == 2950.0  # 1*550 + 2*1200
        assert snap.unrealized_pnl == 450.0  # 50 + 400
        assert snap.equity == 8500.0 + 2950.0
        assert snap.total_pnl == 1450.0
        assert snap.open_positions == 2

    def test_deployment_scale_account(self, client, db):
        """The real demo figures: 100000 capital, one NIFTY-sized unit."""
        _sid, did = _account_pair(cash=100000.0, balance=23346.0)
        _add_position(did, quantity=3, avg_entry_price=23346.0, last_price=24000.0)

        snap = _snap(did)
        assert snap.initial_balance == 100000.0
        assert snap.position_value == 3 * 24000.0
        assert snap.unrealized_pnl == 3 * (24000.0 - 23346.0)
        assert snap.equity == 23346.0 + 3 * 24000.0
        assert snap.total_pnl == snap.equity - 100000.0

    def test_zero_initial_balance_does_not_divide_by_zero(self, client, db):
        """Defensive: a snapshot must never raise, even at zero capital."""
        _sid, did = _account_pair(cash=0.0, balance=0.0)

        snap = _snap(did)
        assert snap.initial_balance == 0.0
        assert snap.total_pnl == 0.0
        assert snap.total_return_pct == 0.0


class TestPaperAccountApi:
    """E. Read endpoints and their 404/422 contracts."""

    def test_paper_account_returns_snapshot(self, client, db):
        sid = _seed_strategy()
        client.post(f"/strategies/{sid}/deploy", json={"cash": DEPLOY_CASH})

        resp = client.get(f"/strategies/{sid}/paper-account")
        assert resp.status_code == 200
        body = resp.json()
        assert body["strategy_id"] == sid
        assert body["status"] == "active"
        assert body["initial_balance"] == DEPLOY_CASH
        assert body["cash_balance"] == DEPLOY_CASH
        assert body["equity"] == DEPLOY_CASH

    def test_paper_account_links_deployment_and_strategy(self, client, db):
        sid = _seed_strategy()
        deploy = client.post(f"/strategies/{sid}/deploy", json={"cash": DEPLOY_CASH}).json()

        body = client.get(f"/strategies/{sid}/paper-account").json()
        assert body["deployment_id"] == deploy["id"]
        assert body["strategy_id"] == sid

    def test_collections_return_empty_arrays_after_deploy(self, client, db):
        sid = _seed_strategy()
        client.post(f"/strategies/{sid}/deploy", json={"cash": DEPLOY_CASH})
        for path in ("positions", "trades", "orders"):
            resp = client.get(f"/strategies/{sid}/{path}")
            assert resp.status_code == 200, path
            assert resp.json() == [], path

    def test_positions_are_listed_when_present(self, client, db):
        """The endpoint surfaces rows even though Phase 1 never creates any."""
        _sid, did = _account_pair()
        _add_position(did, quantity=4, avg_entry_price=23346.0, last_price=24000.0)
        sid = _seed_strategy()
        # Attach the seeded account to this strategy's conversation so the
        # route can resolve it.
        with SessionLocal() as session:
            dep = session.query(PaperDeployment).filter(PaperDeployment.id == did).first()
            strat = session.query(Strategy).filter(Strategy.id == sid).first()
            dep.strategy_id = strat.id
            session.commit()

        resp = client.get(f"/strategies/{sid}/positions")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "NIFTY50"
        assert rows[0]["quantity"] == 4
        assert rows[0]["avg_entry_price"] == 23346.0
        assert rows[0]["last_price"] == 24000.0
        assert rows[0]["deployment_id"] == did

    def test_no_active_deployment_returns_422(self, client, db):
        """An approved-but-not-deployed strategy has no virtual account yet."""
        sid = _seed_strategy()
        for path in ("paper-account", "positions", "trades", "orders"):
            resp = client.get(f"/strategies/{sid}/{path}")
            assert resp.status_code == 422, path
            reasons = resp.json()["detail"]["reasons"]
            assert any("no active paper deployment" in r for r in reasons), path

    def test_stopped_deployment_returns_422(self, client, db):
        """After stop there is no active account to value."""
        sid = _seed_strategy()
        client.post(f"/strategies/{sid}/deploy", json={"cash": DEPLOY_CASH})
        client.post(f"/strategies/{sid}/stop", json={"reason": "done"})

        resp = client.get(f"/strategies/{sid}/paper-account")
        assert resp.status_code == 422
        assert any(
            "no active paper deployment" in r for r in resp.json()["detail"]["reasons"]
        )

    def test_unknown_uuid_returns_404(self, client, db):
        for path in ("paper-account", "positions", "trades", "orders"):
            resp = client.get(f"/strategies/{UNKNOWN_UUID}/{path}")
            assert resp.status_code == 404, path
            assert resp.json()["detail"] == f"Strategy {UNKNOWN_UUID} not found"

    @pytest.mark.parametrize("bad_id", MALFORMED_IDS)
    def test_malformed_id_returns_404_not_500(self, client, db, bad_id):
        """Malformed ids must never reach Postgres — see app.ids."""
        for path in ("paper-account", "positions", "trades", "orders"):
            resp = client.get(f"/strategies/{bad_id}/{path}")
            assert resp.status_code == 404, path
            assert resp.json()["detail"] == f"Strategy {bad_id[:MAX_ECHOED_ID]} not found"


class TestLedgerIntegrity:
    """The database enforces the paper-trading invariants."""

    def test_duplicate_open_position_for_same_symbol_is_rejected(self, client, db):
        """One open position per (deployment, symbol)."""
        _sid, did = _account_pair()
        _add_position(did, symbol="NIFTY50", quantity=1)

        with pytest.raises(IntegrityError):
            with SessionLocal() as session:
                session.add(
                    PaperPosition(
                        deployment_id=did, symbol="NIFTY50", quantity=2,
                        avg_entry_price=600.0,
                    )
                )
                session.commit()

    def test_same_symbol_on_a_different_deployment_is_allowed(self, client, db):
        _sid1, did1 = _account_pair(email="dup1@local")
        _sid2, did2 = _account_pair(email="dup2@local")
        _add_position(did1, symbol="NIFTY50", quantity=1)
        _add_position(did2, symbol="NIFTY50", quantity=3)  # must not raise
        assert _snap(did2).open_positions == 1

    def test_non_positive_quantity_is_rejected(self, client, db):
        _sid, did = _account_pair()
        with pytest.raises(IntegrityError):
            with SessionLocal() as session:
                session.add(
                    PaperPosition(
                        deployment_id=did, symbol="NIFTY50", quantity=0,
                        avg_entry_price=500.0,
                    )
                )
                session.commit()

    def test_invalid_order_side_is_rejected(self, client, db):
        _sid, did = _account_pair()
        with pytest.raises(IntegrityError):
            with SessionLocal() as session:
                session.add(
                    PaperOrder(deployment_id=did, symbol="NIFTY50", side="hodl", quantity=1)
                )
                session.commit()

    def test_invalid_order_status_is_rejected(self, client, db):
        _sid, did = _account_pair()
        with pytest.raises(IntegrityError):
            with SessionLocal() as session:
                session.add(
                    PaperOrder(
                        deployment_id=did, symbol="NIFTY50", side="buy", quantity=1,
                        status="maybe",
                    )
                )
                session.commit()

    def test_trade_net_pnl_must_match_gross_minus_commission(self, client, db):
        _sid, did = _account_pair()
        with pytest.raises(IntegrityError):
            with SessionLocal() as session:
                session.add(
                    PaperTrade(
                        deployment_id=did,
                        symbol="NIFTY50",
                        direction="long",
                        quantity=1,
                        entry_price=500.0,
                        exit_price=550.0,
                        entry_date=datetime(2024, 1, 1),
                        exit_date=datetime(2024, 1, 2),
                        gross_pnl=50.0,
                        commission=1.0,
                        net_pnl=999.0,  # inconsistent: should be 49.0
                        won=True,
                    )
                )
                session.commit()

    def test_valid_closed_trade_is_accepted(self, client, db):
        """The ledger accepts a coherent trade so Phase 2 has a legal target."""
        _sid, did = _account_pair()
        with SessionLocal() as session:
            session.add(
                PaperTrade(
                    deployment_id=did,
                    symbol="NIFTY50",
                    direction="long",
                    quantity=1,
                    entry_price=500.0,
                    exit_price=550.0,
                    entry_date=datetime(2024, 1, 1),
                    exit_date=datetime(2024, 1, 2),
                    gross_pnl=50.0,
                    commission=1.0,
                    net_pnl=49.0,
                    won=True,
                )
            )
            session.commit()

        resp_status = _snap(did).closed_trades
        assert resp_status == 1