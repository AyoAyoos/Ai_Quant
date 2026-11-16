"""
QuantCode-Bench single-turn evaluation adapter.

Runs backtest_reward_fn in an isolated subprocess with per-evaluation
temporary directory, process-group termination, and exact file cleanup.
Evaluation is best-effort and backend-only.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Windows Job Object ctypes helpers
if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    CreateJobObjectW = kernel32.CreateJobObjectW
    CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPWSTR]
    CreateJobObjectW.restype = wintypes.HANDLE

    SetInformationJobObject = kernel32.SetInformationJobObject
    SetInformationJobObject.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
    SetInformationJobObject.restype = wintypes.BOOL

    AssignProcessToJobObject = kernel32.AssignProcessToJobObject
    AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    AssignProcessToJobObject.restype = wintypes.BOOL

    ResumeThread = kernel32.ResumeThread
    ResumeThread.argtypes = [wintypes.HANDLE]
    ResumeThread.restype = wintypes.DWORD

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    QueryInformationJobObject = kernel32.QueryInformationJobObject
    QueryInformationJobObject.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    QueryInformationJobObject.restype = wintypes.BOOL

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformationClass = 9

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_ulonglong),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

_DEFAULT_QCB_PATH_WIN = r"D:\QuantCode-Bench"
_DEFAULT_BACKEND_PATH_WIN = r"D:\Ai_Quant_Clean\backend"
_DEFAULT_QCB_PATH_LINUX = "/mnt/d/QuantCode-Bench"
_DEFAULT_BACKEND_PATH_LINUX = "/mnt/d/Ai_Quant_Clean/backend"

if os.name == "nt":
    _default_qcb = _DEFAULT_QCB_PATH_WIN
    _default_backend = _DEFAULT_BACKEND_PATH_WIN
else:
    _default_qcb = _DEFAULT_QCB_PATH_LINUX
    _default_backend = _DEFAULT_BACKEND_PATH_LINUX

QCB_PATH = os.environ.get("QCB_PATH", _default_qcb)
AI_QUANT_BACKEND = os.environ.get("AI_QUANT_BACKEND", _default_backend)

EVALUATION_TIMEOUT = 120  # seconds


def _create_windows_job() -> Optional[wintypes.HANDLE]:
    """Create a Job Object with KILL_ON_JOB_CLOSE. Returns handle or None on failure."""
    if os.name != "nt":
        return None
    job = CreateJobObjectW(None, None)
    if not job:
        return None
    try:
        eli = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        eli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not SetInformationJobObject(job, JobObjectExtendedLimitInformationClass, ctypes.byref(eli), ctypes.sizeof(eli)):
            CloseHandle(job)
            return None
        return job
    except Exception:
        try:
            CloseHandle(job)
        except Exception:
            pass
        return None


def _job_has_active_processes(job: wintypes.HANDLE) -> bool:
    """Return True if job still has active processes, False if empty or on error."""
    if os.name != "nt" or not job:
        return False
    class JOBOBJECT_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("NumberOfAssignedProcesses", ctypes.c_uint32),
            ("NumberOfProcessInJob", ctypes.c_uint32),
        ]
    info = JOBOBJECT_BASIC_INFORMATION()
    size = ctypes.sizeof(info)
    returned = wintypes.DWORD()
    ok = QueryInformationJobObject(job, 0, ctypes.byref(info), size, ctypes.byref(returned))
    if not ok:
        return True  # conservative
    return info.NumberOfProcessInJob > 0


def _pgid_is_empty(pgid: int) -> bool:
    """Return True if process group pgid has no live members."""
    if pgid is None:
        return True
    try:
        result = subprocess.run(
            ["pgrep", "-g", str(pgid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return len(result.stdout.strip()) == 0
    except FileNotFoundError:
        # pgrep not available, fallback to /proc scan
        try:
            for pid_str in os.listdir('/proc'):
                if not pid_str.isdigit():
                    continue
                try:
                    with open(f'/proc/{pid_str}/status') as f:
                        for line in f:
                            if line.startswith('PGid:'):
                                try:
                                    cur_pgid = int(line.split(':')[1].strip())
                                    if cur_pgid == pgid:
                                        return False
                                except ValueError:
                                    pass
                                break
                except Exception:
                    continue
            return True
        except Exception:
            return False
    except Exception:
        # Conservative: assume not empty
        return False


def _process_tree_has_descendants(pid: int) -> bool:
    """Return True if the process has living children. Conservative on errors."""
    try:
        if os.name == "nt":
            # wmic is available on Windows; list direct children
            result = subprocess.run(
                ["wmic", "process", "where", f"ParentProcessId={pid}", "get", "ProcessId"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Filter lines that are pure digits
            pids = [ln.strip() for ln in result.stdout.splitlines() if ln.strip().isdigit()]
            return len(pids) > 0
        else:
            # Unix: pgrep -P finds direct children
            result = subprocess.run(
                ["pgrep", "-P", str(pid)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return len(result.stdout.strip()) > 0
    except Exception:
        # On failure be conservative: assume descendants may exist
        return True


def _qcb_processes_remaining(marker: str = "qcb_runner.py") -> bool:
    """Return True if any QCB evaluator processes are still running, identified by marker in command line."""
    try:
        if os.name == "nt":
            # wmic query by CommandLine containing marker
            result = subprocess.run(
                ["wmic", "process", "where", f"CommandLine like '%{marker}%'", "get", "ProcessId"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            pids = [ln.strip() for ln in result.stdout.splitlines() if ln.strip().isdigit()]
            return len(pids) > 0
        else:
            result = subprocess.run(
                ["pgrep", "-f", marker],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return len(result.stdout.strip()) > 0
    except Exception:
        # Conservative: assume processes may remain
        return True


def _run_evaluator_subprocess(task_info: Dict[str, Any], code: str, strategy_uuid: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute QuantCode-Bench evaluation in an isolated subprocess.

    Returns dict with evaluation result or error info.
    """
    # Warn if QCB path is not accessible; evaluation will fail gracefully
    if not os.path.isdir(QCB_PATH):
        logger.warning("QuantCode-Bench path %s not accessible, evaluation may fail for strategy_uuid=%s", QCB_PATH, strategy_uuid)
    # Create per-evaluation temp dir
    temp_dir = tempfile.mkdtemp(prefix="qcb_eval_")
    try:
        # Environment with isolated TEMP/TMP/TMPDIR
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([QCB_PATH, AI_QUANT_BACKEND])
        env["TEMP"] = temp_dir
        env["TMP"] = temp_dir
        env["TMPDIR"] = temp_dir
        # Disable judge by default unless env vars are present in host
        # Keep judge optional; do not require openai import
        # Ensure subprocess doesn't inherit unnecessary vars
        # Build a small runner script
        runner_code = f"""
import json, sys, os
# Ensure temp dir is used
os.environ["TEMP"] = r"{temp_dir}"
os.environ["TMP"] = r"{temp_dir}"
os.environ["TMPDIR"] = r"{temp_dir}"
try:
    from quantcode_bench.reward import backtest_reward_fn
except Exception as e:
    print(json.dumps({{"error": "import_failed", "message": str(e)}}))
    sys.exit(0)

task_info = {json.dumps(task_info)}
code = {json.dumps(code)}

try:
    reward, metadata = backtest_reward_fn(task_info, code)
    out = {{"reward": reward, "metadata": metadata}}
except Exception as e:
    out = {{"error": "evaluation_exception", "message": str(e)}}
print(json.dumps(out))
"""
        # Write runner to a temp file to avoid command-line quoting issues
        runner_path = Path(temp_dir) / "qcb_runner.py"
        runner_path.write_text(runner_code, encoding="utf-8")

        # Prepare subprocess with isolation
        job_handle = None
        pgid = None
        creationflags = 0
        start_new_session = False
        if os.name == "nt":
            job_handle = _create_windows_job()
            if job_handle:
                create_suspended = getattr(subprocess, "CREATE_SUSPENDED", 0)
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | create_suspended
            else:
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            start_new_session = True

        proc = subprocess.Popen(
            [sys.executable, str(runner_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )

        # Assign to job / capture pgid for ownership
        if os.name == "nt" and job_handle:
            try:
                assigned = AssignProcessToJobObject(job_handle, proc._handle)
                if assigned:
                    # Resume main thread
                    try:
                        ResumeThread(proc._thread_handle)
                    except Exception:
                        pass
                else:
                    logger.warning("Failed to assign evaluator process %s to Job Object, temp dir will be preserved", proc.pid)
            except Exception as e:
                logger.warning("Job Object assignment error PID %s: %s", proc.pid, e)
        elif os.name != "nt":
            try:
                pgid = os.getpgid(proc.pid)
            except Exception as e:
                logger.warning("Failed to capture pgid for PID %s: %s", proc.pid, e)
                pgid = None

        try:
            stdout, stderr = proc.communicate(timeout=EVALUATION_TIMEOUT)
        except subprocess.TimeoutExpired:
            # Kill process tree
            _kill_process_tree(proc, pgid)
            return {"error": "timeout", "message": f"Evaluation exceeded {EVALUATION_TIMEOUT}s"}

        # Parse output
        try:
            result = json.loads(stdout.strip().splitlines()[-1])
        except Exception:
            result = {"error": "parse_failed", "stderr": stderr[-500:]}

        if "error" in result:
            logger.warning("QuantCode-Bench evaluation error for strategy_uuid=%s strategy_id=%s: %s",
                           strategy_uuid or "unknown", task_info.get("strategy_id"), result.get("message"))
        else:
            logger.debug("QuantCode-Bench evaluation completed for strategy_uuid=%s strategy_id=%s reward=%s metadata=%s",
                         strategy_uuid or "unknown", task_info.get("strategy_id"), result.get("reward"), result.get("metadata"))

        return result

    finally:
        # Ensure process tree terminated before cleanup
        process_terminated = False
        kill_success = True
        try:
            if 'proc' in locals():
                # Always attempt to terminate owned container, even if parent already exited
                if os.name != "nt" and pgid is not None:
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        # Process group already gone, treat as success
                        pass
                    except Exception as e:
                        logger.warning("Failed to kill process group %s: %s", pgid, e)
                        kill_success = False
                # Windows termination is handled by Job Object KILL_ON_JOB_CLOSE; no extra kill needed
                # Wait for parent to ensure it has exited
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.error("QuantCode-Bench evaluator process %s did not terminate after kill, temp dir preserved", proc.pid)
                    kill_success = False

                # Verify owned container is empty
                container_empty = True
                if os.name == "nt" and job_handle:
                    # Windows Job Object verification
                    try:
                        if _job_has_active_processes(job_handle):
                            logger.warning("Job Object still has active processes for evaluation, temp dir preserved")
                            container_empty = False
                        # Close job handle to trigger KILL_ON_JOB_CLOSE if still open
                        try:
                            CloseHandle(job_handle)
                        except Exception:
                            pass
                    except Exception as e:
                        logger.warning("Job Object verification failed: %s", e)
                        container_empty = False
                else:
                    # Linux pgid verification
                    if pgid is not None:
                        if not _pgid_is_empty(pgid):
                            logger.warning("Process group %s still has live members, temp dir preserved", pgid)
                            container_empty = False
                    else:
                        # No pgid captured, conservative
                        logger.warning("PGID not captured for evaluation, temp dir preserved")
                        container_empty = False

                process_terminated = kill_success and container_empty
            else:
                process_terminated = True
        except Exception as e:
            logger.warning("Process termination verification failed: %s", e)
            process_terminated = False

        # Cleanup temp dir only if process tree is confirmed terminated
        if process_terminated:
            try:
                if os.path.isdir(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=False)
            except Exception as e:
                logger.warning("Failed to remove temp dir %s: %s", temp_dir, e)
        else:
            logger.warning("Skipping temp dir cleanup for %s because evaluator process tree may still be running", temp_dir)


def _kill_process_tree(proc: subprocess.Popen, pgid: Optional[int] = None) -> bool:
    """Terminate process tree safely. Returns True if termination confirmed."""
    kill_success = False
    try:
        if os.name == "nt":
            # Windows termination is handled by Job Object KILL_ON_JOB_CLOSE
            # No taskkill or global searches used
            kill_success = True
        else:
            # Kill process group using stored pgid if available
            target_pgid = pgid if pgid is not None else os.getpgid(proc.pid)
            os.killpg(target_pgid, signal.SIGKILL)
            kill_success = True
    except Exception as e:
        logger.warning("Failed to kill process tree for PID %s: %s", getattr(proc, "pid", "unknown"), e)
        kill_success = False
    # Wait for parent to exit to confirm tree termination signal was received
    try:
        proc.wait(timeout=5)
        return kill_success
    except subprocess.TimeoutExpired:
        logger.warning("Process PID %s did not exit after kill attempt", proc.pid)
        return False
    except Exception:
        return kill_success


def evaluate_strategy(code: str, task_info: Dict[str, Any], strategy_uuid: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Public entry point. Runs QuantCode-Bench evaluation best-effort.

    Returns dict with reward/metadata or None on unrecoverable error.
    Evaluation does not raise; failures are logged internally.
    """
    try:
        return _run_evaluator_subprocess(task_info, code, strategy_uuid)
    except Exception as e:
        logger.exception("QuantCode-Bench evaluation failed: %s", e)
        return {"error": "adapter_exception", "message": str(e)}
