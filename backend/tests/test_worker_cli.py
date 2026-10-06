import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

from app.services.backtest_service import (
    BacktestError,
    BacktestTimeout,
    _kill_tree,
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

        # Sentinel must be the very last line (strategy prints come before it).
        lines = result.stdout.decode().splitlines()
        sentinel_pos = next(i for i, l in enumerate(lines) if l.startswith(RESULT_MARKER))
        assert sentinel_pos == len(lines) - 1

    def test_rejects_malicious_code_with_nonzero_exit(self):
        code = "import backtrader as bt\nexec('import os')\n"
        result = _run_worker(code + "class GeneratedStrategy(bt.Strategy):\n    def next(self):\n        self.buy()")
        assert result.returncode == 1
        ok, payload = _last_sentinel(result.stdout)
        assert not ok
        assert "refused" in payload["error"].lower()


class TestOrchestrator:
    def test_cagr_is_a_percentage_consistent_with_total_return(self):
        """cagr_pct must be on the same scale as the other *_pct metrics.

        Runs the real sandboxed pipeline (one subprocess) because the value
        under test is computed by the orchestrator from worker-reported dates.
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


def _spawn_sleeper_tree():
    """Spawn a parent python that spawns a child sleeper, mirroring how a
    strategy could shell out. Returns (parent_proc, child_pid_file)."""
    marker = BACKEND_DIR / f"_child_{os.getpid()}.pid"
    posix_marker = marker.as_posix()
    parent_code = (
        "import subprocess, sys, time; "
        f"p = subprocess.Popen([sys.executable, '-c', "
        f"\"import time; open('{posix_marker}', 'w').write(str(__import__('os').getpid())); "
        "time.sleep(120)\"]); "
        "time.sleep(120)"
    )
    kwargs = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([sys.executable, "-c", parent_code], **kwargs)
    return proc, marker


def _wait_for_file(path, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.2)
    return False


def _pid_alive(pid: int) -> bool:
    if os.name == "posix":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True, text=True,
    )
    return str(pid) in out.stdout


class TestKillTree:
    def test_kills_lone_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        _kill_tree(proc)
        assert proc.poll() is not None

    def test_kills_whole_tree_not_just_parent(self):
        proc, marker = _spawn_sleeper_tree()
        try:
            assert _wait_for_file(marker), "child sleeper never started"
            child_pid = int(marker.read_text().strip())
            assert _pid_alive(child_pid)

            _kill_tree(proc)

            assert proc.poll() is not None
            deadline = time.time() + 10
            while _pid_alive(child_pid) and time.time() < deadline:
                time.sleep(0.2)
            assert not _pid_alive(child_pid), "orphaned child survived the tree kill"
        finally:
            if proc.poll() is None:
                proc.kill()
            if marker.exists():
                marker.unlink()

    @pytest.mark.skipif(os.name != "posix", reason="rlimit sandbox is POSIX-only")
    def test_tiny_memory_cap_kills_worker(self, monkeypatch):
        import app.services.backtest_service as svc

        monkeypatch.setattr(svc.settings, "sandbox_memory_mb", 64)
        code = (FIXTURES / "buy_hold.py").read_text()
        with pytest.raises(BacktestError):
            run_backtest_sandboxed(code, str(DATA.resolve()), timeout_seconds=60)