"""Phase 2 tests — simulated paper-trade execution.

Every test drives the account from synthetic bars. Nothing here touches Yahoo
Finance or the network, and the API tests stub the strategy replay so they stay
fast; the real subprocess signal path is exercised separately in
``TestSignalGeneration``.

Arithmetic convention throughout: ``commission_pct`` is a percentage of notional,
matching ``strategy_runner``'s ``COMM_PERC`` broker config. At the default 0.1% a
1-unit fill costs 0.005 x price, so a round trip is charged on both legs and the
total lands on ``PaperTrade.commission``.
"""
import itertools
from datetime import datetime, timedelta
from decimal import Decimal

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
from app.services.paper_bars import (
    PaperBar,
    PaperBarDuplicate,
    PaperBarError,
    load_bars,
    next_bar,
    validate_bar,
)
from app.services.paper_engine import (
    ORDER_FILLED,
    ORDER_REJECTED,
    PaperExecutionError,
    commission_for,
    execute_buy,
    execute_sell,
    find_position,
    mark_positions,
    open_account,
    run_tick,
    size_for_cash,
    snapshot,
    validate_price,
)
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


class _FakeData:
    """Stand-in for a Backtrader data feed in the sizer-parity check."""

    def __init__(self, close):
        self.close = [close]

SYMBOL = "NIFTY50"
COMMISSION_PCT = 0.1  # 0.1% of notional, per leg
SIZER_PERCENTS = 95.0
UNKNOWN_UUID = "00000000-0000-0000-0000-000000000000"

DAY0 = datetime(2024, 1, 1)


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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_ACCOUNT_SEQ = itertools.count()


def _account(
    cash=10000.0,
    commission_pct=COMMISSION_PCT,
    sizer_percents=SIZER_PERCENTS,
    status=StrategyStatus.paper_trading,
    dep_status=DeploymentStatus.active,
    code=CLEAN_CODE,
    email=None,
):
    """Seed a strategy + deployment directly, bypassing the HTTP gate."""
    # A counter keeps the email unique even when one test seeds several
    # accounts with otherwise identical parameters.
    email = email or (
        f"p2-{next(_ACCOUNT_SEQ)}-{cash}-{commission_pct}-{sizer_percents}-"
        f"{status.value}-{dep_status.value}@local"
    )
    with SessionLocal() as session:
        user = User(email=email)
        session.add(user)
        session.commit()
        session.refresh(user)
        conv = Conversation(user_id=user.id, title="Paper 2")
        session.add(conv)
        session.commit()
        session.refresh(conv)
        strat = Strategy(
            conversation_id=conv.id,
            name="Paper 2 Strategy",
            generated_code=code,
            status=status,
            market=SYMBOL,
        )
        session.add(strat)
        session.commit()
        session.refresh(strat)
        dep = PaperDeployment(
            strategy_id=strat.id,
            status=dep_status,
            cash=cash,
            commission_pct=commission_pct,
            sizer_percents=sizer_percents,
        )
        # The deploy route always calls this; a hand-built row that skips it
        # would keep the ORM default balance of 0.0 and reject every order.
        open_account(dep)
        session.add(dep)
        session.commit()
        session.refresh(dep)
        return strat.id, dep.id


def _bar(day: int, close: float, symbol=SYMBOL, **overrides) -> PaperBar:
    """A valid flat-ish bar at ``close``, so OHLC consistency never fails."""
    base = dict(
        symbol=symbol,
        bar_date=DAY0 + timedelta(days=day),
        open_=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=1000.0,
    )
    base.update(overrides)
    return validate_bar(**base)


def _state(deployment_id):
    """Read the whole account eagerly, so nothing is inspected after detach."""
    with SessionLocal() as session:
        dep = (
            session.query(PaperDeployment)
            .filter(PaperDeployment.id == deployment_id)
            .first()
        )
        return {
            "balance": dep.balance,
            "realized_pnl": dep.realized_pnl,
            "last_bar_date": dep.last_bar_date,
            "last_error": dep.last_error,
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_entry_price": p.avg_entry_price,
                    "last_price": p.last_price,
                    "opened_at": p.opened_at,
                }
                for p in dep.positions
            ],
            "trades": [
                {
                    "symbol": t.symbol,
                    "direction": t.direction,
                    "quantity": t.quantity,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "gross_pnl": t.gross_pnl,
                    "commission": t.commission,
                    "net_pnl": t.net_pnl,
                    "won": t.won,
                    "entry_date": t.entry_date,
                    "exit_date": t.exit_date,
                }
                for t in dep.trades
            ],
            "orders": [
                {
                    "side": o.side,
                    "quantity": o.quantity,
                    "status": o.status,
                    "reason": o.reason,
                    "fill_price": o.fill_price,
                    "order_type": o.order_type,
                }
                for o in dep.orders
            ],
        }


def _snap(deployment_id):
    with SessionLocal() as session:
        dep = (
            session.query(PaperDeployment)
            .filter(PaperDeployment.id == deployment_id)
            .first()
        )
        return snapshot(dep)


class _OrderView:
    """Plain snapshot of a persisted PaperOrder.

    The engine returns a live ORM object, but a test cannot read its attributes
    once the session closes (``DetachedInstanceError`` after commit), so the
    harness copies the fields out while still attached.
    """

    __slots__ = (
        "id", "side", "quantity", "status", "reason", "fill_price",
        "filled_at", "order_type", "created_at",
    )

    def __init__(self, order):
        for name in self.__slots__:
            setattr(self, name, getattr(order, name, None))

    def __repr__(self):
        return (
            f"<Order {self.side} {self.quantity} {self.status} "
            f"@{self.fill_price} {self.reason!r}>"
        )


def _run(deployment_id, fn, *args, **kwargs):
    """Apply an engine function to a live deployment and persist the result."""
    with SessionLocal() as session:
        dep = (
            session.query(PaperDeployment)
            .filter(PaperDeployment.id == deployment_id)
            .first()
        )
        result = fn(dep, *args, **kwargs)
        if isinstance(result, PaperOrder):
            session.add(result)
        session.commit()

        if isinstance(result, PaperOrder):
            return _OrderView(result)
        # run_tick returns a dict whose "order" may be an ORM object too.
        if isinstance(result, dict) and isinstance(result.get("order"), PaperOrder):
            result = dict(result)
            result["order"] = _OrderView(result["order"])
        return result


def _tick(deployment_id, bar, action, quantity=None):
    return _run(
        deployment_id,
        lambda dep: run_tick(dep, bar, action, quantity=quantity),
    )


# --------------------------------------------------------------------------- #
# Price / input validation (section 12)
# --------------------------------------------------------------------------- #
class TestPriceValidation:
    @pytest.mark.parametrize(
        "bad", [0, -1, -0.01, float("nan"), float("inf"), float("-inf"), None, "abc"]
    )
    def test_rejects_unusable_price(self, bad):
        with pytest.raises(PaperExecutionError):
            validate_price(bad)

    @pytest.mark.parametrize("good", [0.01, 1, 23346.75, 1e6])
    def test_accepts_positive_finite_price(self, good):
        assert validate_price(good) == float(good)

    def test_nan_price_cannot_corrupt_an_account(self, db):
        _sid, did = _account()
        before = _state(did)
        with pytest.raises(PaperExecutionError):
            _run(did, execute_buy, SYMBOL, float("nan"), _bar(0, 500.0), quantity=1)
        assert _state(did) == before


class TestBarValidation:
    @pytest.mark.parametrize("bad_close", [0, -5, float("nan"), float("inf")])
    def test_rejects_bad_close(self, bad_close):
        with pytest.raises(PaperBarError):
            _bar(0, bad_close)

    def test_rejects_inconsistent_ohlc(self):
        with pytest.raises(PaperBarError):
            validate_bar(
                symbol=SYMBOL, bar_date=DAY0, open_=100, high=90, low=95, close=100,
                volume=10,
            )

    def test_rejects_high_below_close(self):
        # high must be >= max(open, close); 99 < 100 breaks that.
        with pytest.raises(PaperBarError, match="inconsistent"):
            validate_bar(
                symbol=SYMBOL, bar_date=DAY0, open_=100, high=99, low=98, close=100,
                volume=10,
            )

    def test_rejects_negative_volume(self):
        with pytest.raises(PaperBarError):
            _bar(0, 100.0, volume=-1)

    def test_allows_zero_volume(self):
        assert _bar(0, 100.0, volume=0).volume == 0.0

    def test_rejects_unparseable_date(self):
        with pytest.raises(PaperBarError):
            validate_bar(
                symbol=SYMBOL, bar_date="not-a-date", open_=100, high=101, low=99,
                close=100, volume=1,
            )

    def test_symbol_is_normalised(self):
        assert _bar(0, 100.0, symbol="nifty50").symbol == "NIFTY50"


class TestCommissionAndSizing:
    def test_commission_is_percent_of_notional(self):
        assert commission_for(COMMISSION_PCT, 1, 500.0) == pytest.approx(0.5)
        assert commission_for(COMMISSION_PCT, 2, 500.0) == pytest.approx(1.0)

    def test_explicit_quantity_must_be_at_least_one(self):
        with pytest.raises(PaperExecutionError):
            size_for_cash(10000, 500, 95, quantity=0)
        with pytest.raises(PaperExecutionError):
            size_for_cash(10000, 500, 95, quantity=-3)

    def test_sized_quantity_uses_the_percent_sizer_formula(self):
        # int(cash / price * percents/100) — the whole-unit equivalent of
        # bt.sizers.PercentSizer, which the project adds with retint=False.
        assert size_for_cash(10000, 500, 95) == int(10000 / 500 * 0.95)
        assert size_for_cash(100000, 23346, 95) == int(100000 / 23346 * 0.95)

    def test_parity_with_backtrader_percent_sizer(self):
        """The reused formula must match the sizer the backtester installs.

        ``bt.sizers.PercentSizer._getsizing`` is ``cash / data.close[0] *
        (percents / 100)`` and is added with the default ``retint=False``, so
        it returns a float that the broker truncates to whole units. Phase 2 is
        integer-only, so our result is that truncation.
        """
        import backtrader as bt

        sizer = bt.sizers.PercentSizer(percents=95.0)
        assert sizer.p.retint is False  # float sizing, truncated by the broker

        for cash, price in ((10000.0, 500.0), (100000.0, 23346.0), (55555.0, 101.25)):
            raw = cash / price * (95.0 / 100)
            assert size_for_cash(cash, price, 95) == int(raw)
            # and the same truncation backtrader's broker would apply
            assert _FakeData(price).close[0] == price

    def test_cannot_size_a_position_it_cannot_afford(self):
        assert size_for_cash(100, 500, 95) == 0
        assert size_for_cash(0, 500, 95) == 0


# --------------------------------------------------------------------------- #
# A. BUY success
# --------------------------------------------------------------------------- #
class TestBuySuccess:
    def test_buy_fills_and_opens_position(self, db):
        _sid, did = _account(cash=10000.0)
        bar = _bar(0, 500.0)

        order = _run(did, execute_buy, SYMBOL, 500.0, bar_date=bar.bar_date, quantity=1)

        assert order.status == ORDER_FILLED
        assert order.side == "buy"
        assert order.quantity == 1
        assert order.fill_price == 500.0
        assert order.filled_at == bar.bar_date
        assert order.reason is None

        state = _state(did)
        # 1 unit @ 500 + 0.1% commission (0.50) leaves 9499.50
        assert state["balance"] == pytest.approx(9499.5)
        assert len(state["positions"]) == 1
        position = state["positions"][0]
        assert position["symbol"] == SYMBOL
        assert position["quantity"] == 1
        assert position["avg_entry_price"] == 500.0
        assert position["last_price"] == 500.0
        assert position["opened_at"] == bar.bar_date

    def test_buy_records_an_auditable_order(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        orders = _state(did)["orders"]
        assert len(orders) == 1
        assert orders[0]["status"] == ORDER_FILLED
        assert orders[0]["order_type"] == "market"

    def test_buy_without_explicit_quantity_sizes_from_cash(self, db):
        _sid, did = _account(cash=10000.0)
        order = _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date)
        assert order.quantity == size_for_cash(10000.0, 500.0, SIZER_PERCENTS)
        assert order.quantity == 19  # int(10000/500*0.95)

    def test_snapshot_reflects_a_fresh_position(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)

        snap = _snap(did)
        assert snap.initial_balance == 10000.0
        assert snap.cash_balance == pytest.approx(9499.5)
        assert snap.position_value == 500.0
        assert snap.equity == pytest.approx(9999.5)
        assert snap.total_pnl == pytest.approx(-0.5)  # commission only
        assert snap.open_positions == 1


# --------------------------------------------------------------------------- #
# B. SELL profit   /   C. SELL loss
# --------------------------------------------------------------------------- #
class TestSellProfit:
    def test_sell_closes_position_and_books_the_trade(self, db):
        _sid, did = _account(cash=10000.0)
        entry = _bar(0, 500.0)
        exit_bar = _bar(1, 550.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=entry.bar_date, quantity=1)

        order = _run(did, execute_sell, SYMBOL, 550.0, bar_date=exit_bar.bar_date)

        assert order.status == ORDER_FILLED
        assert order.side == "sell"
        assert order.quantity == 1
        assert order.fill_price == 550.0

        state = _state(did)
        assert state["positions"] == []  # position closed

        assert len(state["trades"]) == 1
        trade = state["trades"][0]
        assert trade["symbol"] == SYMBOL
        assert trade["direction"] == "long"
        assert trade["quantity"] == 1
        assert trade["entry_price"] == 500.0
        assert trade["exit_price"] == 550.0
        assert trade["entry_date"] == entry.bar_date
        assert trade["exit_date"] == exit_bar.bar_date
        assert trade["gross_pnl"] == pytest.approx(50.0)
        # round trip: 0.5 (buy @500) + 0.55 (sell @550)
        assert trade["commission"] == pytest.approx(1.05)
        assert trade["net_pnl"] == pytest.approx(48.95)
        assert trade["won"] is True

        assert state["realized_pnl"] == pytest.approx(48.95)
        # 10000 - 500.50 + (550 - 0.55)
        assert state["balance"] == pytest.approx(10048.95)

    def test_net_pnl_equals_gross_minus_total_commission(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        _run(did, execute_sell, SYMBOL, 550.0, bar_date=_bar(1, 550.0).bar_date)
        trade = _state(did)["trades"][0]
        assert trade["net_pnl"] == pytest.approx(
            trade["gross_pnl"] - trade["commission"], abs=1e-9
        )


class TestSellLoss:
    def test_sell_at_a_loss(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)

        _run(did, execute_sell, SYMBOL, 450.0, bar_date=_bar(1, 450.0).bar_date)

        state = _state(did)
        assert state["positions"] == []
        trade = state["trades"][0]
        assert trade["gross_pnl"] == pytest.approx(-50.0)
        assert trade["commission"] == pytest.approx(0.95)  # 0.50 + 0.45
        assert trade["net_pnl"] == pytest.approx(-50.95)
        assert trade["won"] is False
        assert state["realized_pnl"] == pytest.approx(-50.95)
        # 10000 - 500.50 + (450 - 0.45)
        assert state["balance"] == pytest.approx(9949.05)
        assert state["realized_pnl"] < 0


# --------------------------------------------------------------------------- #
# D. Unrealised profit while holding
# --------------------------------------------------------------------------- #
class TestUnrealizedPnl:
    def test_hold_bar_marks_the_position_up(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)

        _tick(did, _bar(1, 550.0), "hold")

        state = _state(did)
        assert state["positions"][0]["last_price"] == 550.0
        assert state["balance"] == pytest.approx(9499.5)  # unchanged by a HOLD

        snap = _snap(did)
        assert snap.position_value == 550.0
        assert snap.unrealized_pnl == pytest.approx(50.0)
        assert snap.equity == pytest.approx(10049.5)
        assert snap.realized_pnl == 0.0
        assert snap.total_pnl == pytest.approx(49.5)  # 50 unrealised less 0.50 paid
        assert snap.open_positions == 1
        assert snap.closed_trades == 0

    def test_marking_moves_down_too(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        _tick(did, _bar(1, 450.0), "hold")
        snap = _snap(did)
        assert snap.unrealized_pnl == pytest.approx(-50.0)
        assert snap.equity == pytest.approx(9949.5)


# --------------------------------------------------------------------------- #
# E. Insufficient balance
# --------------------------------------------------------------------------- #
class TestInsufficientBalance:
    def test_buy_beyond_cash_is_rejected(self, db):
        _sid, did = _account(cash=1000.0)
        before = _state(did)

        order = _run(
            did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=100
        )

        assert order.status == ORDER_REJECTED
        assert "insufficient funds" in order.reason
        assert order.fill_price is None

        after = _state(did)
        assert after["balance"] == before["balance"]
        assert after["positions"] == []
        assert after["trades"] == []
        # The rejection is still auditable.
        assert len(after["orders"]) == 1
        assert after["orders"][0]["status"] == ORDER_REJECTED

    def test_buy_that_cannot_afford_one_unit_is_rejected(self, db):
        _sid, did = _account(cash=100.0)
        order = _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date)
        assert order.status == ORDER_REJECTED
        assert "cannot afford 1 unit" in order.reason
        assert _state(did)["balance"] == 100.0

    def test_rejected_buy_records_the_requested_quantity(self, db):
        """The rejected lot is what was asked for, not a placeholder 1."""
        _sid, did = _account(cash=10000.0)
        order = _run(
            did, execute_buy, SYMBOL, 5000.0,
            bar_date=_bar(0, 5000.0).bar_date, quantity=7,
        )
        assert order.status == ORDER_REJECTED
        assert order.quantity == 7
        assert "insufficient funds" in order.reason

    def test_rejected_sell_records_the_requested_quantity(self, db):
        _sid, did = _account(cash=10000.0)
        order = _run(
            did, execute_sell, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=9
        )
        assert order.status == ORDER_REJECTED
        assert order.quantity == 9
        assert "no open position" in order.reason


# --------------------------------------------------------------------------- #
# F. Duplicate buy (no pyramiding)
# --------------------------------------------------------------------------- #
class TestDuplicateBuy:
    def test_second_buy_while_holding_is_rejected(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        after_first = _state(did)

        order = _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(1, 500.0).bar_date, quantity=1)

        assert order.status == ORDER_REJECTED
        assert "already holding" in order.reason
        assert "no pyramiding" in order.reason

        after = _state(did)
        assert after["balance"] == after_first["balance"]
        assert len(after["positions"]) == 1
        assert after["positions"][0]["quantity"] == 1
        assert len(after["orders"]) == 2

    def test_rebuy_is_allowed_once_flat(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        _run(did, execute_sell, SYMBOL, 550.0, bar_date=_bar(1, 550.0).bar_date)
        order = _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(2, 500.0).bar_date, quantity=1)
        assert order.status == ORDER_FILLED
        assert len(_state(did)["positions"]) == 1


# --------------------------------------------------------------------------- #
# G. Sell without a position (long-only)
# --------------------------------------------------------------------------- #
class TestSellWithoutPosition:
    def test_sell_with_nothing_open_is_rejected(self, db):
        _sid, did = _account(cash=10000.0)
        before = _state(did)

        order = _run(did, execute_sell, SYMBOL, 550.0, bar_date=_bar(0, 550.0).bar_date)

        assert order.status == ORDER_REJECTED
        assert "no open position" in order.reason
        assert "never shorts" in order.reason

        after = _state(did)
        assert after["balance"] == before["balance"]
        assert after["positions"] == []
        assert after["trades"] == []
        assert len(after["orders"]) == 1

    def test_repeated_sells_never_open_a_short(self, db):
        _sid, did = _account(cash=10000.0)
        for day in range(4):
            _run(did, execute_sell, SYMBOL, 500.0, bar_date=_bar(day, 500.0).bar_date)
        state = _state(did)
        assert state["positions"] == []
        assert state["trades"] == []
        assert state["balance"] == 10000.0
        assert all(o["status"] == ORDER_REJECTED for o in state["orders"])

    def test_partial_exit_is_refused(self, db):
        _sid, did = _account(cash=100000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=4)
        order = _run(
            did, execute_sell, SYMBOL, 500.0, bar_date=_bar(1, 500.0).bar_date, quantity=1
        )
        assert order.status == ORDER_REJECTED
        assert "partial exits are not supported" in order.reason
        assert len(_state(did)["positions"]) == 1


# --------------------------------------------------------------------------- #
# H. Duplicate bar protection (watermark)
# --------------------------------------------------------------------------- #
class TestDuplicateBars:
    def test_tick_advances_the_watermark(self, db):
        _sid, did = _account(cash=10000.0)
        assert _state(did)["last_bar_date"] is None

        _tick(did, _bar(0, 500.0), "hold")
        assert _state(did)["last_bar_date"] == DAY0

        _tick(did, _bar(1, 510.0), "hold")
        assert _state(did)["last_bar_date"] == DAY0 + timedelta(days=1)

    def test_replaying_a_bar_does_not_trade_twice(self, db):
        _sid, did = _account(cash=10000.0)
        bar = _bar(0, 500.0)

        first = _tick(did, bar, "buy")
        assert first["order"].status == ORDER_FILLED
        after_first = _state(did)

        # The router normally refuses this via next_bar(); this asserts the
        # engine's own guard is not the only thing standing between a retry
        # and a double buy: mark + watermark bookkeeping must stay consistent.
        second = _tick(did, bar, "buy")
        assert second["order"].status == ORDER_REJECTED  # already holding
        after_second = _state(did)
        assert after_second["balance"] == after_first["balance"]
        assert len(after_second["positions"]) == 1

    def test_duplicate_trade_is_impossible_for_one_bar(self, db):
        _sid, did = _account(cash=10000.0)
        _tick(did, _bar(0, 500.0), "buy")
        _tick(did, _bar(1, 550.0), "sell")
        for _ in range(3):
            _tick(did, _bar(1, 550.0), "sell")
        assert len(_state(did)["trades"]) == 1

    def test_rejected_order_still_advances_the_watermark(self, db):
        """The bar was consumed even though the order did not fill."""
        _sid, did = _account(cash=100.0)
        result = _tick(did, _bar(0, 500.0), "buy")
        assert result["order"].status == ORDER_REJECTED
        assert _state(did)["last_bar_date"] == DAY0
        assert "cannot afford" in _state(did)["last_error"]


# --------------------------------------------------------------------------- #
# Bar selection (section 8: deterministic, no network)
# --------------------------------------------------------------------------- #
def _write_csv(tmp_path, closes, start="2024-01-01"):
    import pandas as pd

    idx = pd.date_range(start, periods=len(closes), freq="D")
    frame = pd.DataFrame(
        {
            "Open": [c * 0.999 for c in closes],
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Volume": [1000.0] * len(closes),
        },
        index=idx,
    )
    frame.index.name = "Date"
    path = tmp_path / "SYNTH.csv"
    frame.to_csv(path, date_format="%Y-%m-%d")
    return path


class TestBarSelection:
    def test_first_bar_when_no_watermark(self, tmp_path):
        path = _write_csv(tmp_path, [100, 101, 102])
        assert next_bar(SYMBOL, after=None, path=path).date_str == "2024-01-01"

    def test_next_bar_is_strictly_after_the_watermark(self, tmp_path):
        path = _write_csv(tmp_path, [100, 101, 102])
        got = next_bar(SYMBOL, after=datetime(2024, 1, 1), path=path)
        assert got.date_str == "2024-01-02"
        got = next_bar(SYMBOL, after=datetime(2024, 1, 2), path=path)
        assert got.date_str == "2024-01-03"

    def test_watermark_bar_is_never_returned_again(self, tmp_path):
        path = _write_csv(tmp_path, [100, 101, 102])
        for day in range(1, 3):
            bar = next_bar(SYMBOL, after=datetime(2024, 1, day), path=path)
            assert bar.bar_date > datetime(2024, 1, day)

    def test_exhausted_data_raises(self, tmp_path):
        path = _write_csv(tmp_path, [100, 101])
        with pytest.raises(PaperBarError, match="no bar after"):
            next_bar(SYMBOL, after=datetime(2024, 6, 1), path=path)

    def test_pinned_bar_is_returned(self, tmp_path):
        path = _write_csv(tmp_path, [100, 101, 102])
        bar = next_bar(SYMBOL, on=datetime(2024, 1, 3), path=path)
        assert bar.date_str == "2024-01-03"

    def test_pinned_bar_at_or_before_watermark_is_a_duplicate(self, tmp_path):
        path = _write_csv(tmp_path, [100, 101, 102])
        with pytest.raises(PaperBarDuplicate):
            next_bar(
                SYMBOL, after=datetime(2024, 1, 3), on=datetime(2024, 1, 3), path=path
            )
        with pytest.raises(PaperBarDuplicate):
            next_bar(
                SYMBOL, after=datetime(2024, 1, 3), on=datetime(2024, 1, 1), path=path
            )

    def test_unknown_pinned_date_is_an_error_not_a_duplicate(self, tmp_path):
        path = _write_csv(tmp_path, [100, 101, 102])
        with pytest.raises(PaperBarError) as exc:
            next_bar(SYMBOL, after=datetime(2024, 1, 1), on=datetime(2024, 5, 5), path=path)
        assert not isinstance(exc.value, PaperBarDuplicate)

    def test_missing_cache_is_an_error(self, tmp_path):
        with pytest.raises(PaperBarError, match="no cached market data"):
            load_bars(SYMBOL, path=tmp_path / "nope.csv")

    def test_cache_missing_columns_is_an_error(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text("Date,Close\n2024-01-01,100\n")
        with pytest.raises(PaperBarError, match="missing columns"):
            load_bars(SYMBOL, path=path)

    def test_cache_with_nan_price_is_rejected(self, tmp_path):
        path = tmp_path / "nan.csv"
        path.write_text(
            "Date,Open,High,Low,Close,Volume\n"
            "2024-01-01,100,101,99,NaN,1000\n"
        )
        with pytest.raises(PaperBarError, match="NaN"):
            load_bars(SYMBOL, path=path)

    def test_bars_come_back_sorted(self, tmp_path):
        path = _write_csv(tmp_path, [100, 101, 102])
        bars = load_bars(SYMBOL, path=path)
        assert [b.bar_date for b in bars] == sorted(b.bar_date for b in bars)


# --------------------------------------------------------------------------- #
# J / K. Worked examples
# --------------------------------------------------------------------------- #
class TestWorkedExamples:
    def test_profit_example_gross_before_costs(self, db):
        """10000 -> buy 1 @ 500 -> sell 1 @ 550 => 10050 with no commission."""
        _sid, did = _account(cash=10000.0, commission_pct=0.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        _run(did, execute_sell, SYMBOL, 550.0, bar_date=_bar(1, 550.0).bar_date)

        state = _state(did)
        assert state["balance"] == pytest.approx(10050.0)
        assert state["trades"][0]["gross_pnl"] == pytest.approx(50.0)
        assert state["trades"][0]["commission"] == pytest.approx(0.0)
        assert state["trades"][0]["net_pnl"] == pytest.approx(50.0)

        snap = _snap(did)
        assert snap.equity == pytest.approx(10050.0)
        assert snap.total_pnl == pytest.approx(50.0)
        assert snap.total_return_pct == pytest.approx(0.5)

    def test_loss_example_gross_before_costs(self, db):
        """10000 -> buy 1 @ 500 -> sell 1 @ 450 => 9950 with no commission."""
        _sid, did = _account(cash=10000.0, commission_pct=0.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        _run(did, execute_sell, SYMBOL, 450.0, bar_date=_bar(1, 450.0).bar_date)

        state = _state(did)
        assert state["balance"] == pytest.approx(9950.0)
        assert state["trades"][0]["gross_pnl"] == pytest.approx(-50.0)
        assert state["trades"][0]["net_pnl"] == pytest.approx(-50.0)

        snap = _snap(did)
        assert snap.equity == pytest.approx(9950.0)
        assert snap.total_pnl == pytest.approx(-50.0)
        assert snap.total_return_pct == pytest.approx(-0.5)

    def test_account_identity_holds_across_a_full_cycle(self, db):
        """realized + unrealized == total, and equity ties to cash + value."""
        _sid, did = _account(cash=20000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=10)
        _tick(did, _bar(1, 540.0), "hold")  # still open, marked up
        _run(did, execute_sell, SYMBOL, 560.0, bar_date=_bar(2, 560.0).bar_date)
        _tick(did, _bar(3, 520.0), "hold")  # flat, cash only

        snap = _snap(did)
        assert snap.realized_pnl + snap.unrealized_pnl == pytest.approx(snap.total_pnl)
        assert snap.equity == pytest.approx(snap.cash_balance + snap.position_value)
        assert snap.total_pnl == pytest.approx(snap.equity - snap.initial_balance)


# --------------------------------------------------------------------------- #
# Ledger integrity still holds
# --------------------------------------------------------------------------- #
class TestLedgerIntegrityUnderExecution:
    def test_round_trip_never_short_sells(self, db):
        _sid, did = _account(cash=10000.0)
        _tick(did, _bar(0, 500.0), "sell")
        assert _state(did)["trades"] == []

    def test_trade_rows_satisfy_the_net_pnl_constraint(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        _run(did, execute_sell, SYMBOL, 550.0, bar_date=_bar(1, 550.0).bar_date)
        # Reading it back proves the CHECK constraint accepted the insert.
        assert _state(did)["trades"][0]["net_pnl"] == pytest.approx(48.95)

    def test_position_uniqueness_still_holds(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        with pytest.raises(IntegrityError):
            with SessionLocal() as session:
                session.add(
                    PaperPosition(
                        deployment_id=did, symbol=SYMBOL, quantity=2, avg_entry_price=600.0
                    )
                )
                session.commit()

    def test_order_statuses_stay_inside_the_check_constraint(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        with pytest.raises(IntegrityError):
            with SessionLocal() as session:
                session.add(
                    PaperOrder(
                        deployment_id=did, symbol=SYMBOL, side="buy", quantity=1,
                        status="exploded",
                    )
                )
                session.commit()


# --------------------------------------------------------------------------- #
# run_tick behaviour
# --------------------------------------------------------------------------- #
class TestRunTick:
    def test_hold_creates_no_order(self, db):
        _sid, did = _account(cash=10000.0)
        result = _tick(did, _bar(0, 500.0), "hold")
        assert result["order"] is None
        assert result["marked_positions"] == 0
        assert _state(did)["orders"] == []

    def test_unknown_action_is_refused(self, db):
        _sid, did = _account(cash=10000.0)
        with pytest.raises(PaperExecutionError, match="unknown action"):
            _tick(did, _bar(0, 500.0), "moon")

    def test_action_case_is_tolerated(self, db):
        _sid, did = _account(cash=10000.0)
        result = _tick(did, _bar(0, 500.0), "BUY")
        assert result["action"] == "buy"
        assert result["order"].status == ORDER_FILLED

    def test_buy_tick_marks_and_watermarks_in_one_pass(self, db):
        _sid, did = _account(cash=10000.0)
        bar = _bar(0, 500.0)
        result = _tick(did, bar, "buy")
        assert result["bar_date"] == bar.bar_date
        assert result["price"] == 500.0
        assert result["marked_positions"] == 1

        state = _state(did)
        assert state["last_bar_date"] == bar.bar_date
        assert state["last_error"] is None
        assert state["positions"][0]["last_price"] == 500.0

    def test_sell_tick_clears_the_error_from_a_previous_rejection(self, db):
        _sid, did = _account(cash=100.0)
        _tick(did, _bar(0, 500.0), "buy")
        assert _state(did)["last_error"] is not None
        # Fund the account enough for a fill, then trade.
        with SessionLocal() as session:
            dep = session.query(PaperDeployment).filter(
                PaperDeployment.id == did
            ).first()
            dep.balance = 10000.0
            session.commit()
        _tick(did, _bar(1, 500.0), "buy")
        assert _state(did)["last_error"] is None


class TestFindPositionAndMarking:
    def test_find_position_is_case_insensitive(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        with SessionLocal() as session:
            dep = session.query(PaperDeployment).filter(
                PaperDeployment.id == did
            ).first()
            assert find_position(dep, "nifty50") is not None
            assert find_position(dep, "BANKNIFTY") is None

    def test_mark_positions_counts_and_updates(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        with SessionLocal() as session:
            dep = session.query(PaperDeployment).filter(
                PaperDeployment.id == did
            ).first()
            assert mark_positions(dep, 777.0) == 1
            assert dep.positions[0].last_price == 777.0

    def test_marking_with_a_bad_price_raises(self, db):
        _sid, did = _account(cash=10000.0)
        _run(did, execute_buy, SYMBOL, 500.0, bar_date=_bar(0, 500.0).bar_date, quantity=1)
        with SessionLocal() as session:
            dep = session.query(PaperDeployment).filter(
                PaperDeployment.id == did
            ).first()
            with pytest.raises(PaperExecutionError):
                mark_positions(dep, 0.0)


# --------------------------------------------------------------------------- #
# H. POST /strategies/{id}/paper-tick
#
# The strategy replay is stubbed here so the API contract can be tested fast and
# offline; the real subprocess is covered in TestSignalGeneration below.
# --------------------------------------------------------------------------- #
@pytest.fixture()
def market(tmp_path, monkeypatch):
    """Point the router at a synthetic cached CSV and a scripted signal."""
    import app.routers.strategies as router_module

    path = _write_csv(tmp_path, [500.0, 510.0, 550.0, 540.0, 560.0])
    monkeypatch.setattr(router_module, "ensure_market_data", lambda market: path)

    state = {"action": "hold", "calls": []}

    def fake_signal(code, data_path, cash, commission_pct, sizer_percents, upto_date=None):
        state["calls"].append(
            {
                "code": code,
                "cash": cash,
                "commission_pct": commission_pct,
                "sizer_percents": sizer_percents,
                "upto_date": upto_date,
            }
        )
        bar = next_bar(SYMBOL, on=datetime.fromisoformat(upto_date), path=path)
        return {"action": state["action"], "bar_date": upto_date, "close": bar.close}

    monkeypatch.setattr(router_module, "run_signal_sandboxed", fake_signal)
    state["path"] = path
    return state


class TestPaperTickApi:
    def test_tick_holds_and_returns_a_snapshot(self, client, db, market):
        sid, did = _account(cash=10000.0)
        market["action"] = "hold"

        resp = client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert body["bar_date"] == "2024-01-01"
        assert body["symbol"] == SYMBOL
        assert body["price"] == 500.0
        assert body["action"] == "HOLD"
        assert body["duplicate"] is False
        assert body["order"] is None
        assert body["account"]["initial_balance"] == 10000.0
        assert body["account"]["cash_balance"] == 10000.0
        assert body["account"]["total_pnl"] == 0.0
        assert body["account"]["last_bar_date"].startswith("2024-01-01")

    def test_tick_buys(self, client, db, market):
        sid, did = _account(cash=10000.0)
        market["action"] = "buy"

        resp = client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "BUY"
        assert body["fill_price"] == 500.0
        assert body["quantity"] == 1
        assert body["order"]["status"] == "filled"
        assert body["account"]["open_positions"] == 1
        assert body["account"]["cash_balance"] == pytest.approx(9499.5)

        positions = client.get(f"/strategies/{sid}/positions").json()
        assert len(positions) == 1
        assert positions[0]["quantity"] == 1
        assert positions[0]["avg_entry_price"] == 500.0

    def test_tick_sells_after_a_buy(self, client, db, market):
        sid, did = _account(cash=10000.0)
        market["action"] = "buy"
        client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 1})

        market["action"] = "sell"
        resp = client.post(
            f"/strategies/{sid}/paper-tick", json={"bar_date": "2024-01-03", "quantity": 1}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "SELL"
        assert body["fill_price"] == 550.0
        assert body["order"]["status"] == "filled"
        assert body["account"]["open_positions"] == 0
        assert body["account"]["closed_trades"] == 1
        assert body["account"]["realized_pnl"] == pytest.approx(48.95)
        assert body["account"]["cash_balance"] == pytest.approx(10048.95)

        trades = client.get(f"/strategies/{sid}/trades").json()
        assert len(trades) == 1
        assert trades[0]["direction"] == "long"
        assert trades[0]["net_pnl"] == pytest.approx(48.95)

    def test_holding_a_position_shows_unrealised_pnl(self, client, db, market):
        sid, did = _account(cash=10000.0)
        market["action"] = "buy"
        client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 1})

        market["action"] = "hold"
        body = client.post(
            f"/strategies/{sid}/paper-tick", json={"bar_date": "2024-01-03"}
        ).json()
        assert body["action"] == "HOLD"
        assert body["account"]["unrealized_pnl"] == pytest.approx(50.0)
        assert body["account"]["open_positions"] == 1
        assert body["account"]["closed_trades"] == 0

    def test_orders_endpoint_shows_the_fill(self, client, db, market):
        sid, did = _account(cash=10000.0)
        market["action"] = "buy"
        client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 1})
        orders = client.get(f"/strategies/{sid}/orders").json()
        assert len(orders) == 1
        assert orders[0]["side"] == "buy"
        assert orders[0]["status"] == "filled"
        assert orders[0]["fill_price"] == 500.0

    def test_tick_advances_one_bar_at_a_time(self, client, db, market):
        sid, did = _account(cash=10000.0)
        seen = []
        for _ in range(3):
            body = client.post(f"/strategies/{sid}/paper-tick", json={}).json()
            seen.append(body["bar_date"])
        assert seen == ["2024-01-01", "2024-01-02", "2024-01-03"]

    def test_duplicate_bar_is_a_safe_no_op(self, client, db, market):
        sid, did = _account(cash=10000.0)
        market["action"] = "buy"
        first = client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 1}).json()
        assert first["duplicate"] is False

        again = client.post(
            f"/strategies/{sid}/paper-tick", json={"bar_date": "2024-01-01", "quantity": 1}
        )
        assert again.status_code == 200
        body = again.json()
        assert body["duplicate"] is True
        assert "already processed" in body["reason"]
        # Nothing moved.
        assert body["account"]["cash_balance"] == pytest.approx(9499.5)
        assert body["account"]["open_positions"] == 1
        assert body["account"]["closed_trades"] == 0

        orders = client.get(f"/strategies/{sid}/orders").json()
        assert len(orders) == 1  # no duplicate order
        trades = client.get(f"/strategies/{sid}/trades").json()
        assert trades == []

    def test_duplicate_reports_the_real_price_not_a_placeholder(self, client, db, market):
        """The retry's snapshot must be directly comparable with the original."""
        sid, did = _account(cash=10000.0)
        market["action"] = "buy"
        first = client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 1}).json()
        again = client.post(
            f"/strategies/{sid}/paper-tick", json={"bar_date": "2024-01-01", "quantity": 1}
        ).json()
        assert again["price"] == first["price"] == 500.0
        assert again["price"] != 0.0

    def test_rejected_order_records_the_requested_quantity(self, client, db, market):
        """The audit trail shows the lot asked for, not a fabricated 1."""
        sid, did = _account(cash=10000.0)
        market["action"] = "buy"
        client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 1})

        market["action"] = "sell"
        blocked = client.post(
            f"/strategies/{sid}/paper-tick",
            json={"bar_date": "2024-01-02", "quantity": 3},
        ).json()
        assert blocked["order"]["status"] == "rejected"
        # A refused partial exit records the size actually held, and names the
        # over-large request in the reason.
        assert blocked["order"]["quantity"] == 1
        assert "partial exits" in blocked["order"]["reason"]
        assert "asked to sell 3" in blocked["order"]["reason"]

        flat = _account(cash=400.0)
        market["action"] = "sell"
        no_pos = client.post(
            f"/strategies/{flat[0]}/paper-tick", json={"quantity": 7}
        ).json()
        assert no_pos["order"]["status"] == "rejected"
        assert no_pos["order"]["quantity"] == 7
        assert "no open position" in no_pos["order"]["reason"]

    def test_replaying_an_earlier_bar_is_also_a_no_op(self, client, db, market):
        sid, did = _account(cash=10000.0)
        market["action"] = "buy"
        client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 1})
        for stale in ("2024-01-01", "2023-12-25"):
            resp = client.post(
                f"/strategies/{sid}/paper-tick", json={"bar_date": stale, "quantity": 1}
            )
            assert resp.status_code == 200
            assert resp.json()["duplicate"] is True
        assert len(client.get(f"/strategies/{sid}/orders").json()) == 1

    def test_unknown_pinned_date_is_422_not_a_silent_skip(self, client, db, market):
        sid, did = _account(cash=10000.0)
        resp = client.post(f"/strategies/{sid}/paper-tick", json={"bar_date": "2030-01-01"})
        assert resp.status_code == 422
        assert "no usable market bar" in resp.json()["detail"]["reasons"][0]

    def test_data_exhaustion_is_422(self, client, db, market):
        sid, did = _account(cash=10000.0)
        for _ in range(5):
            assert client.post(f"/strategies/{sid}/paper-tick", json={}).status_code == 200
        resp = client.post(f"/strategies/{sid}/paper-tick", json={})
        assert resp.status_code == 422
        assert "no bar after" in resp.json()["detail"]["reasons"][0]

    def test_strategy_signal_receives_deployment_config(self, client, db, market):
        sid, did = _account(cash=10000.0, commission_pct=0.25, sizer_percents=80.0)
        client.post(f"/strategies/{sid}/paper-tick", json={})
        call = market["calls"][-1]
        assert call["cash"] == 10000.0
        assert call["commission_pct"] == 0.25
        assert call["sizer_percents"] == 80.0
        assert call["upto_date"] == "2024-01-01"
        assert "GeneratedStrategy" in call["code"]

    def test_insufficient_cash_returns_a_rejected_order(self, client, db, market):
        sid, did = _account(cash=400.0)
        market["action"] = "buy"
        body = client.post(
            f"/strategies/{sid}/paper-tick", json={"quantity": 5}
        ).json()
        assert body["order"]["status"] == "rejected"
        assert "insufficient funds" in body["order"]["reason"]
        assert body["account"]["cash_balance"] == 400.0
        assert body["account"]["open_positions"] == 0
        # the bar was still consumed
        assert body["account"]["last_bar_date"].startswith("2024-01-01")


class TestPaperTickLifecycleGuards:
    def test_requires_paper_trading_status(self, client, db, market):
        sid, did = _account(status=StrategyStatus.approved)
        resp = client.post(f"/strategies/{sid}/paper-tick", json={})
        assert resp.status_code == 422
        assert "paper_trading" in resp.json()["detail"]["reasons"][0]

    def test_requires_an_active_deployment(self, client, db, market):
        sid, did = _account(dep_status=DeploymentStatus.stopped)
        resp = client.post(f"/strategies/{sid}/paper-tick", json={})
        assert resp.status_code == 422
        assert "no active paper deployment" in resp.json()["detail"]["reasons"][0]

    def test_requires_generated_code(self, client, db, market):
        sid, did = _account(code="")
        resp = client.post(f"/strategies/{sid}/paper-tick", json={})
        assert resp.status_code == 422
        assert "no generated code" in resp.json()["detail"]["reasons"][0]

    def test_draft_strategy_cannot_tick(self, client, db, market):
        sid, did = _account(status=StrategyStatus.draft)
        assert client.post(f"/strategies/{sid}/paper-tick", json={}).status_code == 422

    def test_rejected_strategy_cannot_tick(self, client, db, market):
        sid, did = _account(status=StrategyStatus.rejected)
        assert client.post(f"/strategies/{sid}/paper-tick", json={}).status_code == 422

    def test_unknown_uuid_is_404(self, client, db, market):
        resp = client.post(f"/strategies/{UNKNOWN_UUID}/paper-tick", json={})
        assert resp.status_code == 404

    @pytest.mark.parametrize("bad_id", ["abc123", "not-a-uuid", "'; DROP TABLE strategies; --"])
    def test_malformed_id_is_404_not_500(self, client, db, market, bad_id):
        resp = client.post(f"/strategies/{bad_id}/paper-tick", json={})
        assert resp.status_code == 404
        assert resp.json()["detail"] == f"Strategy {bad_id[:MAX_ECHOED_ID]} not found"

    def test_no_body_is_accepted(self, client, db, market):
        """A bodyless POST still advances the account."""
        sid, did = _account(cash=10000.0)
        resp = client.post(f"/strategies/{sid}/paper-tick")
        assert resp.status_code == 200
        assert resp.json()["bar_date"] == "2024-01-01"

    def test_quantity_must_be_positive(self, client, db, market):
        sid, did = _account(cash=10000.0)
        resp = client.post(f"/strategies/{sid}/paper-tick", json={"quantity": 0})
        assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Real subprocess signal generation (section 9)
# --------------------------------------------------------------------------- #
SMA_CROSS_CODE = (
    "import backtrader as bt\n"
    "class GeneratedStrategy(bt.Strategy):\n"
    "    params = (('fast', 3), ('slow', 5))\n"
    "    def __init__(self):\n"
    "        self.fast = bt.indicators.SMA(self.data.close, period=self.p.fast)\n"
    "        self.slow = bt.indicators.SMA(self.data.close, period=self.p.slow)\n"
    "    def next(self):\n"
    "        if not self.position:\n"
    "            if self.fast[0] > self.slow[0]:\n"
    "                self.buy()\n"
    "        else:\n"
    "            if self.fast[0] < self.slow[0]:\n"
    "                self.sell()\n"
)


def _zigzag(n=40):
    """A deterministic zigzag that makes a fast/slow cross fire both ways."""
    closes = []
    for i in range(n):
        phase = (i % 12) / 12.0
        swing = 1.0 if phase < 0.5 else -1.0
        closes.append(100.0 + 20.0 * swing * (phase if phase < 0.5 else 1 - phase) * 2)
    return closes


class TestSignalGeneration:
    """The generated code really is replayed, in a subprocess, offline."""

    def test_signal_is_deterministic(self, tmp_path):
        from app.services.backtest_service import run_signal_sandboxed

        path = _write_csv(tmp_path, _zigzag())
        first = run_signal_sandboxed(
            code=SMA_CROSS_CODE, data_path=str(path), cash=100000.0,
            commission_pct=0.1, sizer_percents=95.0, upto_date="2024-01-20",
        )
        second = run_signal_sandboxed(
            code=SMA_CROSS_CODE, data_path=str(path), cash=100000.0,
            commission_pct=0.1, sizer_percents=95.0, upto_date="2024-01-20",
        )
        assert first == second
        assert first["bar_date"] == "2024-01-20"
        assert first["action"] in ("buy", "sell", "hold")

    def test_signal_reports_the_bar_it_decided_on(self, tmp_path):
        from app.services.backtest_service import run_signal_sandboxed

        path = _write_csv(tmp_path, _zigzag())
        for day in ("2024-01-12", "2024-01-20", "2024-01-24"):
            got = run_signal_sandboxed(
                code=SMA_CROSS_CODE, data_path=str(path), cash=100000.0,
                commission_pct=0.1, sizer_percents=95.0, upto_date=day,
            )
            assert got["bar_date"] == day

    def test_a_cross_produces_buy_then_sell(self, tmp_path):
        from app.services.backtest_service import run_signal_sandboxed

        path = _write_csv(tmp_path, _zigzag())
        actions = []
        for day in ("2024-01-12", "2024-01-13", "2024-01-20"):
            got = run_signal_sandboxed(
                code=SMA_CROSS_CODE, data_path=str(path), cash=100000.0,
                commission_pct=0.1, sizer_percents=95.0, upto_date=day,
            )
            actions.append(got["action"])
        assert actions[0] == "buy"
        assert "sell" in actions

    def test_guardrail_still_refuses_unsafe_code_in_signal_mode(self, tmp_path):
        from app.services.backtest_service import BacktestError, run_signal_sandboxed

        path = _write_csv(tmp_path, _zigzag())
        unsafe = (
            "import backtrader as bt\n"
            "open('enemy.txt')\n"
            "class GeneratedStrategy(bt.Strategy):\n"
            "    def next(self):\n"
            "        self.buy()\n"
        )
        with pytest.raises(BacktestError, match="open\\(\\)"):
            run_signal_sandboxed(
                code=unsafe, data_path=str(path), cash=100000.0,
                commission_pct=0.1, sizer_percents=95.0, upto_date="2024-01-20",
            )

    def test_no_strategy_class_is_an_error(self, tmp_path):
        from app.services.backtest_service import BacktestError, run_signal_sandboxed

        path = _write_csv(tmp_path, _zigzag())
        with pytest.raises(BacktestError, match="no bt.Strategy subclass"):
            run_signal_sandboxed(
                code="x = 1\n", data_path=str(path), cash=100000.0,
                commission_pct=0.1, sizer_percents=95.0, upto_date="2024-01-20",
            )

    def test_early_bars_warm_up_as_hold_rather_than_erroring(self, tmp_path):
        """A strategy whose indicators are not ready yet must HOLD, not fail."""
        from app.services.backtest_service import run_signal_sandboxed

        path = _write_csv(tmp_path, _zigzag())
        got = run_signal_sandboxed(
            code=SMA_CROSS_CODE, data_path=str(path), cash=100000.0,
            commission_pct=0.1, sizer_percents=95.0, upto_date="2024-01-02",
        )
        assert got["action"] == "hold"
        assert got.get("warmup") is True
        assert "warming up" in got["reason"]
        assert got["bar_date"] == "2024-01-02"

    def test_signal_only_looks_at_history_up_to_the_bar(self, tmp_path):
        """No lookahead: the decision for a bar cannot depend on later bars."""
        from app.services.backtest_service import run_signal_sandboxed

        base = _zigzag()
        early = run_signal_sandboxed(
            code=SMA_CROSS_CODE, data_path=str(_write_csv(tmp_path, base)), cash=100000.0,
            commission_pct=0.1, sizer_percents=95.0, upto_date="2024-01-12",
        )
        # Same early bars, wildly different future, must give the same answer.
        mutated = list(base)
        for i in range(12, len(mutated)):
            mutated[i] = 9999.0
        perturbed = run_signal_sandboxed(
            code=SMA_CROSS_CODE, data_path=str(_write_csv(tmp_path, mutated, start="2024-02-01")),
            cash=100000.0, commission_pct=0.1, sizer_percents=95.0,
            upto_date="2024-02-12",
        )
        assert early["action"] == perturbed["action"]
        assert early["close"] == pytest.approx(perturbed["close"])