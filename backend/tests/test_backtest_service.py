"""Unit + spawn tests for the sandboxed backtest orchestrator.

The failure these pin down: a worker that dies without printing the
``__BT_RESULT__`` sentinel used to surface as a bare "worker exited with
code 1" (HTTP 422) with the real traceback captured and then thrown away.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from app.config import settings
from app.services.backtest_service import (
    BacktestError,
    _annotate_warnings,
    _runner_command,
    _worker_failure_message,
    run_backtest_sandboxed,
)

FIXTURES = Path(__file__).parent / "fixtures"
NIFTY_CSV = str((FIXTURES / "nifty50.csv").resolve())
BUY_HOLD = (FIXTURES / "buy_hold.py").read_text()

SENTINEL_ERROR = b'__BT_RESULT__ {"ok": false, "error": "refused import: os"}\n'
TRACEBACK_ONLY = (
    b'Traceback (most recent call last):\n'
    b'  File "strategy_runner.py", line 12, in <module>\n'
    b'    import backtrader as bt\n'
    b"ImportError: /usr/lib/algos.so: failed to map segment from shared object\n"
)


class TestRunnerCommand:
    def test_runs_the_runner_as_a_script_not_a_module(self):
        """`-m app.services.strategy_runner` executes the package __init__ first.

        That pulls pandas in before the runner's own error handling exists, so
        a failure there exits 1 with no sentinel — exactly the 422 the API
        reported. The worker must be launched as a plain file instead.
        """
        cmd = _runner_command("/data/nifty.csv", 50000, 20, 50)

        assert cmd[1].endswith("strategy_runner.py")
        assert Path(cmd[1]).is_file()
        assert "-m" not in cmd
        assert "app.services.strategy_runner" not in cmd

    def test_passes_the_money_knobs_through_as_percentages(self):
        cmd = _runner_command("/data/nifty.csv", 50000, 20, 50)
        assert cmd[cmd.index("--cash") + 1] == "50000"
        # 20 stays 20 (a percentage), it is the worker that divides by 100.
        assert cmd[cmd.index("--commission") + 1] == "20"
        assert cmd[cmd.index("--sizer-percents") + 1] == "50"


class TestWorkerFailureMessage:
    def test_prefers_the_workers_own_sentinel_error(self):
        assert _worker_failure_message(1, SENTINEL_ERROR) == "refused import: os"

    def test_surfaces_the_traceback_when_no_sentinel_was_printed(self):
        message = _worker_failure_message(1, TRACEBACK_ONLY)
        assert "worker exited with code 1" in message
        assert "failed to map segment" in message

    def test_hints_at_the_sandbox_memory_cap(self):
        message = _worker_failure_message(1, TRACEBACK_ONLY)
        assert "SANDBOX_MEMORY_MB" in message

    def test_reports_silence_as_silence(self):
        assert _worker_failure_message(3, b"") == "worker exited with code 3 and produced no output"

    def test_truncates_a_huge_traceback(self):
        noisy = b"\n".join(b"# padding line %d" % i for i in range(5000)) + b"\nBoomError: bang\n"
        message = _worker_failure_message(1, noisy)
        assert "BoomError: bang" in message
        assert len(message) < 4000


class TestWarningAnnotation:
    @pytest.mark.parametrize("commission", [0.1, 1.0, 4.9])
    def test_realistic_commission_is_not_flagged(self, commission):
        metrics = {"warnings": []}
        _annotate_warnings(metrics, commission)
        assert metrics["warnings"] == []

    @pytest.mark.parametrize("commission", [5, 20, 99])
    def test_extreme_commission_is_flagged(self, commission):
        metrics = {"warnings": []}
        _annotate_warnings(metrics, commission)
        assert "extreme_commission" in metrics["warnings"]

    def test_creates_the_warnings_list_if_the_worker_omitted_it(self):
        metrics = {}
        _annotate_warnings(metrics, 0.1)
        assert metrics["warnings"] == []


def test_sandbox_memory_cap_leaves_room_for_pandas():
    """RLIMIT_AS below ~1.5GB makes pandas unimportable in the worker:

    ``ImportError: ... failed to map segment from shared object`` -> exit 1
    with no sentinel -> HTTP 422 "worker exited with code 1".
    """
    assert settings.sandbox_memory_mb >= 1536


class TestSandboxSpawn:
    def test_empty_code_still_produces_a_sentinel_error(self):
        """A worker that never gets to run must report *why* over the protocol."""
        with pytest.raises(BacktestError, match="bt.Strategy subclass"):
            run_backtest_sandboxed(code="", data_path=NIFTY_CSV)

    def test_runs_a_real_strategy_end_to_end(self):
        metrics = run_backtest_sandboxed(
            code=BUY_HOLD, data_path=NIFTY_CSV, cash=50000, commission_pct=20, sizer_percents=50
        )
        assert metrics["value_start"] == 50000
        assert metrics["value_end"] > 0
        assert metrics["num_trades"] == 0
        # 20% commission is legal but flagged so the UI can warn about it.
        assert "extreme_commission" in metrics["warnings"]


def test_worker_writes_a_sentinel_even_when_stdin_is_empty():
    """Guards the protocol itself: no sentinel means a bare exit code, which
    is what turned every worker crash into an opaque 422."""
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / "app" / "services" / "strategy_runner.py"),
         "--data", NIFTY_CSV],
        input="",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1
    assert "__BT_RESULT__" in proc.stdout
    assert '"ok": false' in proc.stdout
