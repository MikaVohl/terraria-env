"""Run a TerraBot program (Python using the `tb` library) in a sandboxed child interpreter.

The child is `python -I -S sandbox_boot.py` with a minimal environment, its own session (process group), resource
limits, and an audit hook that blocks network, process creation, native code and file access outside the workspace.
On Linux the child is additionally wrapped in `unshare -rn` (empty network namespace) when user namespaces work;
that namespace, not the audit hook, is the real network boundary.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

BOOT = Path(__file__).resolve().with_name("sandbox_boot.py")
TRACEBACK_LINES = 30
_netns: Optional[bool] = None


def network_namespace_available() -> bool:
    """True if `unshare -rn` works here (Linux with unprivileged user namespaces). Detected once per process."""
    global _netns
    if _netns is None:
        exe = shutil.which("unshare") if sys.platform.startswith("linux") else None
        try:
            _netns = bool(exe) and subprocess.run([exe, "-r", "-n", "true"], stdin=subprocess.DEVNULL,
                                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                  timeout=10).returncode == 0
        except (OSError, subprocess.SubprocessError):
            _netns = False
    return _netns


def _read_capped(f, max_output: int) -> str:
    """The whole file if it fits, else head + marker + tail (max_output bytes in total)."""
    size = f.seek(0, os.SEEK_END)
    f.seek(0)
    if size <= max_output:
        return f.read().decode("utf-8", "replace")
    half = max_output // 2
    head = f.read(half)
    f.seek(size - half)
    tail = f.read(half)
    marker = f"\n\n... [{size - 2 * half} bytes truncated] ...\n\n"
    return head.decode("utf-8", "replace") + marker + tail.decode("utf-8", "replace")


def _traceback_tail(stderr: str) -> str:
    i = stderr.rfind("Traceback (most recent call last):")
    text = stderr[i:] if i >= 0 else stderr
    return "\n".join(text.rstrip().splitlines()[-TRACEBACK_LINES:])


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_program(code: str, *, workspace: Path, socket_path: str, tb_dir: Path, timeout: float = 60.0,
                name: str = "program", max_output: int = 20000,
                cleanup: Optional[Callable[[], None]] = None) -> dict:
    """Write `code` to workspace/programs/<name>.py and run it sandboxed; `cleanup` runs after the child ends.

    Returns {name, exit ('ok'|'error'|'timeout'|'killed'), returncode, seconds, stdout, stderr, traceback_tail,
    network_namespace} (and cleanup_error if `cleanup` raised)."""
    if not name or os.sep in name or name.startswith(".") or (os.altsep and os.altsep in name):
        raise ValueError(f"invalid program name {name!r}")
    workspace = Path(workspace).resolve()
    programs = workspace / "programs"
    programs.mkdir(parents=True, exist_ok=True)
    program = programs / f"{name}.py"
    program.write_text(code, encoding="utf-8")

    cfg = {"workspace": str(workspace), "tb_dir": str(Path(tb_dir).resolve()), "socket": str(socket_path),
           "program": str(program), "cpu_seconds": int(timeout) + 5}
    cmd = [sys.executable, "-I", "-S", "-u", str(BOOT), json.dumps(cfg)]
    netns = network_namespace_available()
    if netns:
        cmd = [shutil.which("unshare"), "-r", "-n", "--"] + cmd
    env = {"TB_SOCKET": str(socket_path), "TB_STORE": str(workspace / "store.json"),
           "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(workspace),
           "LANG": os.environ.get("LANG", "C.UTF-8")}

    result = {"name": name, "network_namespace": netns}
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=env,
                                    cwd=str(workspace), start_new_session=True, close_fds=True)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(proc)
                proc.wait()
            except BaseException:  # e.g. KeyboardInterrupt in the harness: never leave the program running
                _kill_group(proc)
                proc.wait()
                raise
        finally:
            result["seconds"] = round(time.monotonic() - start, 3)
            if cleanup is not None:
                try:
                    cleanup()
                except Exception as e:  # report, but keep the program's result
                    result["cleanup_error"] = f"{type(e).__name__}: {e}"
        rc = proc.returncode
        result["stdout"] = _read_capped(out, max_output)
        result["stderr"] = _read_capped(err, max_output)

    result["returncode"] = rc
    if timed_out:
        result["exit"] = "timeout"
        result["stderr"] += f"\n[sandbox] killed after the {timeout:g} s time limit\n"
    elif rc == 0:
        result["exit"] = "ok"
    elif rc < 0:
        result["exit"] = "killed"
        try:
            sig = signal.Signals(-rc).name
        except ValueError:
            sig = str(-rc)
        result["stderr"] += f"\n[sandbox] killed by {sig} (CPU/memory/file-size limit or signal)\n"
    else:
        result["exit"] = "error"
    result["traceback_tail"] = "" if result["exit"] == "ok" else _traceback_tail(result["stderr"])
    return result
