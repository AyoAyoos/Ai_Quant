"""
Sandboxed backtest orchestrator.

Spins up the strategy runner (``app.services.strategy_runner``) as an isolated
subprocess so AI-generated code never executes inside the API process. The
worker reads the strategy code from stdin and writes a single sentinel-prefixed
JSON line (``__BT_RESULT__ ...``) on stdout; anything the strategy itself prints
arrives before that line and is discarded (byte-capped). A hard wall-clock
timeout bounds worst-case runtime so a runaway or malicious strategy can't hang
the server.
"""
import json
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services.strategy_runner import RESULT_MARKER, TIMEOUT_DEFAULT_SECONDS

MAX_OUTPUT_BYTES = 256 * 1024

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class BacktestError(RuntimeError):
    pass


class BacktestTimeout(BacktestError):
    pass


def _popen_kwargs():
    kwargs = {"text": False}
    if os.name == "posix":
        # New session => the worker is a process-group leader, so a timeout
        # can signal the whole tree (killpg), not just the direct child.
        kwargs["start_new_session"] = True
        memory_mb = settings.sandbox_memory_mb
        cpu_seconds = settings.sandbox_cpu_seconds
        if memory_mb or cpu_seconds:
            kwargs["preexec_fn"] = lambda: _apply_posix_limits(memory_mb, cpu_seconds)
    else:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if creationflags:
            kwargs["creationflags"] = creationflags
    return kwargs


def _apply_posix_limits(memory_mb: int | None, cpu_seconds: int | None) -> None:
    """Runs in the forked child before exec. Import is local because the
    ``resource`` module does not exist on Windows (this never runs there)."""
    import resource

    if memory_mb:
        limit = int(memory_mb * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    if cpu_seconds:
        resource.setrlimit(resource.RLIMIT_CPU, (int(cpu_seconds), int(cpu_seconds)))


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the worker and anything it spawned.

    ``proc.kill()`` alone only kills the direct child — a strategy that
    shells out would leave orphans behind. On POSIX the worker is a process
    group leader (see _popen_kwargs), so killpg takes the whole tree. On
    Windows taskkill /T walks and kills the child tree.
    """
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
            )
    except Exception:
        pass
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


def _compute_cagr_pct(metrics: dict) -> float | None:
    """Annualised return from the value span + date span the runner reported."""
    value_start = metrics.get("value_start")
    value_end = metrics.get("value_end")
    start = metrics.get("start_date")
    end = metrics.get("end_date")
    if not value_start or not value_end or not start or not end:
        return None
    try:
        start_dt = datetime.fromisoformat(str(start)).date()
        end_dt = datetime.fromisoformat(str(end)).date()
    except ValueError:
        return None
    days = (end_dt - start_dt).days
    if days <= 0 or float(value_start) <= 0:
        return None
    # Return a percentage, consistent with the other ``*_pct`` metrics.
    return round(((float(value_end) / float(value_start)) ** (365.0 / days) - 1.0) * 100.0, 4)


def _run_worker(
    code: str,
    data_path: str,
    cash: float,
    commission_pct: float,
    sizer_percents: float,
    extra_args: list[str],
    timeout_seconds: int,
    max_output_bytes: int,
) -> dict:
    """Spawn the strategy worker and return its sentinel payload.

    Shared by the backtest and paper-signal paths so both get the identical
    isolation story (fresh process, stdin-delivered code, output byte cap,
    hard timeout, process-tree kill). The AI-generated code never runs inside
    the API process either way — adding a second, weaker spawn helper for the
    signal path would be the easy way to quietly erode that boundary.
    """
    cmd = [
        sys.executable,
        "-m",
        "app.services.strategy_runner",
        "--data", str(data_path),
        "--cash", str(cash),
        "--commission", str(commission_pct),
        "--sizer-percents", str(sizer_percents),
        *extra_args,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(_BACKEND_DIR),
        env=os.environ.copy(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **_popen_kwargs(),
    )

    try:
        out, _ = proc.communicate(input=code.encode("utf-8"), timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        raise BacktestTimeout(f"backtest exceeded {timeout_seconds}s and was killed") from None

    if proc.returncode != 0:
        raise BacktestError(
            _parse_worker_error(out) or f"worker exited with code {proc.returncode}"
        )

    text = out.decode("utf-8", "replace")
    if len(text) > max_output_bytes:
        raise BacktestError(f"worker output exceeded {max_output_bytes} bytes")

    for line in reversed(text.splitlines()):
        if line.startswith(RESULT_MARKER):
            payload = json.loads(line[len(RESULT_MARKER):].strip())
            if payload.get("ok"):
                return payload
            raise BacktestError(payload.get("error") or "worker reported an error")

    raise BacktestError("worker produced no result line")


def run_backtest_sandboxed(
    code: str,
    data_path: str,
    cash: float = 100000.0,
    commission_pct: float = 0.1,
    sizer_percents: float = 95.0,
    timeout_seconds: int = TIMEOUT_DEFAULT_SECONDS,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> dict:
    payload = _run_worker(
        code=code,
        data_path=data_path,
        cash=cash,
        commission_pct=commission_pct,
        sizer_percents=sizer_percents,
        extra_args=[],
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
    )
    metrics = payload["metrics"]
    metrics["cagr_pct"] = _compute_cagr_pct(metrics)
    return metrics


def run_signal_sandboxed(
    code: str,
    data_path: str,
    cash: float = 100000.0,
    commission_pct: float = 0.1,
    sizer_percents: float = 95.0,
    upto_date: str | None = None,
    timeout_seconds: int = TIMEOUT_DEFAULT_SECONDS,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> dict:
    """Ask the strategy what it wants to do on one bar.

    Returns the worker's ``{"action", "bar_date", "close"}`` payload. Raises the
    same :class:`BacktestError` / :class:`BacktestTimeout` as a backtest so the
    router can map worker failures the same way.
    """
    extra_args = ["--signal"]
    if upto_date:
        extra_args += ["--upto-date", str(upto_date)]

    payload = _run_worker(
        code=code,
        data_path=data_path,
        cash=cash,
        commission_pct=commission_pct,
        sizer_percents=sizer_percents,
        extra_args=extra_args,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
    )
    return payload["signal"]


def _parse_worker_error(out: bytes) -> str | None:
    """Extract the worker's error string from a sentinel line, if present."""
    for line in reversed(out.decode("utf-8", "replace").splitlines()):
        if not line.startswith(RESULT_MARKER):
            continue
        try:
            payload = json.loads(line[len(RESULT_MARKER):].strip())
        except json.JSONDecodeError:
            continue
        error = payload.get("error")
        if error:
            return error
    return None