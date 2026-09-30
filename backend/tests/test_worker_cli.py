import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from app.services.backtest_service import (
    BacktestError,
    BacktestTimeout,
    run_backtest_sandboxed,
)
from app.services.strategy_runner import RESULT_MARKER

FIXTURES = Path(__file__).parent / "fixtures"
DATA = FIXTURES / "nifty50.csv"
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_worker(code, *args):
    cmd = [
        sys.executable,
        "-m",
        "app.services.strategy_runner",
        "--data",
        str(DATA.resolve()),
        "--sizer-percents",
        "95",
        *args,
    ]
    return subprocess.run(
        cmd,
        cwd=str(BACKEND_DIR),
        input=code.encode("utf-8"),
        capture_output=True,
        timeout=60,
    )


def _last_sentinel(binary: bytes) -> tuple[bool, dict]:
    for line in reversed(binary.decode("utf-8", "replace").splitlines()):
        if line.startswith(RESULT_MARKER):
            payload = json.loads(line[len(RESULT_MARKER):].strip())
            return bool(payload.get("ok")), payload
    return False, {}


class TestWorkerCli:
    def test_runs_strategy_and_emits_sentinel(self):
        code = (FIXTURES / "buy_hold.py").read_text()
        result = _run_worker(code)
        assert result.returncode == 0
        ok, payload = _last_sentinel(result.stdout)
        assert ok
        assert payload["metrics"]["value_start"] == 100000.0
        assert payload["metrics"]["num_trades"] == 0

    def test_rejects_malicious_code_with_nonzero_exit(self):
        code = "import backtrader as bt\nexec('import os')\n"
        result = _run_worker(code + "class GeneratedStrategy(bt.Strategy):\n    def next(self):\n        self.buy()")
        assert result.returncode == 1
        ok, payload = _last_sentinel(result.stdout)
        assert not ok
        assert "refused" in payload["error"].lower()

    def test_strategy_output_precedes_sentinel(self):
        code = (FIXTURES / "buy_hold.py").read_text()
        result = _run_worker(code)
        lines = result.stdout.decode().splitlines()
        sentinel_pos = next(i for i, l in enumerate(lines) if l.startswith(RESULT_MARKER))
        assert sentinel_pos == len(lines) - 1  # sentinel is the last line


class TestOrchestrator:
    def test_metrics_come_back_with_cagr(self):
        code = (FIXTURES / "alternating.py").read_text()
        metrics = run_backtest_sandboxed(code, str(DATA.resolve()), timeout_seconds=60)
        assert "cagr_pct" in metrics
        assert isinstance(metrics["total_return_pct"], float)

    def test_cagr_is_a_percentage_consistent_with_total_return(self):
        """cagr_pct must be on the same scale as the other *_pct metrics.

        A raw ratio (-0.134) is easy to mistake for a percent and mislabels
        results as ~100x smaller than reality, so pin the scale explicitly.
        """
        code = (FIXTURES / "alternating.py").read_text()
        metrics = run_backtest_sandboxed(code, str(DATA.resolve()), timeout_seconds=60)

        cagr = metrics["cagr_pct"]
        total = metrics["total_return_pct"]
        start = datetime.fromisoformat(str(metrics["start_date"])).date()
        end = datetime.fromisoformat(str(metrics["end_date"])).date()
        days = (end - start).days

        assert cagr is not None and days > 0
        expected = (((1.0 + total / 100.0) ** (365.0 / days)) - 1.0) * 100.0
        assert cagr == pytest.approx(expected, rel=1e-3)
        assert (cagr > 0) == (total > 0) or total == 0
        assert -100.0 < cagr < 1_000_000.0

    def test_kills_runaway_strategy_after_timeout(self):
        code = (
            "import backtrader as bt\n"
            "class GeneratedStrategy(bt.Strategy):\n"
            "    def next(self):\n"
            "        while True:\n"
            "            pass\n"
        )
        with pytest.raises(BacktestTimeout):
            run_backtest_sandboxed(code, str(DATA.resolve()), timeout_seconds=3)

    def test_surfaces_guardrail_error(self):
        code = "import backtrader as bt\nopen('x')\nclass GeneratedStrategy(bt.Strategy):\n    def next(self):\n        self.buy()"
        with pytest.raises(BacktestError, match="refused"):
            run_backtest_sandboxed(code, str(DATA.resolve()))