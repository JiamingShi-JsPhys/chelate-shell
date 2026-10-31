"""Sandbox tests: process isolation + 120-second circuit-breaker.

Two test cases:
    1. A fast command completes inside the child  -> status "PASS"
    2. An infinite loop hits the timeout           -> status "UNVERIFIED",
       timeout=True, returncode=-1

The timeout test uses a 2-second budget (not the 120-second default)
so the suite stays fast; the code path is identical.

Windows ``spawn`` safety: ``_worker`` is a module-level function, so the
child process can unpickle it without re-importing a running module.  The
tests explicitly set ``multiprocessing.set_start_method('spawn',
force=False)`` in a fixture so the spawn path is exercised on
Linux/macOS CI as well (where fork is the default).
"""
from __future__ import annotations

import multiprocessing as _mp
import sys

import pytest

from core.sandbox import (
    DEFAULT_TIMEOUT_SECONDS,
    _worker,
    missing_dependencies,
    run_sandboxed,
)


# ---------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def _spawn_context(monkeypatch):
    """Force the spawn start method so Windows-style pickling is
    exercised on every platform (fork on Linux/macOS would mask it)."""
    ctx = _mp.get_context("spawn")
    monkeypatch.setattr(_mp, "get_context", lambda *a, **k: ctx)
    return ctx


# ---------------------------------------------------------------- tests

def test_worker_exists_and_is_module_level():
    """_worker must be a plain module-level callable (no closure),
    otherwise the Windows spawn unpickle fails at import time."""
    assert callable(_worker)
    # __module__ must be 'core.sandbox' so the spawn child can re-import it
    assert _worker.__module__ == "core.sandbox"


def test_default_timeout_is_120_seconds():
    assert DEFAULT_TIMEOUT_SECONDS == 120


def test_missing_dependencies_detects_absent_module():
    """A clearly-nonexistent module must be flagged missing."""
    missing = missing_dependencies(["_this_module_does_not_exist_xyz_999"])
    assert "_this_module_does_not_exist_xyz_999" in missing


def test_run_sandboxed_normal_command_completes():
    """A trivially fast command (``python -c pass``) must PASS."""
    cmd = [sys.executable, "-c", "pass"]
    outcome = run_sandboxed(cmd, dependencies=[], timeout=30)
    assert outcome["status"] == "PASS", outcome
    assert outcome["timeout"] is False
    assert outcome["returncode"] == 0
    assert outcome["seconds"] > 0
    assert outcome["missing"] == []


def test_run_sandboxed_missing_dependency_short_circuits():
    """When a declared dependency is absent the sandbox must NOT launch
    a child process — it returns UNVERIFIED immediately with
    returncode=-2 and a degraded reason."""
    outcome = run_sandboxed(
        [sys.executable, "-c", "pass"],
        dependencies=["_this_module_does_not_exist_xyz_999"],
        timeout=30,
    )
    assert outcome["status"] == "UNVERIFIED", outcome
    assert outcome["timeout"] is False
    assert outcome["returncode"] == -2
    assert "missing dependencies" in outcome["reason"]
    assert "_this_module_does_not_exist_xyz_999" in outcome["missing"]
    # Must have returned before the timeout elapsed (no process was started)
    assert outcome["seconds"] < 5, outcome


def test_run_sandboxed_timeout_circuit_breaker():
    """An infinite loop must be killed by the circuit-breaker and
    reported as UNVERIFIED with timeout=True and returncode=-1."""
    # Use a 2-second budget; the code path is identical to the
    # 120-second default, just faster for the test suite.
    import time as _time
    # Run the child in the background so we don't block here;
    # run_sandboxed itself blocks on proc.join(timeout).
    cmd = [sys.executable, "-c", "import time; time.sleep(300)"]
    started = _time.monotonic()
    outcome = run_sandboxed(cmd, dependencies=[], timeout=2)
    elapsed = _time.monotonic() - started
    assert outcome["status"] == "UNVERIFIED", outcome
    assert outcome["timeout"] is True, outcome
    assert outcome["returncode"] == -1, outcome
    assert "timed out" in outcome["reason"], outcome
    assert outcome["seconds"] > 0
    # Sanity: the circuit-breaker must have triggered before the
    # infinite sleep finished (i.e. well under 300 s).
    assert elapsed < 60, f"elapsed={elapsed}s; circuit-breaker failed"


def test_run_sandboxed_child_crash_returns_unverified():
    """A child that exits with a non-zero code (e.g. ``python -c exit(1)``)
    must produce UNVERIFIED, not PASS or FAIL."""
    cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
    outcome = run_sandboxed(cmd, dependencies=[], timeout=30)
    assert outcome["status"] == "UNVERIFIED", outcome
    assert outcome["timeout"] is False
    assert outcome["returncode"] == 1, outcome


def test_run_sandboxed_non_zero_rc_from_worker():
    """When the subprocess inside _worker returns rc=2 the outcome must
    be UNVERIFIED with returncode=2 and a reason mentioning the failure."""
    cmd = [sys.executable, "-c", "import sys; sys.exit(2)"]
    outcome = run_sandboxed(cmd, dependencies=[], timeout=30)
    assert outcome["status"] == "UNVERIFIED", outcome
    assert outcome["timeout"] is False
    assert outcome["returncode"] == 2, outcome
    assert "sandbox child failed" in outcome["reason"], outcome


def test_worker_puts_result_on_queue():
    """Direct unit test of _worker: it must put a dict with 'rc' on the queue."""
    q = _mp.get_context("spawn").Queue()
    _worker([sys.executable, "-c", "pass"], q)
    report = q.get(timeout=5)
    assert report["rc"] == 0, report


def test_run_sandboxed_propagates_gate_failure_from_stdout():
    """A sandboxed skill that prints a FAIL gate JSON on stdout (and exits 0)
    must surface that FAIL verdict (with reason + artifacts) to the caller,
    not be collapsed into PASS by the exit code."""
    script = (
        "import sys, json; "
        "print(json.dumps({'status': 'FAIL', 'evidence_level': 'EMPIRICAL', "
        "'reason': 'intentional misfit', 'artifacts': ['/tmp/x.png']})); "
        "sys.exit(0)"
    )
    cmd = [sys.executable, "-c", script]
    outcome = run_sandboxed(cmd, dependencies=[], timeout=30)
    assert outcome["status"] == "FAIL", outcome
    assert outcome["evidence_level"] == "EMPIRICAL"
    assert outcome["reason"] == "intentional misfit"
    assert outcome["artifacts"] == ["/tmp/x.png"]
    assert outcome["timeout"] is False


def test_run_sandboxed_propagates_gate_unverified_from_stdout():
    """A degraded skill that prints an UNVERIFIED gate JSON must surface it."""
    script = (
        "import sys, json; "
        "print(json.dumps({'status': 'UNVERIFIED', 'evidence_level': "
        "'UNVERIFIED', 'reason': 'rdkit not installed', 'artifacts': []})); "
        "sys.exit(0)"
    )
    cmd = [sys.executable, "-c", script]
    outcome = run_sandboxed(cmd, dependencies=[], timeout=30)
    assert outcome["status"] == "UNVERIFIED", outcome
    assert outcome["reason"] == "rdkit not installed"
