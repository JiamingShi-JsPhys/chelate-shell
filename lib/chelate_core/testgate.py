"""test-gate's engine — run a declared test command and read its verdict.

Caller: skills/test-gate/run.py.

Data schemas:
    Reads:  <workspace>/.chelate/test-gate.json
                {"command": ["python", "-m", "pytest", "-q"], "timeout": 120}
            or the same object given inline with --command.
    Writes: nothing here; the adapter writes process/test_report_*.json.

Design — four rules, in the order they matter.

    **The command is an argument list, never a string.** No shell is
    involved, so a semicolon inside a test name stays a character in an
    argument instead of becoming an operator. The first element still goes
    through core.sandbox's executable whitelist, because the declaration
    lives in the workspace and the workspace is where an agent writes.

    **A green exit code is not a green test run.** `unittest` exits 0 after
    collecting nothing, pytest's exit code for "no tests ran" depends on
    how it was invoked, and a wrapper script exits with whatever it chose.
    "no tests ran", "collected 0 items" and "Ran 0 tests" are therefore
    UNVERIFIED: the pipeline is not told "tests pass" by a command that
    never ran one.

    **A red summary beats a green exit code.** When the output counts
    failures, that count wins over rc, so a wrapper that swallows its
    child's status cannot turn a failing run into a PASS.

    **Time out to UNVERIFIED, not FAIL.** A suite slower than its declared
    budget says nothing about the code; FAIL would blame the author for a
    limit this gate chose.

Layering note: `core.sandbox` is imported inside `run()` rather than at
module scope. The documented dependency direction is
`skills -> lib/chelate_core -> third-party`, and the whitelist must still
have exactly one implementation — importing it lazily keeps both true.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_CONFIG = os.path.join(".chelate", "test-gate.json")
DEFAULT_TIMEOUT = 110
MAX_CAPTURE = 64 * 1024
# Same pair the hook runner scrubs: a declaration must not be able to
# inherit this session's approval hatch into the code it just launched.
_SCRUBBED_ENV = ("CHELATE_UNSAFE_AUTO_APPROVE", "CHELATE_HUMAN")

_NO_TESTS = ("no tests ran", "collected 0 items", "ran 0 tests",
             "0 tests in ")
_COUNT = re.compile(
    r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)", re.IGNORECASE)
_OK_LINE = re.compile(r"^OK(\s*\(.*\))?$", re.MULTILINE)
_FAILED_LINE = re.compile(r"^FAILED\s*\((.*)\)$", re.MULTILINE)


class TestGateError(ValueError):
    """The declaration is unusable or the command cannot be started."""


# --------------------------------------------------------------------------
# the declaration
# --------------------------------------------------------------------------

def parse_command(value: Any) -> List[str]:
    """Turn a declaration value into an argv list — or refuse it.

    A string is accepted only when it is a JSON array. Accepting prose
    ("pytest -q tests/") would mean splitting it ourselves, and the one
    thing worse than a shell is a hand-rolled imitation of one.
    """
    if isinstance(value, (list, tuple)):
        parts = [str(item) for item in value]
    elif isinstance(value, str):
        text = value.strip()
        if not text.startswith("["):
            raise TestGateError(
                'command must be a JSON array of arguments, e.g. '
                '["python", "-m", "pytest", "-q"] — a plain string would '
                'need a shell to split it')
        try:
            decoded = json.loads(text)
        except ValueError as exc:
            raise TestGateError(f"command is not valid JSON: {exc}")
        parts = [str(item) for item in decoded]
    else:
        raise TestGateError(f"command must be a list, not {type(value).__name__}")
    if not parts or not parts[0]:
        raise TestGateError("command is empty")
    return parts


def _timeout_of(value: Any, fallback: int) -> int:
    if value in (None, ""):
        return fallback
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        raise TestGateError(f"timeout must be whole seconds, not {value!r}")
    if seconds <= 0:
        raise TestGateError(f"timeout must be positive, not {seconds}")
    return seconds


def load_declaration(root: str, path: Optional[str] = None) -> Dict[str, Any]:
    """Read `.chelate/test-gate.json` (or an explicit path) from the workspace."""
    target = path or os.path.join(root, DEFAULT_CONFIG)
    if not os.path.isfile(target):
        if path:
            raise TestGateError(f"config not found: {target}")
        raise TestGateError(
            f"no test command declared; write {DEFAULT_CONFIG} in the "
            f'workspace as {{"command": ["python", "-m", "pytest", "-q"]}} '
            f"or pass --command")
    try:
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise TestGateError(f"cannot read {target}: {exc}")
    except ValueError as exc:
        raise TestGateError(f"{target} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise TestGateError(f"{target} must hold a JSON object")
    unknown = set(data) - {"command", "timeout"}
    if unknown:
        raise TestGateError(
            f"{target} has unknown key(s) {sorted(unknown)}; a declaration "
            f"is a command and a timeout, nothing else")
    return {"command": parse_command(data.get("command")),
            "timeout": _timeout_of(data.get("timeout"), DEFAULT_TIMEOUT),
            "source": target}


def resolve(root: str, command: Optional[str] = None,
            config: Optional[str] = None,
            timeout: Optional[int] = None) -> Dict[str, Any]:
    """Merge --command / --config / --timeout over the declaration file."""
    declaration: Dict[str, Any] = {"command": [], "timeout": DEFAULT_TIMEOUT,
                                   "source": "--command"}
    if command:
        declaration["command"] = parse_command(command)
    else:
        declaration = load_declaration(root, config or None)
    if timeout:
        declaration["timeout"] = _timeout_of(timeout, DEFAULT_TIMEOUT)
    return declaration


# --------------------------------------------------------------------------
# reading the output
# --------------------------------------------------------------------------

def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1][:240] if lines else ""


def summarise(text: str) -> Dict[str, Any]:
    """Count what the output says, without trusting any single line."""
    # Normalise first: subprocess text mode gives CRLF on Windows, and a
    # trailing CR defeats every "$"-anchored pattern below.
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lowered = text.lower()
    counts: Dict[str, Any] = {"passed": 0, "failed": 0, "error": 0,
                              "skipped": 0}
    for raw_n, word in _COUNT.findall(lowered):
        key = word.lower().rstrip("s")
        if key in counts:
            counts[key] += int(raw_n)
    no_tests = any(marker in lowered for marker in _NO_TESTS)

    summary = ""
    for candidate in reversed([l.strip() for l in (text or "").splitlines()
                               if l.strip()]):
        low = candidate.lower()
        if "=" in candidate and any(word in low for word in
                                    ("passed", "failed", "error", "no tests ran")):
            summary = candidate.strip("= ").strip()[:200]
            break
    if not summary:
        failed_line = _FAILED_LINE.search(text or "")
        if failed_line:
            summary = f"FAILED ({failed_line.group(1)})"[:200]
        elif _OK_LINE.search(text or ""):
            summary = "OK"
    framework = ""
    if summary == "OK" or summary.startswith("FAILED ("):
        framework = "unittest"
    elif summary or counts["passed"] or counts["failed"] or no_tests:
        framework = "pytest"
    counts.update({"no_tests": no_tests, "summary": summary,
                   "framework": framework})
    return counts


# --------------------------------------------------------------------------
# running it
# --------------------------------------------------------------------------

def run(root: str, argv: Sequence[str], timeout: int = DEFAULT_TIMEOUT,
        cwd: Optional[str] = None) -> Dict[str, Any]:
    """Execute the declared command; never raises for a failing test run."""
    from core.sandbox import check_command  # lazy: see the layering note

    command = check_command(list(argv))
    workdir = os.path.abspath(cwd or root)
    if not os.path.isdir(workdir):
        raise TestGateError(f"cwd is not a directory: {workdir}")
    env = dict(os.environ)
    for name in _SCRUBBED_ENV:
        env.pop(name, None)
    env.setdefault("PYTHONIOENCODING", "utf-8")

    started = time.monotonic()
    try:
        proc = subprocess.run(command, cwd=workdir, capture_output=True,
                              text=True, timeout=timeout, env=env, shell=False)
        stdout, stderr, rc, timed_out = (proc.stdout or "", proc.stderr or "",
                                         proc.returncode, False)
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = _as_text(exc.stdout), _as_text(exc.stderr)
        rc, timed_out = -1, True
    except OSError as exc:
        raise TestGateError(f"cannot start {command[0]!r}: {exc}")
    return {"command": command, "rc": rc, "timed_out": timed_out,
            "seconds": round(time.monotonic() - started, 3),
            "stdout": stdout[-MAX_CAPTURE:], "stderr": stderr[-MAX_CAPTURE:],
            "cwd": workdir}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def verdict(outcome: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """Map one run onto the gate contract. Ordered, so the cases cannot overlap."""
    counts = summarise(outcome["stdout"])
    detail = counts["summary"] or _last_line(outcome["stderr"]) \
        or _last_line(outcome["stdout"]) or "no output"
    data = {"command": outcome["command"], "cwd": outcome.get("cwd"),
            "rc": outcome["rc"], "seconds": outcome["seconds"],
            "timed_out": outcome["timed_out"],
            "passed": counts["passed"], "failed": counts["failed"],
            "errors": counts["error"], "skipped": counts["skipped"],
            "summary": counts["summary"],
            "framework": counts["framework"] or "unknown"}

    if outcome["timed_out"]:
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": (f"timed out after {timeout}s: the suite's result "
                           f"is unknown, which is not a failure of the code"),
                "data": data}
    if counts["no_tests"]:
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": (f"the command ran but collected no tests "
                           f"({detail}); a green exit code with nothing run "
                           f"is not a pass"),
                "data": data}
    if counts["failed"] or counts["error"]:
        return {"status": "FAIL", "evidence_level": "EXACT",
                "reason": (f"{counts['passed']} passed, {counts['failed']} "
                           f"failed, {counts['error']} error(s) — {detail}"),
                "data": data}
    if outcome["rc"] != 0:
        return {"status": "FAIL", "evidence_level": "EXACT",
                "reason": f"command exited {outcome['rc']}: {detail}",
                "data": data}
    counted = counts["passed"] or counts["skipped"]
    if not counted:
        # The same rule as "no tests ran", one step weaker: a zero exit with
        # nothing readable is not evidence that a test ran. Saying PASS here
        # would make the gate's headline claim untrue for a command that
        # merely succeeded.
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": (f"the command exited 0 but printed no test summary "
                           f"this gate recognises ({detail}); a successful "
                           f"exit is not evidence that a test ran"),
                "data": data}
    return {"status": "PASS", "evidence_level": "EXACT",
            "reason": (f"{counts['passed']} passed, {counts['skipped']} "
                       f"skipped in {outcome['seconds']}s — {detail}"),
            "data": data}


def report(outcome: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """The verdict plus the evidence a later reader needs to check it."""
    result = verdict(outcome, timeout)
    result["timeout"] = timeout
    result["stdout_tail"] = _tail_lines(outcome["stdout"], 40)
    result["stderr_tail"] = _tail_lines(outcome["stderr"], 20)
    return result


def _tail_lines(text: str, count: int) -> List[str]:
    lines = [line.rstrip() for line in (text or "").splitlines() if line.strip()]
    return lines[-count:]
