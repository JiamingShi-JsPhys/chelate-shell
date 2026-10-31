"""Chelate Shell sandbox — true process-level isolation.

Caller: core/router.py for skills whose manifest declares
        ``sandbox_required: true`` (the heavy skills: rdkit,
        scikit-learn, matplotlib).
No existing file in chelate-shell-v1.1.0/ serves this purpose.
Data schemas:
    Reads:  a skill's dependency list (from SkillRecord.dependencies).
    Writes: none — the function below blocks on the child process and
            returns an outcome dict; the router folds it into the pipeline
            record as an UNVERIFIED gate.

Design (v1.2.0):
    * Every sandboxed skill runs in its own ``multiprocessing.Process``
      so a crash (segfault, OOM, recursive C call) cannot take the main
      pipeline down with it.
    * A 120-second circuit-breaker: when the child does not finish within
      ``DEFAULT_TIMEOUT_SECONDS`` the parent calls ``terminate()`` on
      Windows (a hard taskkill equivalent via the ``multiprocessing``
      API) and returns a structured ``UNVERIFIED`` result with a
      timeout reason, rather than letting a hung heavy dependency
      (rdkit on a pathological input, a matplotlib renderer stuck in a
      pathological layout)
      stall the whole pipeline indefinitely.
    * Windows spawn safety: the child target is a *top-level* module
      function (``_child_target``) — never a closure or lambda — so the
      child process can be unpickled under the Windows ``spawn``
      start method without re-importing a module that was running in
      the parent.

Compatibility note: the ``resolve_environment`` helper from v1.1.x is
retained unchanged so the non-sandboxed path in router.py keeps working;
new code calls ``run_sandboxed`` when ``sandbox_required`` is true.
"""
from __future__ import annotations

import importlib.util
import json
import multiprocessing as _mp
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

DEFAULT_TIMEOUT_SECONDS = 120

# Pickle-friendly: must be importable at module level, not a closure.
_CHILD_TARGET: str = "_child_target"


@dataclass
class SandboxDecision:
    """Outcome of resolving an execution environment for one skill.

    Retained for backward compatibility with the v1.1.x router path.
    """

    interpreter: str
    extra_pythonpath: List[str] = field(default_factory=list)
    degraded: bool = False
    missing: List[str] = field(default_factory=list)

    def env(self) -> Dict[str, str]:
        extra = os.pathsep.join(self.extra_pythonpath) if self.extra_pythonpath else ""
        base = os.environ.get("PYTHONPATH", "")
        combined = os.pathsep.join(p for p in [extra, base] if p)
        return {**os.environ, "PYTHONPATH": combined}


def missing_dependencies(names: List[str]) -> List[str]:
    """Return the subset of ``names`` that cannot be imported in this env."""
    out: List[str] = []
    for n in names:
        if importlib.util.find_spec(n) is None:
            out.append(n)
    return out


def resolve_environment(dependencies: List[str],
                        interpreter: Optional[str] = None) -> SandboxDecision:
    """Pick interpreter + env for a *non-sandboxed* skill (v1.1.x path).

    Returns the main interpreter with a ``degraded`` flag when a dependency
    is absent, so the router can run the skill as-is and let it degrade to
    an UNVERIFIED gate.
    """
    interp = interpreter or sys.executable
    missing = missing_dependencies(dependencies)
    return SandboxDecision(interpreter=interp, degraded=bool(missing),
                           missing=missing)


def _parse_stdout(stdout: str):
    """Best-effort extraction of the last JSON object a skill printed.

    Delegates to the adapter toolkit's single implementation so the two
    call sites (router, sandbox) can never drift apart.
    """
    from lib.chelate_core.adapter import last_json
    return last_json(stdout)


def _worker(cmd: List[str], q: "_mp.Queue") -> None:
    """Top-level target for the sandbox child process.

    Defined at module level (not a closure) so it survives the Windows
    ``spawn`` pickle boundary. Runs ``cmd`` as a subprocess and reports the
    exit code *and* the captured stdout/stderr back to the parent via ``q``.
    """
    import sys
    try:
        rc = 0
        stdout = ""
        stderr = ""
        if cmd:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            rc = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
        q.put({"rc": rc, "stdout": stdout, "stderr": stderr})
    except Exception as e:
        q.put({"rc": -1, "error": f"{type(e).__name__}: {e}",
               "stdout": "", "stderr": ""})


def run_sandboxed(cmd: List[str],
                  dependencies: List[str],
                  timeout: int = DEFAULT_TIMEOUT_SECONDS,
                  env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Run ``cmd`` in an isolated ``multiprocessing.Process``.

    Returns a dict shaped like the router's pipeline record:

        {
            "status": "PASS" | "FAIL" | "UNVERIFIED",
            "evidence_level": "UNVERIFIED",
            "reason": "...",
            "returncode": int | -1 (timeout) | -2 (crash),
            "timeout": bool,
            "missing": [...],
            "seconds": float,
        }

    The 120-second circuit-breaker is the *timeout* parameter default;
    callers can override it per-skill via the router's ``--timeout`` flag.
    """
    import time
    started = time.time()

    # 1. Pre-check dependencies in the *parent* interpreter.
    missing = missing_dependencies(dependencies)
    if missing:
        return {
            "status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
            "reason": f"degraded: missing dependencies {missing}",
            "returncode": -2, "timeout": False,
            "missing": missing,
            "seconds": round(time.time() - started, 3),
        }

    # 2. Launch the isolated process (Windows spawn-safe).
    ctx = _mp.get_context()
    q = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(list(cmd), q), daemon=True)
    proc.start()
    proc.join(timeout)

    # 3. Evaluate the outcome.
    elapsed = time.time() - started
    if proc.is_alive():
        # Circuit-breaker: force-terminate the child.
        proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
        return {
            "status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
            "reason": (f"skill timed out after {timeout}s; "
                       f"sandbox process force-terminated"),
            "returncode": -1, "timeout": True,
            "missing": [],
            "seconds": round(elapsed, 3),
        }

    if proc.exitcode not in (0, None):
        return {
            "status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
            "reason": (f"sandbox child exited unexpectedly "
                       f"(exitcode={proc.exitcode})"),
            "returncode": proc.exitcode, "timeout": False,
            "missing": [],
            "seconds": round(elapsed, 3),
        }

    # 4. Collect the worker's report from the queue.
    try:
        report = q.get(timeout=2)
    except Exception:
        report = {"rc": 0, "stdout": "", "stderr": ""}
    rc = report.get("rc", 0)
    stdout = report.get("stdout", "")
    # Trust the skill's own verdict when it printed a gate JSON on stdout.
    # The adapter layer (lib/chelate_core/adapter.py) prints one JSON line
    # carrying the gate verdict; parsing it here lets a heavy gate skill
    # actually hard-block the pipeline on FAIL (and surface its reason and
    # artifacts) instead of the sandbox collapsing every outcome onto the
    # child's exit code.
    payload = _parse_stdout(stdout)
    if payload and isinstance(payload, dict) and "status" in payload:
        return {
            "status": payload["status"],
            "evidence_level": payload.get("evidence_level", "UNVERIFIED"),
            "reason": payload.get("reason", ""),
            "artifacts": list(payload.get("artifacts", []) or []),
            "returncode": rc, "timeout": False, "missing": [],
            "seconds": round(elapsed, 3),
        }
    if rc == 0:
        return {
            "status": "PASS", "evidence_level": "UNVERIFIED",
            "reason": "sandbox child completed successfully",
            "returncode": 0, "timeout": False,
            "missing": [],
            "artifacts": [],
            "seconds": round(elapsed, 3),
        }
    err = report.get("error", "")
    return {
        "status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
        "reason": f"sandbox child failed (rc={rc}){': ' + err if err else ''}",
        "returncode": rc, "timeout": False,
        "missing": [],
        "artifacts": [],
        "seconds": round(elapsed, 3),
    }


def run_skill_sandboxed(rec, root: str, action: str, extra_args: List[str],
                        timeout: int = DEFAULT_TIMEOUT_SECONDS,
                        debug: bool = False) -> Dict[str, Any]:
    """Sandboxed replacement for router.run_skill's subprocess call.

    Builds the same command as the v1.1.x path but executes it inside a
    ``multiprocessing.Process`` with a 120-second circuit-breaker.
    Intended for skills with ``sandbox_required: true``.
    """
    from core.router import _REPO_ROOT  # local import to avoid a cycle
    cmd = [sys.executable, rec.run_path, "--root", root, "--action", action]
    cmd += list(extra_args)
    return run_sandboxed(cmd, rec.dependencies, timeout=timeout)

