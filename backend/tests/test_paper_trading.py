"""Tests for simulated paper trading (no broker, no real money).

Pure-engine tests run everywhere. The SQLite end-to-end flow overrides the
``get_db`` dependency so it also runs without Postgres; it drives the real
HTTP endpoints (deploy -> paper-tick -> account/positions/orders/trades/
market-bars) with the real sandboxed worker on tiny data slices.
"""
import csv
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Conversation, Strategy, StrategyStatus, User
from app.services import paper_bars, paper_engine
from app.services.paper_bars import PaperBarsError
from app.services.paper_engine import (
    OrderRejected,
    account_snapshot,
    compute_buy_fill,
    compute_sell_fill,
    map_signal,
)

# --------------------------------------------------------------------------- #
# Pure signal mapping: (strategy replay state, stored position) -> decision
# --------------------------------------------------------------------------- #
class TestMapSignal:
    def test_flat_strategy_flat_account_holds(self):
        assert map_signal(False, False) == ("HOLD", "HOLD")

    def test_long_replay_flat_account_buys(self):
        assert map_signal(True, False) == ("BUY", "BUY")

    def test_long_replay_open_position_holds(self):
        # One open position per deployment: never pyramid.
        assert map_signal(True, True) == ("BUY", "HOLD")

    def test_flat_replay_open_position_sells(self):
        assert map_signal(False, True) == ("SELL", "SELL")


# --------------------------------------------------------------------------- #
# Fill math
# --------------------------------------------------------------------------- #
class TestBuyFill:
    def test_sizes_like_percent_sizer(self):
        fill = compute_buy_fill(
            close=100.0, cash_balance=100000.0,
            commission_pct=0.1, sizer_percents=95.0,
        )
        # 95% of 100k = 95000; one unit costs 100.10 incl. commission.
        assert fill["quantity"] == int(95000 // 100.10)
        assert fill["price"] == 100.0
        assert fill["commission"] == pytest.approx(fill["quantity"] * 0.10)
        assert fill["cost"] == pytest.approx(fill["quantity"] * 100.0 + fill["commission"])

    def test_integer_quantities_only(self):
        fill = compute_buy_fill(
            close=33.33, cash_balance=1000.0,
            commission_pct=0.1, sizer_percents=95.0,
        )
        assert isinstance(fill["quantity"], int)

    def test_insufficient_cash_rejects_without_leverage(self):
        with pytest.raises(OrderRejected):
            compute_buy_fill(
                close=25000.0, cash_balance=100.0,
                commission_pct=0.1, sizer_percents=95.0,
            )

    def test_untradeable_close_rejects(self):
        with pytest.raises(OrderRejected):
            compute_buy_fill(
                close=0.0, cash_balance=100000.0,
                commission_pct=0.1, sizer_percents=95.0,
            )


class FakePosition:
    def __init__(self, quantity, avg_price):
        self.quantity = quantity
        self.avg_price = avg_price


class TestSellFill:
    def test_round_trip_pnl_net_of_both_commissions(self):
        fill = compute_sell_fill(110.0, FakePosition(10, 100.0), 0.1)
        assert fill["quantity"] == 10
        assert fill["price"] == 110.0
        assert fill["pnl"] == pytest.approx(100.0)  # gross
        # Net = gross - entry commission (10*100*0.001) - exit (10*110*0.001).
        assert fill["pnl_net"] == pytest.approx(100.0 - 1.0 - 1.1)
        assert fill["proceeds"] == pytest.approx(1100.0 - 1.1)

    def test_loss_math(self):
        fill = compute_sell_fill(90.0, FakePosition(10, 100.0), 0.1)
        assert fill["pnl"] == pytest.approx(-100.0)
        assert fill["pnl_net"] == pytest.approx(-100.0 - 1.0 - 0.9)


class FakeDeployment:
    def __init__(self, **kwargs):
        self.id = "dep-1"
        self.strategy_id = "strat-1"
        self.cash = kwargs.get("cash", 100000.0)
        self.cash_balance = kwargs.get("cash_balance", 100000.0)
        self.realized_pnl = kwargs.get("realized_pnl", 0.0)
        self.last_bar_date = kwargs.get("last_bar_date")
        self.last_error = kwargs.get("last_error")
        self.deployed_at = None
        self.stopped_at = None
        from app.models import DeploymentStatus
        self.status = kwargs.get("status", DeploymentStatus.active)


class TestSnapshot:
    def test_equity_splits_cash_and_unrealized(self):
        dep = FakeDeployment(cash_balance=90000.0, realized_pnl=500.0)
        snap = account_snapshot(
            dep, [FakePosition(10, 100.0)], completed_trades=2, last_close=110.0
        )
        assert snap["starting_cash"] == 100000.0
        assert snap["cash_balance"] == 90000.0
        assert snap["unrealized_pnl"] == pytest.approx(100.0)
        assert snap["equity"] == pytest.approx(90100.0)
        assert snap["total_pnl"] == pytest.approx(-9900.0)
        assert snap["return_pct"] == pytest.approx(-9.9)
        assert snap["open_positions"] == 1
        assert snap["completed_trades"] == 2

    def test_unknown_price_leaves_unrealized_null(self):
        snap = account_snapshot(FakeDeployment(), [], 0, None)
        assert snap["unrealized_pnl"] is None
        assert snap["equity"] == 100000.0

    def test_null_balance_reads_as_untouched_starting_cash(self):
        dep = FakeDeployment(cash_balance=None, realized_pnl=None)
        snap = account_snapshot(dep, [], 0, None)
        assert snap["cash_balance"] == 100000.0
        assert snap["realized_pnl"] == 0.0


# --------------------------------------------------------------------------- #
# Bar selection + cache loading
# --------------------------------------------------------------------------- #
BARS = [
    {"date": "2024-10-03", "open": 1, "high": 1, "low": 1, "close": 10, "volume": 1},
    {"date": "2024-10-04", "open": 1, "high": 1, "low": 1, "close": 11, "volume": 1},
    {"date": "2024-10-07", "open": 1, "high": 1, "low": 1, "close": 12, "volume": 1},
]


class TestSelectNextBar:
    def test_first_tick_takes_oldest_bar(self):
        assert paper_bars.select_next_bar(BARS, None)["date"] == "2024-10-03"

    def test_advances_past_watermark(self):
        assert paper_bars.select_next_bar(BARS, "2024-10-03")["date"] == "2024-10-04"

    def test_exhausted_data_raises(self):
        with pytest.raises(PaperBarsError):
            paper_bars.select_next_bar(BARS, "2024-10-07")

    def test_requested_date_must_exist(self):
        with pytest.raises(PaperBarsError):
            paper_bars.select_next_bar(BARS, None, "1999-01-01")

    def test_requested_date_cannot_replay_watermark(self):
        with pytest.raises(PaperBarsError):
            paper_bars.select_next_bar(BARS, "2024-10-04", "2024-10-03")

    def test_requested_date_after_watermark_ok(self):
        bar = paper_bars.select_next_bar(BARS, "2024-10-03", "2024-10-04")
        assert bar["date"] == "2024-10-04"

    def test_requested_date_skipping_next_bar_rejected(self):
        with pytest.raises(PaperBarsError, match="next unprocessed market bar"):
            paper_bars.select_next_bar(BARS, "2024-10-03", "2024-10-07")


class TestLoadBars:
    def test_reads_real_cached_nifty_data(self):
        bars = paper_bars.load_bars("NIFTY50")
        assert len(bars) > 100
        first, last = bars[0], bars[-1]
        assert first["date"] < last["date"]  # oldest first
        for key in ("open", "high", "low", "close"):
            assert isinstance(first[key], float)

    def test_missing_market_raises_instead_of_fabricating(self):
        with pytest.raises(PaperBarsError):
            paper_bars.load_bars("NO_SUCH_MARKET_XYZ")

    def test_processed_bars_respects_watermark(self):
        assert paper_bars.processed_bars(BARS, None) == []
        assert [b["date"] for b in paper_bars.processed_bars(BARS, "2024-10-04")] == [
            "2024-10-03",
            "2024-10-04",
        ]


# --------------------------------------------------------------------------- #
# Worker integration: the replay slice must report its end-of-run position.
# --------------------------------------------------------------------------- #
BUY_AND_HOLD_CODE = (
    "import backtrader as bt\n"
    "class GeneratedStrategy(bt.Strategy):\n"
    "    def next(self):\n"
    "        if not self.position:\n"
    "            self.buy(exectype=bt.Order.Close)\n"
)

FLAT_CODE = (
    "import backtrader as bt\n"
    "class GeneratedStrategy(bt.Strategy):\n"
    "    def next(self):\n"
    "        pass\n"
)


def _slice_csv(rows: int) -> str:
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", prefix="paper_test_", delete=False, newline=""
    )
    writer = csv.DictWriter(
        handle, fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"]
    )
    writer.writeheader()
    price = 100.0
    for day in range(1, rows + 1):
        price += 1.0
        writer.writerow(
            {
                "Date": f"2024-01-{day:02d}",
                "Open": price, "High": price + 1,
                "Low": price - 1, "Close": price, "Volume": 1000,
            }
        )
    handle.close()
    return handle.name


class TestSliceSignal:
    def test_buy_strategy_reports_open_position(self):
        from app.services.strategy_runner import run_backtest

        path = _slice_csv(5)
        try:
            metrics = run_backtest(
                BUY_AND_HOLD_CODE, path, cash=100000.0,
                commission_pct=0.1, sizer_percents=95.0,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        assert metrics["open_position"] is not None
        assert metrics["open_position"]["size"] > 0

    def test_flat_strategy_reports_no_open_position(self):
        from app.services.strategy_runner import run_backtest

        path = _slice_csv(5)
        try:
            metrics = run_backtest(
                FLAT_CODE, path, cash=100000.0,
                commission_pct=0.1, sizer_percents=95.0,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        assert metrics["open_position"] is None


# --------------------------------------------------------------------------- #
# SQLite end-to-end: deploy -> tick x4 -> BUY, HOLD, SELL + ledger + chart data
# --------------------------------------------------------------------------- #
ROUND_TRIP_CODE = (
    "import backtrader as bt\n"
    "class GeneratedStrategy(bt.Strategy):\n"
    "    def next(self):\n"
    "        if len(self) == 1:\n"
    "            self.buy(exectype=bt.Order.Close)\n"
    "        elif len(self) >= 4:\n"
    "            self.close(exectype=bt.Order.Close)\n"
)


@pytest.fixture()
def sqlite_client(tmp_path, monkeypatch):
    """File-backed SQLite app with seeded approved strategy; no Postgres needed."""
    db_path = tmp_path / "paper_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    def override():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    try:
        session = session_factory()
        user = User(email="paper@local")
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
            description="sqlite e2e",
            market="NIFTY50",
            generated_code=ROUND_TRIP_CODE,
            status=StrategyStatus.approved,
        )
        session.add(strat)
        session.commit()
        session.refresh(strat)
        strategy_id = strat.id
        session.close()
        yield client, strategy_id
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _tick(client, strategy_id, body=None):
    resp = client.post(f"/strategies/{strategy_id}/paper-tick", json=body or {})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestPaperFlowSQLite:
    def test_deploy_initializes_virtual_account(self, sqlite_client):
        client, strategy_id = sqlite_client
        resp = client.post(
            f"/strategies/{strategy_id}/deploy",
            json={"cash": 100000.0, "commission_pct": 0.1, "sizer_percents": 95.0},
        )
        assert resp.status_code == 200, resp.text
        account = client.get(f"/strategies/{strategy_id}/paper-account").json()
        assert account["starting_cash"] == 100000.0
        assert account["cash_balance"] == 100000.0
        assert account["equity"] == 100000.0
        assert account["open_positions"] == 0
        assert account["completed_trades"] == 0
        assert account["last_bar_date"] is None

    def test_tick_without_deployment_refuses(self, sqlite_client):
        client, strategy_id = sqlite_client
        resp = client.post(f"/strategies/{strategy_id}/paper-tick", json={})
        assert resp.status_code == 422

    def test_full_round_trip(self, sqlite_client):
        client, strategy_id = sqlite_client
        client.post(
            f"/strategies/{strategy_id}/deploy",
            json={"cash": 100000.0, "commission_pct": 0.1, "sizer_percents": 95.0},
        )

        warmup = _tick(client, strategy_id)
        assert warmup["action"] == "HOLD"  # single-bar slice: no signal possible
        assert warmup["order_id"] is None

        buy = _tick(client, strategy_id)
        assert buy["signal"] == "BUY"
        assert buy["action"] == "BUY"
        assert buy["order_status"] == "filled"
        assert buy["quantity"] > 0

        positions = client.get(f"/strategies/{strategy_id}/paper-positions").json()
        assert len(positions) == 1
        assert positions[0]["quantity"] == buy["quantity"]
        assert positions[0]["entry_date"] == buy["bar_date"]

        hold = _tick(client, strategy_id)
        assert hold["action"] == "HOLD"  # one open position: never pyramid
        assert hold["order_id"] is None

        # Backtrader fills Close orders on the NEXT bar, so the exit placed
        # on slice-bar 4 only shows as flat in the 5-bar replay.
        still_holding = _tick(client, strategy_id)
        assert still_holding["action"] == "HOLD"

        sell = _tick(client, strategy_id)
        assert sell["signal"] == "SELL"
        assert sell["action"] == "SELL"
        assert sell["trade_id"] is not None
        assert sell["pnl_net"] is not None

        trades = client.get(f"/strategies/{strategy_id}/paper-trades").json()
        assert len(trades) == 1
        assert trades[0]["pnl_net"] == pytest.approx(sell["pnl_net"])
        assert trades[0]["entry_date"] == buy["bar_date"]
        assert trades[0]["exit_date"] == sell["bar_date"]

        orders = client.get(f"/strategies/{strategy_id}/paper-orders").json()
        filled = [o for o in orders if o["status"] == "filled"]
        assert len(filled) == 2
        assert {o["side"] for o in filled} == {"BUY", "SELL"}

        account = client.get(f"/strategies/{strategy_id}/paper-account").json()
        assert account["open_positions"] == 0
        assert account["completed_trades"] == 1
        assert account["realized_pnl"] == pytest.approx(sell["pnl_net"])
        assert account["last_bar_date"] == sell["bar_date"]

        bars = client.get(f"/strategies/{strategy_id}/market-bars").json()
        assert bars["last_bar_date"] == sell["bar_date"]
        assert [b["date"] for b in bars["bars"]] == sorted(b["date"] for b in bars["bars"])
        assert bars["bars"][-1]["date"] == sell["bar_date"]
        assert bars["bars"][0]["date"] <= buy["bar_date"]

        hub = client.get("/paper/deployments").json()
        assert len(hub) == 1
        assert hub[0]["strategy_id"] == strategy_id
        assert hub[0]["completed_trades"] == 1

    def test_rejected_buy_stays_visible_without_marker(
        self, sqlite_client, monkeypatch
    ):
        # Force a BUY signal while the virtual account cannot afford one
        # NIFTY unit: the rejected order must persist visibly, with no
        # position, no trade, and no chart marker.
        import app.services.paper_engine as engine_module

        def fake_replay(**kwargs):
            return {"open_position": {"size": 5, "price": 25000.0}}

        monkeypatch.setattr(engine_module, "run_backtest_sandboxed", fake_replay)
        client, strategy_id = sqlite_client
        # Tiny cash: even one NIFTY unit is unaffordable -> rejected BUY order.
        client.post(
            f"/strategies/{strategy_id}/deploy",
            json={"cash": 10.0, "commission_pct": 0.1, "sizer_percents": 95.0},
        )
        _tick(client, strategy_id)  # warmup
        rejected = _tick(client, strategy_id)
        assert rejected["signal"] == "BUY"
        assert rejected["action"] == "HOLD"
        assert rejected["order_status"] == "rejected"
        orders = client.get(f"/strategies/{strategy_id}/paper-orders").json()
        assert len(orders) == 1
        assert orders[0]["status"] == "rejected"
        assert client.get(f"/strategies/{strategy_id}/paper-positions").json() == []
        assert client.get(f"/strategies/{strategy_id}/paper-trades").json() == []

    def test_state_survives_client_refresh(self, sqlite_client):
        """Re-reading every endpoint reproduces backend-derived state."""
        client, strategy_id = sqlite_client
        client.post(
            f"/strategies/{strategy_id}/deploy",
            json={"cash": 100000.0, "commission_pct": 0.1, "sizer_percents": 95.0},
        )
        _tick(client, strategy_id)
        first_buy = _tick(client, strategy_id)
        for _ in range(3):  # repeated reads, like browser refreshes
            account = client.get(f"/strategies/{strategy_id}/paper-account").json()
            bars = client.get(f"/strategies/{strategy_id}/market-bars").json()
            assert account["last_bar_date"] == first_buy["bar_date"]
            assert bars["bars"][-1]["date"] == first_buy["bar_date"]


EMA_WARMUP_CODE = (
    "import backtrader as bt\n"
    "class GeneratedStrategy(bt.Strategy):\n"
    "    params = ((\"ema_fast_period\", 20), (\"ema_slow_period\", 50),)\n"
    "    def __init__(self):\n"
    "        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.p.ema_fast_period)\n"
    "        self.ema_slow = bt.indicators.EMA(self.data.close, period=self.p.ema_slow_period)\n"
    "    def next(self):\n"
    "        if self.ema_fast[0] > self.ema_slow[0] and self.ema_fast[-1] <= self.ema_slow[-1]:\n"
    "            if not self.position:\n"
    "                self.buy()\n"
)


class TestWarmupInsufficiency:
    def test_short_slice_index_error_is_warmup(self):
        from app.services.paper_engine import _is_warmup_insufficiency

        assert _is_warmup_insufficiency(IndexError("array assignment index out of range"), 2)
        assert _is_warmup_insufficiency(RuntimeError("signal replay failed: array assignment index out of range"), 49)
        assert not _is_warmup_insufficiency(IndexError("array assignment index out of range"), 300)
        assert not _is_warmup_insufficiency(RuntimeError("boom"), 5)

    def test_ema_short_slices_hold_and_advance(self, sqlite_client):
        """EMA 20/50 needs ~50 bars: ticks 1..3 must HOLD and move the watermark."""
        from app.main import app as _app
        from app.database import get_db as _get_db
        from app.models import Strategy as StrategyModel

        client, strategy_id = sqlite_client
        # Insert a real EMA-cross strategy: pre-fix, tick 2 crashed the worker
        # with IndexError and the watermark stuck at the first bar.
        gen = _app.dependency_overrides[_get_db]()
        session = next(gen)
        try:
            existing = session.query(StrategyModel).filter(
                StrategyModel.id == strategy_id
            ).first()
            ema = StrategyModel(
                conversation_id=existing.conversation_id,
                name="EMA warmup",
                description="warmup",
                market="NIFTY50",
                generated_code=EMA_WARMUP_CODE,
                status=StrategyStatus.approved,
            )
            session.add(ema)
            session.commit()
            session.refresh(ema)
            ema_id = ema.id
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

        client.post(
            f"/strategies/{ema_id}/deploy",
            json={"cash": 100000.0, "commission_pct": 0.1, "sizer_percents": 95.0},
        )
        seen = []
        for _ in range(3):
            resp = client.post(f"/strategies/{ema_id}/paper-tick", json={})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["action"] == "HOLD"
            assert body["order_id"] is None
            seen.append(body["bar_date"])
        # Watermark advanced every tick, never repeated the same bar.
        assert len(set(seen)) == 3
        assert seen == sorted(seen)
        account = client.get(f"/strategies/{ema_id}/paper-account").json()
        assert account["last_bar_date"] == seen[-1]
        assert account["last_error"] is None
        assert client.get(f"/strategies/{ema_id}/paper-orders").json() == []
        bars = client.get(f"/strategies/{ema_id}/market-bars").json()
        assert bars["bars"][-1]["date"] == seen[-1]
        assert bars["bars"][0]["date"] == seen[0]

    def test_pinned_tick_and_stopped_refusal(self, sqlite_client):
        client, strategy_id = sqlite_client
        deploy = client.post(
            f"/strategies/{strategy_id}/deploy",
            json={"cash": 100000.0, "commission_pct": 0.1, "sizer_percents": 95.0},
        )
        assert deploy.status_code == 200, deploy.text
        dep_id = deploy.json()["id"]
        first = client.post(
            f"/strategies/{strategy_id}/paper-tick",
            json={"deployment_id": dep_id},
        )
        assert first.status_code == 200, first.text
        assert first.json()["deployment_id"] == dep_id
        bad = client.post(
            f"/strategies/{strategy_id}/paper-tick",
            json={"deployment_id": str(uuid.uuid4())},
        )
        assert bad.status_code == 404
        client.post(f"/strategies/{strategy_id}/stop", json={"reason": "done"})
        stopped = client.post(
            f"/strategies/{strategy_id}/paper-tick",
            json={"deployment_id": dep_id},
        )
        assert stopped.status_code == 422

    def test_skipped_future_bar_rejected_without_mutation(self, sqlite_client):
        """A forward jump must 422 and leave watermark/ledger untouched."""
        from app.services.paper_bars import load_bars

        client, strategy_id = sqlite_client
        deploy = client.post(
            f"/strategies/{strategy_id}/deploy",
            json={"cash": 100000.0, "commission_pct": 0.1, "sizer_percents": 95.0},
        )
        dep_id = deploy.json()["id"]
        first = client.post(
            f"/strategies/{strategy_id}/paper-tick",
            json={"deployment_id": dep_id},
        ).json()
        bars = load_bars("NIFTY50")
        idx = next(i for i, b in enumerate(bars) if b["date"] == first["bar_date"])
        skip_to = bars[idx + 2]["date"]  # skip exactly one intermediate bar
        before = client.get(f"/strategies/{strategy_id}/paper-account").json()
        resp = client.post(
            f"/strategies/{strategy_id}/paper-tick",
            json={"deployment_id": dep_id, "bar_date": skip_to},
        )
        assert resp.status_code == 422, resp.text
        assert "next unprocessed market bar" in resp.text
        after = client.get(f"/strategies/{strategy_id}/paper-account").json()
        assert after["last_bar_date"] == before["last_bar_date"] == first["bar_date"]
        assert after["cash_balance"] == before["cash_balance"]
        assert client.get(f"/strategies/{strategy_id}/paper-orders").json() == []
        assert client.get(f"/strategies/{strategy_id}/paper-trades").json() == []
        # Exact-next explicit date still works.
        nxt = bars[idx + 1]["date"]
        ok = client.post(
            f"/strategies/{strategy_id}/paper-tick",
            json={"deployment_id": dep_id, "bar_date": nxt},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["bar_date"] == nxt

    def test_stop_preserves_ledger_without_liquidation(self, sqlite_client):
        """Stop freezes state: no SELL fabricated, ledger intact, tick refused."""
        client, strategy_id = sqlite_client
        dep_id = client.post(
            f"/strategies/{strategy_id}/deploy",
            json={"cash": 100000.0, "commission_pct": 0.1, "sizer_percents": 95.0},
        ).json()["id"]
        first = client.post(
            f"/strategies/{strategy_id}/paper-tick",
            json={"deployment_id": dep_id},
        ).json()
        orders_before = client.get(f"/strategies/{strategy_id}/paper-orders").json()
        trades_before = client.get(f"/strategies/{strategy_id}/paper-trades").json()
        account_before = client.get(f"/strategies/{strategy_id}/paper-account").json()
        stop = client.post(
            f"/strategies/{strategy_id}/stop", json={"reason": "manual hub test"}
        )
        assert stop.status_code == 200, stop.text
        assert stop.json()["status"] == "stopped"
        assert stop.json()["stopped_at"]
        # Ledger untouched: no fake liquidation order/trade.
        assert client.get(f"/strategies/{strategy_id}/paper-orders").json() == orders_before
        assert client.get(f"/strategies/{strategy_id}/paper-trades").json() == trades_before
        account_after = client.get(f"/strategies/{strategy_id}/paper-account").json()
        assert account_after["last_bar_date"] == first["bar_date"] == account_before["last_bar_date"]
        assert account_after["cash_balance"] == account_before["cash_balance"]
        # Stopped deployment cannot tick (pinned or unpinned).
        assert client.post(
            f"/strategies/{strategy_id}/paper-tick",
            json={"deployment_id": dep_id},
        ).status_code == 422
        assert client.post(f"/strategies/{strategy_id}/paper-tick", json={}).status_code == 422
        # History surfaces the stopped record with end timestamp.
        hub = client.get("/paper/deployments").json()
        stopped_rows = [d for d in hub if d["id"] == dep_id]
        assert len(stopped_rows) == 1
        assert stopped_rows[0]["status"] == "stopped"
        assert stopped_rows[0]["stopped_at"]
        assert [d for d in client.get("/paper/deployments/active").json() if d["id"] == dep_id] == []
