"""Sandboxed code execution for practice problems.

Defense in depth for running user + AI-generated test code on the host:
  1. Hard wall-clock timeout (kills runaway loops).
  2. POSIX resource limits (CPU seconds, file size, process count).
  3. macOS `sandbox-exec` profile that DENIES all network and restricts writes
     to the throwaway work dir. Reads are allowed (interpreters need many files).

This is a personal, single-user, auth-gated tool — not a hostile multi-tenant
runner — but the above stops the realistic failure modes (infinite loops,
runaway memory/forks, and any network callback/exfiltration).
"""
from __future__ import annotations

import json
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

RESULT_MARKER = "PREPPILOT_RESULT:"
OUTPUTS_MARKER = "PREPPILOT_OUTPUTS:"
# Go can't be concatenated (single package/import block), so the driver is a full
# program with this marker line where the user's function is substituted in.
USER_CODE_MARKER = "//__PREPPILOT_USER_CODE__"

# Discover interpreters (node may live outside PATH under launchd).
_NODE_CANDIDATES = [
    shutil.which("node"),
    os.path.expanduser("~/.local/node/bin/node"),
    "/usr/local/bin/node",
    "/opt/homebrew/bin/node",
]


def _node_bin() -> str | None:
    for c in _NODE_CANDIDATES:
        if c and Path(c).exists():
            return c
    return None


_GO_CANDIDATES = [
    shutil.which("go"),
    os.path.expanduser("~/.local/go/bin/go"),
    "/usr/local/go/bin/go",
    "/opt/homebrew/bin/go",
]


def _go_bin() -> str | None:
    for c in _GO_CANDIDATES:
        if c and Path(c).exists():
            return c
    return None


_GOIMPORTS_CANDIDATES = [
    shutil.which("goimports"),
    os.path.expanduser("~/.local/bin/goimports"),
    os.path.expanduser("~/go/bin/goimports"),
]


def _goimports_bin() -> str | None:
    for c in _GOIMPORTS_CANDIDATES:
        if c and Path(c).exists():
            return c
    return None


def _fix_go_imports(src_file: Path, workdir: str) -> None:
    """Run goimports to add missing / remove unused imports (Go is strict on both).

    Runs on the host (trusted analysis tool; needs `go` on PATH). Best-effort.
    """
    gi = _goimports_bin()
    go = _go_bin()
    if not gi or not go:
        return
    env = {"PATH": f"{os.path.dirname(go)}:/usr/bin:/bin", "HOME": workdir}
    env.update(_go_env(workdir))
    try:
        subprocess.run([gi, "-w", str(src_file)], env=env, timeout=20,
                       capture_output=True, text=True)
    except (subprocess.SubprocessError, OSError):
        pass


import sys

LANGS = {
    "python": {"ext": "py", "cmd": lambda f: [sys.executable, "-I", f], "timeout": 6.0},
    "javascript": {"ext": "js", "cmd": lambda f: [_node_bin() or "node", f], "timeout": 8.0},
    "go": {"ext": "go", "cmd": lambda f: [_go_bin() or "go", "run", f], "timeout": 25.0,
           "assemble": "substitute"},
}


def default_timeout(language: str) -> float:
    return LANGS.get(language, {}).get("timeout", 8.0)


def _go_env(workdir: str) -> dict:
    return {
        "GO111MODULE": "off", "GOFLAGS": "-mod=mod", "GOPROXY": "off",
        "GOCACHE": f"{workdir}/.gocache", "GOPATH": f"{workdir}/.gopath",
        "GOTMPDIR": workdir, "CGO_ENABLED": "0",
    }

_SANDBOX_PROFILE = """(version 1)
(deny default)
(allow process-fork)
(allow process-exec)
(allow sysctl-read)
(allow mach-lookup)
(allow file-read*)
(allow file-write* (subpath "{work}") (subpath "{work_raw}") (subpath "/private/tmp") (subpath "/tmp")
    (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))
(deny network*)
"""


def _preexec() -> None:
    # New session so we can kill the whole process tree on timeout (Go's `go run`
    # execs a separate binary that would otherwise orphan).
    os.setsid()
    # Best-effort caps (some are no-ops on macOS). NOTE: no RLIMIT_NPROC — it is
    # per-USER on macOS, not per-job, so it would break multi-process runtimes.
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (12, 14))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024 * 1024,) * 2)
    except (ValueError, OSError):
        pass


def language_available(language: str) -> bool:
    if language == "javascript":
        return _node_bin() is not None
    if language == "go":
        return _go_bin() is not None
    return language == "python"


def run_code(language: str, source: str, *, timeout: float = 6.0, sandbox: bool = True) -> dict:
    """Execute `source` and capture output. Returns a result dict."""
    if language not in LANGS:
        return {"ok": False, "error": f"Unsupported language: {language}"}
    if not language_available(language):
        return {"ok": False, "error": f"{language} runtime not available on this host"}

    spec = LANGS[language]
    workdir = tempfile.mkdtemp(prefix="prep_run_")
    src_file = Path(workdir) / f"main.{spec['ext']}"
    src_file.write_text(source)

    if language == "go":
        _fix_go_imports(src_file, workdir)

    cmd = spec["cmd"](str(src_file))
    if sandbox and shutil.which("sandbox-exec"):
        # macOS canonicalizes /var/folders -> /private/var/folders; sandbox matches
        # the resolved path, so allow the realpath (plus the raw path for safety).
        real_work = os.path.realpath(workdir)
        profile = _SANDBOX_PROFILE.format(work=real_work, work_raw=workdir)
        cmd = ["sandbox-exec", "-p", profile] + cmd

    env = {"PATH": "/usr/bin:/bin", "HOME": workdir, "TMPDIR": workdir}
    if language == "go":
        env.update(_go_env(workdir))

    start = time.monotonic()
    timed_out = False
    proc = subprocess.Popen(
        cmd, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, preexec_fn=_preexec, env=env,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        stdout, stderr = proc.communicate()
        stderr = (stderr or "") + f"\n[killed: exceeded {timeout:.0f}s time limit]"
        code = -1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    duration_ms = int((time.monotonic() - start) * 1000)
    return {
        "ok": (not timed_out) and code == 0,
        "timed_out": timed_out,
        "exit_code": code,
        "stdout": stdout[-8000:],
        "stderr": stderr[-4000:],
        "duration_ms": duration_ms,
    }


def run_capture(language: str, solution_code: str, driver_code: str, *, timeout: float | None = None) -> dict:
    """Run solution + driver; parse the driver's PREPPILOT_OUTPUTS line.

    Python/JS: the driver is appended after the solution (shared scope).
    Go: the driver is a full program; the solution is substituted at USER_CODE_MARKER.
    The driver defines test inputs + a normalizer, calls the entry function per input,
    and prints:  PREPPILOT_OUTPUTS:{"labels":[...],"outputs":[...]}  (or {"__error__"} per case).
    """
    if timeout is None:
        timeout = default_timeout(language)
    if LANGS.get(language, {}).get("assemble") == "substitute":
        if USER_CODE_MARKER in driver_code:
            combined = driver_code.replace(USER_CODE_MARKER, solution_code)
        else:  # fallback: prepend the solution
            combined = solution_code + "\n" + driver_code
    else:
        sep = "//" if language == "javascript" else "#"
        combined = solution_code + f"\n\n{sep} ==== PrepPilot driver ====\n" + driver_code
    res = run_code(language, combined, timeout=timeout)
    captured = None
    for line in res["stdout"].splitlines():
        if line.startswith(OUTPUTS_MARKER):
            try:
                captured = json.loads(line[len(OUTPUTS_MARKER):])
            except json.JSONDecodeError:
                captured = None
    res["captured"] = captured
    res["stdout"] = "\n".join(
        ln for ln in res["stdout"].splitlines() if not ln.startswith(OUTPUTS_MARKER)
    )
    return res
