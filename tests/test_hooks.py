"""Hooks: commands are argv lists, failures are reported, the hatch is scrubbed."""
from __future__ import annotations

import json
import os
import sys

import pytest

from core import hooks


def _write(root, payload):
    with open(os.path.join(str(root), hooks.HOOKS_FILE), "w",
              encoding="utf-8") as fh:
        json.dump(payload, fh)


def _echo(expr: str):
    return [sys.executable, "-c", expr]


def test_missing_file_means_no_hooks(workspace):
    assert hooks.load(str(workspace)) == []


def test_unknown_event_is_refused(workspace):
    _write(workspace, {"hooks": [{"event": "on_everything",
                                  "command": _echo("pass")}]})
    with pytest.raises(hooks.HookError, match="unknown event"):
        hooks.load(str(workspace))


def test_a_shell_string_is_not_a_command(workspace):
    _write(workspace, {"hooks": [{"event": "run_finished",
                                  "command": "echo hi; rm -rf /"}]})
    with pytest.raises(hooks.HookError, match="command"):
        hooks.load(str(workspace))


def test_unknown_top_level_key_is_refused(workspace):
    _write(workspace, {"hooks": [], "hook": []})
    with pytest.raises(hooks.HookError, match="unknown top-level"):
        hooks.load(str(workspace))


def test_a_hook_receives_the_event_payload(workspace):
    _write(workspace, {"hooks": [{
        "event": "run_finished",
        "command": _echo("import json,sys;print(json.load(sys.stdin)['event'])"),
    }]})
    outcomes = hooks.emit(str(workspace), "run_finished", {"report": "x"})
    assert outcomes[0]["returncode"] == 0
    assert outcomes[0]["stdout"].strip() == "run_finished"


def test_a_failing_hook_is_reported_not_raised(workspace):
    _write(workspace, {"hooks": [{
        "event": "run_finished",
        "command": _echo("import sys;sys.exit(3)"),
    }]})
    outcomes = hooks.emit(str(workspace), "run_finished", {})
    assert outcomes[0]["returncode"] == 3


def test_the_approval_hatch_is_scrubbed_from_a_hook(workspace, monkeypatch):
    monkeypatch.setenv("CHELATE_UNSAFE_AUTO_APPROVE", "1")
    monkeypatch.setenv("CHELATE_HUMAN", "1")
    _write(workspace, {"hooks": [{
        "event": "session_start",
        "command": _echo(
            "import os;print(os.environ.get('CHELATE_UNSAFE_AUTO_APPROVE',"
            "'absent'), os.environ.get('CHELATE_HUMAN','absent'))"),
    }]})
    outcomes = hooks.emit(str(workspace), "session_start", {})
    assert outcomes[0]["stdout"].split() == ["absent", "absent"]


def test_emit_refuses_an_unknown_event(workspace):
    with pytest.raises(hooks.HookError):
        hooks.emit(str(workspace), "nope", {})


def test_a_missing_executable_is_reported(workspace):
    _write(workspace, {"hooks": [{"event": "run_finished",
                                  "command": ["definitely-not-a-binary-xyz"]}]})
    outcomes = hooks.emit(str(workspace), "run_finished", {})
    assert outcomes[0]["returncode"] is None
    assert "error" in outcomes[0]
