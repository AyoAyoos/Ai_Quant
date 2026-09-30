import json
from pathlib import Path

import pytest

from app.services.strategy_runner import (
    GuardrailError,
    _compute_sortino,
    load_dataframe,
    pct_to_fraction,
    run_backtest,
)

FIXTURES = Path(__file__).parent / "fixtures"
DATA = FIXTURES / "nifty50.csv"
CASH = 100000.0
COMMISSION = 0.1
SIZER = 95.0


@pytest.fixture(scope="module")
def data_path():
    return str(DATA.resolve())


@pytest.mark.parametrize(
    "strategy_file",
    ["buy_hold.py", "alternating.py", "swing_churn.py", "rsi_meanrev.py"],
)
def test_run_backtest_returns_valid_metrics(data_path, strategy_file):
    code = (FIXTURES / strategy_file).read_text()
    metrics = run_backtest(code, data_path, CASH, COMMISSION, SIZER)

    assert metrics["value_start"] == CASH
    assert metrics["value_end"] > 0
    assert isinstance(metrics["total_return_pct"], float)
    assert metrics["start_date"] and metrics["end_date"]
    assert metrics["num_trades"] >= 0
    assert isinstance(metrics["warnings"], list)

    # Must be JSON-serializable (the worker ships these over stdout as JSON).
    json.dumps(metrics)


def test_buy_hold_never_closes_a_trade(data_path):
    code = (FIXTURES / "buy_hold.py").read_text()
    metrics = run_backtest(code, data_path, CASH, COMMISSION, SIZER)
    assert metrics["num_trades"] == 0
    assert "no_trades" in metrics["warnings"]
    assert "win_rate_pct" in metrics


@pytest.mark.parametrize("strategy_file", ["alternating.py", "swing_churn.py"])
def test_active_strategies_generate_trades(data_path, strategy_file):
    code = (FIXTURES / strategy_file).read_text()
    metrics = run_backtest(code, data_path, CASH, COMMISSION, SIZER)
    assert metrics["num_trades"] > 0
    assert "no_trades" not in metrics["warnings"]


def test_guardrail_runs_before_execution(data_path):
    malicious = "import backtrader as bt\nexec('import os')\nclass GeneratedStrategy(bt.Strategy):\n    def next(self):\n        self.buy()"
    with pytest.raises(GuardrailError):
        run_backtest(malicious, data_path, CASH, COMMISSION, SIZER)


def test_fromisoformat_start_date_is_parseable(data_path):
    code = (FIXTURES / "alternating.py").read_text()
    metrics = run_backtest(code, data_path, CASH, COMMISSION, SIZER)
    from datetime import date

    start = date.fromisoformat(metrics["start_date"])
    end = date.fromisoformat(metrics["end_date"])
    assert start <= end


class TestLoadDataframe:
    def test_insufficient_rows_rejected(self, tmp_path):
        p = tmp_path / "tiny.csv"
        p.write_text("Date,Open,High,Low,Close,Volume\n2023-01-01,1,2,0.5,1.5,100\n")
        with pytest.raises(ValueError, match="insufficient data"):
            load_dataframe(str(p))

    def test_missing_required_columns_rejected(self, tmp_path):
        p = tmp_path / "bad.csv"
        p.write_text(
            "Date,Open,Close\n2023-01-01,1,2\n2023-01-02,1,2\n2023-01-03,1,2\n"
        )
        with pytest.raises(ValueError, match="missing columns"):
            load_dataframe(str(p))

    def test_no_date_column_or_index_rejected(self, tmp_path):
        p = tmp_path / "nodate.csv"
        p.write_text("Open,High,Low,Close,Volume\n1,2,0.5,1.5,100\n1,2,0.5,1.5,100\n1,2,0.5,1.5,100\n")
        with pytest.raises(ValueError, match="Date"):
            load_dataframe(str(p))

    def test_zero_volume_rejected(self, tmp_path):
        p = tmp_path / "zerovol.csv"
        p.write_text(
            "Date,Open,High,Low,Close,Volume\n"
            "2023-01-01,1,2,0.5,1.5,0\n2023-01-02,1,2,0.5,1.5,0\n2023-01-03,1,2,0.5,1.5,0\n"
        )
        with pytest.raises(ValueError, match="zero volume"):
            load_dataframe(str(p))


def test_pct_to_fraction():
    assert pct_to_fraction(100.0) == 1.0
    assert pct_to_fraction(0.1) == 0.001


class TestTradeListAndEquityCurve:
    def test_swing_churn_reports_every_trade(self, data_path):
        code = (FIXTURES / "swing_churn.py").read_text()
        metrics = run_backtest(code, data_path, CASH, COMMISSION, SIZER)

        assert len(metrics["trades"]) == metrics["num_trades"] == 123
        assert metrics["trades_truncated"] == 0

        first = metrics["trades"][0]
        assert first["entry_date"] < first["exit_date"]
        assert first["bars_held"] > 0
        assert first["direction"] == "long"
        assert isinstance(first["size"], int) and first["size"] > 0
        # pnl_net sums back to the aggregate within rounding.
        assert sum(t["pnl_net"] for t in metrics["trades"]) == pytest.approx(
            metrics["closed_pnl"], abs=1.0
        )
        wins = sum(1 for t in metrics["trades"] if t["won"])
        assert wins / len(metrics["trades"]) * 100 == pytest.approx(
            metrics["win_rate_pct"], abs=0.6
        )

    def test_buy_hold_has_no_trades_but_has_equity(self, data_path):
        code = (FIXTURES / "buy_hold.py").read_text()
        metrics = run_backtest(code, data_path, CASH, COMMISSION, SIZER)

        assert metrics["trades"] == []
        assert metrics["trades_truncated"] == 0
        assert len(metrics["equity_curve"]) > 0

    def test_equity_curve_ends_on_broker_value(self, data_path):
        code = (FIXTURES / "swing_churn.py").read_text()
        metrics = run_backtest(code, data_path, CASH, COMMISSION, SIZER)

        curve = metrics["equity_curve"]
        assert curve[0][0] == metrics["start_date"]
        assert curve[-1][0] == metrics["end_date"]
        assert curve[0][1] == pytest.approx(CASH, abs=1.0)
        assert curve[-1][1] == pytest.approx(metrics["value_end"], abs=0.01)
        assert len(curve) <= 400
        # Monotonic in time.
        assert [p[0] for p in curve] == sorted(p[0] for p in curve)

    def test_metrics_stay_json_serializable(self, data_path):
        code = (FIXTURES / "swing_churn.py").read_text()
        metrics = run_backtest(code, data_path, CASH, COMMISSION, SIZER)
        json.dumps(metrics)


class TestSortino:
    """Sortino is derived locally because backtrader 1.9.78.123 ships no
    Sortino analyzer — the ``SortinoRatio_A`` lookup always misses."""

    def test_needs_at_least_two_periods(self):
        assert _compute_sortino({}) is None
        assert _compute_sortino(None) is None
        assert _compute_sortino({1: 0.01}) is None

    def test_undefined_without_downside(self):
        # No losing period means zero downside deviation -> no finite ratio.
        assert _compute_sortino({1: 0.01, 2: 0.02}) is None

    def test_all_losses_gives_negative_ratio(self):
        assert _compute_sortino({1: -0.01, 2: -0.02}) < 0

    def test_upside_volatility_is_not_punished(self):
        """Mirroring large gains into losses must worsen the ratio.

        If upside moves inflated the denominator, flipping them to downside
        would leave the ratio unchanged.
        """
        sideways = _compute_sortino({1: 0.20, 2: 0.20, 3: -0.05})
        mirrored = _compute_sortino({1: -0.20, 2: -0.20, 3: -0.05})
        assert sideways > mirrored

    def test_a_gain_lifts_the_ratio_without_being_penalised(self):
        low = _compute_sortino({1: 0.02, 2: -0.02, 3: 0.02})
        high = _compute_sortino({1: 0.10, 2: -0.02, 3: 0.10})
        assert high > low > 0

    def test_real_backtest_reports_sane_sortino(self, data_path):
        """Guards against the geometric-annualisation blowup (values like 69)."""
        for fixture in ("buy_hold.py", "swing_churn.py", "alternating.py"):
            code = (FIXTURES / fixture).read_text()
            metrics = run_backtest(code, data_path, CASH, COMMISSION, SIZER)
            sortino = metrics["sortino"]
            assert sortino is not None, fixture
            assert abs(sortino) < 10.0, f"{fixture} sortino={sortino} is not sane"
            # Downside deviation can never exceed total deviation, so Sortino is
            # at least as large as Sharpe whenever both are positive.
            sharpe = metrics["sharpe"]
            if sharpe is not None and sharpe > 0:
                assert sortino >= sharpe - 0.01, fixture
            if metrics["total_return_pct"] < 0:
                assert sortino < 0, fixture
