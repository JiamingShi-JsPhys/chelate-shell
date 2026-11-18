"""Hooks — what may observe a run, and the three things hooks may not do.

Caller: `core/recipes.py` (recipe lifecycle events), `cli.py hook` (the entry
        point a host hook calls), and anything that wants to watch a pipeline.
Data schemas:
    Reads:  <workspace>/chelate.hooks.json
            {"hooks": [{"event": "recipe_finished",
                        "command": ["python", "scripts/notify.py"],
                        "timeout": 30}]}
    Writes: nothing. A hook's own writes are its own business and happen
            outside this module's authority.
Design:
    * `command` is a list of arguments, never a shell string. There is no
      `shell=True` anywhere here, so `;`, `|` and `$()` are not operators
      inside a hook — they are characters in an argument, or a refusal.
    * A hook cannot block anything. Its exit code is recorded and nothing
      else looks at it: gates are written by skills, promotion is decided by
      tokens, and neither reads this file.
    * A hook never receives the approval hatch. `CHELATE_UNSAFE_AUTO_APPROVE`
      (and the legacy `CHELATE_HUMAN`) are removed from the environment it
      runs with, so a hook that happens to call `pipeline` cannot inherit an
      approval it was never given.
    * Hooks run as the agent, in the workspace. They are for indexing,
      notifying and reporting — never for credentials, and never for writing
      `results/`.

An event that is not in `EVENTS` is refused at load time; a hook that fails
is reported in the return value, because a notification that silently did
nothing is worse than one that says it failed.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

HOOKS_FILE = "chelate.hooks.json"
EVENTS = (
    "run_started", "run_finished",
    "recipe_started", "recipe_step", "recipe_finished",
    "session_start", "session_stop",
)
_TOP_KEYS = {"hooks"}
_HOOK_KEYS = {"event", "command", "timeout"}
_MAX_TIMEOUT = 600
_SCRUBBED_ENV = ("CHELATE_UNSAFE_AUTO_APPROVE", "CHELATE_HUMAN")


class HookError(ValueError):
    """The hooks file is not something this module will run."""


def hooks_path(root: str) -> str:
    return os.path.join(os.path.abspath(root), HOOKS_FILE)


def load(root: str) -> List[Dict[str, Any]]:
    """Read the hooks file; a missing file means no hooks, not an error."""
    path = hooks_path(root)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise HookError(f"{HOOKS_FILE}: {exc}") from exc
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, list):
        raise HookError(f"{HOOKS_FILE}: expected an object with a 'hooks' list")
    unknown = set(data) - _TOP_KEYS
    if unknown:
        # A misspelled key is a hook that will never fire; refuse the file
        # rather than run half of what its author meant.
        raise HookError(f"{HOOKS_FILE}: unknown top-level key(s) {sorted(unknown)}")
    problems = validate(hooks)
    if problems:
        raise HookError("; ".join(problems))
    return hooks


def validate(hooks: List[Dict[str, Any]]) -> List[str]:
    """Every reason this hook list must be refused. Empty == runnable."""
    found: List[str] = []
    for index, hook in enumerate(hooks):
        where = f"hooks[{index}]"
        if not isinstance(hook, dict):
            found.append(f"{where}: not an object")
            continue
        unknown = set(hook) - _HOOK_KEYS
        if unknown:
            found.append(f"{where}: unknown key(s) {sorted(unknown)}")
        event = hook.get("event")
        if event not in EVENTS:
            found.append(f"{where}: unknown event {event!r}")
        command = hook.get("command")
        if (not isinstance(command, list) or not command
                or not all(isinstance(part, str) and part for part in command)):
            found.append(f"{where}: command must be a non-empty list of strings")
        timeout = hook.get("timeout", 30)
        if not isinstance(timeout, int) or not 1 <= timeout <= _MAX_TIMEOUT:
            found.append(f"{where}: timeout must be an integer in 1..{_MAX_TIMEOUT}")
    return found


def _environment() -> Dict[str, str]:
    env = dict(os.environ)
    for name in _SCRUBBED_ENV:
        env.pop(name, None)
    return env


def emit(root: str, event: str,
         payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Run every hook registered for *event*; report each outcome.

    Never raises for a failing hook: the caller is a run that has real work
    to finish, and a notification is not worth aborting it. A hooks file that
    is invalid *does* raise — that is a configuration error the user should
    see before they trust the events.
    """
    if event not in EVENTS:
        raise HookError(f"unknown event {event!r}")
    root = os.path.abspath(root)
    outcomes: List[Dict[str, Any]] = []
    body = json.dumps(dict(payload or {}, event=event, workspace=root),
                      ensure_ascii=False).encode("utf-8")
    for hook in load(root):
        if hook["event"] != event:
            continue
        record = {"event": event, "command": list(hook["command"])}
        try:
            done = subprocess.run(
                hook["command"], cwd=root, input=body,
                capture_output=True, timeout=hook.get("timeout", 30),
                env=_environment(), shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            record.update({"returncode": None,
                           "error": f"{exc.__class__.__name__}: {exc}"})
        else:
            record.update({
                "returncode": done.returncode,
                "stdout": done.stdout.decode("utf-8", "replace")[-2000:],
                "stderr": done.stderr.decode("utf-8", "replace")[-2000:],
            })
        outcomes.append(record)
    return outcomes
