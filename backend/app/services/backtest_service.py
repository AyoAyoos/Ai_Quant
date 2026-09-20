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
import subprocess
import sys
from pathlib import Path

from app.services.strategy_runner import RESULT_MARKER, TIMEOUT_DEFAULT_SECONDS

MAX_OUTPUT_BYTES = 256 * 1024

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class BacktestError(RuntimeError):
    pass


class BacktestTimeout(BacktestError):
    pass


def _popen_kwargs():
    kwargs = {"text": False}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if creationflags:
        kwargs["creationflags"] = creationflags
    return kwargs


def run_backtest_sandboxed(
    code: str,
    data_path: str,
    cash: float = 100000.0,
    commission_pct: float = 0.1,
    sizer_percents: float = 100.0,
    timeout_seconds: int = TIMEOUT_DEFAULT_SECONDS,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> dict:
    cmd = [
        sys.executable,
        "-m",
        "app.services.strategy_runner",
        "--data", str(data_path),
        "--cash", str(cash),
        "--commission", str(commission_pct),
        "--sizer-percents", str(sizer_percents),
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
        proc.kill()
        proc.wait()
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
                return payload["metrics"]
            raise BacktestError(payload.get("error") or "worker reported an error")

    raise BacktestError("worker produced no result line")


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