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
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services.strategy_runner import RESULT_MARKER, TIMEOUT_DEFAULT_SECONDS

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 256 * 1024
# How much of the worker's (merged stdout+stderr) output ends up inside the
# error message the API hands back to the browser. Full output is logged.
MAX_ERROR_CHARS = 1200
# How much of it is written to the log when the worker fails.
MAX_LOG_CHARS = 4000

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_RUNNER_PATH = Path(__file__).resolve().with_name("strategy_runner.py")


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


def _runner_command(data_path, cash, commission_pct, sizer_percents) -> list:
    """Build the worker argv.

    The runner is launched as a *script file*, never as
    ``python -m app.services.strategy_runner``. ``-m`` executes the
    ``app.services`` package ``__init__`` first, which imports pandas,
    yfinance and the LLM client before a single line of runner code runs.
    That costs hundreds of MB of address space against the sandbox rlimit and
    — critically — any failure there happens *before* the runner's own
    try/except, so no ``__BT_RESULT__`` sentinel is ever printed and the API
    can only say "worker exited with code 1". ``strategy_runner.py`` imports
    nothing from ``app``, so running the file directly is equivalent, cheaper
    and puts every failure inside the sentinel protocol.
    """
    return [
        sys.executable,
        str(_RUNNER_PATH),
        "--data", str(data_path),
        "--cash", str(cash),
        "--commission", str(commission_pct),
        "--sizer-percents", str(sizer_percents),
    ]


def run_backtest_sandboxed(
    code: str,
    data_path: str,
    cash: float = 100000.0,
    commission_pct: float = 0.1,
    sizer_percents: float = 95.0,
    timeout_seconds: int = TIMEOUT_DEFAULT_SECONDS,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> dict:
    cmd = _runner_command(data_path, cash, commission_pct, sizer_percents)
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
        # The traceback the worker printed is the only record of *why* it
        # died — log it in full (capped) and surface a readable tail in the
        # error the endpoint returns, instead of discarding it.
        logger.error(
            "backtest worker exited with code %s\ncmd: %s\n%s",
            proc.returncode,
            " ".join(cmd),
            _truncate(out.decode("utf-8", "replace"), MAX_LOG_CHARS) or "<no output>",
        )
        raise BacktestError(_worker_failure_message(proc.returncode, out))

    text = out.decode("utf-8", "replace")
    if len(text) > max_output_bytes:
        raise BacktestError(f"worker output exceeded {max_output_bytes} bytes")

    for line in reversed(text.splitlines()):
        if line.startswith(RESULT_MARKER):
            payload = json.loads(line[len(RESULT_MARKER):].strip())
            if payload.get("ok"):
                metrics = payload["metrics"]
                metrics["cagr_pct"] = _compute_cagr_pct(metrics)
                _annotate_warnings(metrics, commission_pct)
                return metrics
            if payload.get("traceback"):
                logger.error(
                    "backtest worker reported an error\n%s",
                    _truncate(str(payload["traceback"]), MAX_LOG_CHARS),
                )
            error = payload.get("error") or "worker reported an error"
            logger.warning("backtest worker rejected the run: %s", error)
            raise BacktestError(error)

    # Non-zero exit without a sentinel never gets here (handled above), so this
    # is a zero exit whose output was truncated or garbled.
    logger.error("backtest worker produced no result line\ncmd: %s\n%s", " ".join(cmd), _truncate(text, MAX_LOG_CHARS))
    raise BacktestError("worker produced no result line")


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return "... (truncated) ...\n" + text[-limit:]


def _summarize_output(text: str, limit: int = MAX_ERROR_CHARS) -> str:
    """Collapse worker output into the few lines that explain the failure.

    For a Python traceback that is the final ``ExceptionType: message`` line
    plus the frame that raised it — enough to act on without shipping the
    whole traceback to the browser.
    """
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return _truncate(" | ".join(lines[-3:]), limit)


# Output fragments that mean the sandbox, not the strategy, is at fault.
_MEMORY_SIGNATURES = (
    "failed to map segment",
    "MemoryError",
    "Cannot allocate memory",
    "std::bad_alloc",
)


def _worker_failure_message(returncode: int, out: bytes) -> str:
    """Build the error string for a worker that died without a usable sentinel.

    Prefers the worker's own ``__BT_RESULT__`` error (the runner puts the real
    exception there); otherwise falls back to the tail of its captured output
    so the caller sees ``ImportError: ...`` rather than a bare exit code.
    """
    reported = _parse_worker_error(out)
    if reported:
        return reported

    text = out.decode("utf-8", "replace")
    summary = _summarize_output(text)
    if not summary:
        return f"worker exited with code {returncode} and produced no output"

    message = f"worker exited with code {returncode}: {summary}"
    if any(signature in text for signature in _MEMORY_SIGNATURES):
        message += (
            " — the worker hit the sandbox memory cap "
            f"(SANDBOX_MEMORY_MB={settings.sandbox_memory_mb}); raise it or lower the data range"
        )
    return message


def _annotate_warnings(metrics: dict, commission_pct: float) -> None:
    """Flag parameter choices that make a run meaningless (not a failure)."""
    warnings = metrics.setdefault("warnings", [])
    if commission_pct >= 5:
        warnings.append("extreme_commission")


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
