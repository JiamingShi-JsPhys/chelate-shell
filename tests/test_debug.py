"""Tests for the unified debug layer (lib/chelate_core/debug.py + wiring).

Covers:
    * enabled()/enable()/flag() switch semantics
    * adapter.dispatch emits [chelate:debug] lines on stderr when
      CHELATE_DEBUG=1, and stays silent otherwise
    * cli --debug sets CHELATE_DEBUG so skill subprocesses inherit it
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from lib.chelate_core import adapter, debug  # noqa: E402
from core import router as router_module  # noqa: E402


# --------------------------------------------------------------------------
# switch semantics
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("", False), ("no", False),
])
def test_enabled_parses_truthy_values(value, expected):
    assert debug.enabled({"CHELATE_DEBUG": value}) is expected


def test_enabled_defaults_to_os_environ(monkeypatch):
    monkeypatch.setenv("CHELATE_DEBUG", "1")
    assert debug.enabled() is True
    monkeypatch.delenv("CHELATE_DEBUG", raising=False)
    assert debug.enabled() is False


def test_flag_sets_environment_for_children(monkeypatch):
    monkeypatch.setenv("CHELATE_DEBUG", "")  # tracked, so enable() is reverted
    assert debug.flag(True) is True
    assert os.environ["CHELATE_DEBUG"] == "1"


def test_flag_false_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("CHELATE_DEBUG", "yes")
    assert debug.flag(False) is True
    monkeypatch.delenv("CHELATE_DEBUG", raising=False)
    assert debug.flag(False) is False


# --------------------------------------------------------------------------
# adapter wiring
# --------------------------------------------------------------------------

def _dispatch(tmp_path, monkeypatch, capsys, env_value=None):
    if env_value is None:
        monkeypatch.delenv("CHELATE_DEBUG", raising=False)
    else:
        monkeypatch.setenv("CHELATE_DEBUG", env_value)

    def configure(ap):
        ap.add_argument("--input", default="draft.md")

    def handler(args):
        return {"status": "PASS", "evidence_level": "EXACT",
                "reason": "debug smoke test"}

    rc = adapter.dispatch("debug-smoke", configure, {"check": handler},
                          argv=["--root", str(tmp_path), "--action", "check"])
    out, err = capsys.readouterr()
    return rc, out, err


def test_adapter_debug_logs_gate_to_stderr(tmp_path, monkeypatch, capsys):
    rc, out, err = _dispatch(tmp_path, monkeypatch, capsys, env_value="1")
    assert rc == 0
    assert "[chelate:debug]" in err
    assert "debug-smoke: running handler handler" in err
    assert "gate ->" in err
    # stdout keeps the single contract JSON line, unpolluted by debug output
    lines = [l for l in out.strip().splitlines() if l.strip()]
    assert len(lines) == 1 and lines[0].startswith("{")


def test_adapter_silent_without_debug(tmp_path, monkeypatch, capsys):
    rc, out, err = _dispatch(tmp_path, monkeypatch, capsys, env_value=None)
    assert rc == 0
    assert "[chelate:debug]" not in err
    assert "[chelate:debug]" not in out


def test_adapter_debug_logs_stage_action_alias(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHELATE_DEBUG", "1")

    def handler(args):
        return {"status": "PASS", "evidence_level": "EXACT", "reason": "ok"}

    rc = adapter.dispatch("debug-alias", None, {"check": handler},
                          argv=["--root", str(tmp_path), "--action", "gate"])
    _, err = capsys.readouterr()
    assert rc == 0
    assert "stage action 'gate' -> 'check'" in err


# --------------------------------------------------------------------------
# cli wiring
# --------------------------------------------------------------------------

def test_cli_debug_flag_sets_environment(monkeypatch):
    import cli
    monkeypatch.setenv("CHELATE_DEBUG", "")  # tracked, so enable() is reverted
    parser = cli.build_parser()
    args = parser.parse_args(["run", "data-profiler", "--root", ".", "--debug"])
    # argparse.REMAINDER swallows the trailing --debug into args.args
    assert "--debug" in (args.args or [])
    skill_args = [a for a in (args.args or []) if a != "--debug"]
    assert debug.flag(args.debug or "--debug" in (args.args or [])) is True
    assert os.environ["CHELATE_DEBUG"] == "1"
    assert "--debug" not in skill_args


def test_cli_pipeline_debug_flag_reaches_router(monkeypatch):
    import cli
    monkeypatch.setenv("CHELATE_DEBUG", "")  # tracked, so enable() is reverted
    parser = cli.build_parser()
    args = parser.parse_args(["pipeline", "--root", ".", "--mode", "c",
                              "--selected", "data-profiler", "--debug"])
    assert args.debug is True

    captured = {}

    def fake_run(root, **kwargs):
        captured.update(kwargs)
        return {"terminated_by": None}

    monkeypatch.setattr(cli, "router_run", fake_run)
    assert cli.cmd_pipeline(args) == 0
    assert captured["debug"] is True
    assert os.environ.get("CHELATE_DEBUG") == "1"


def test_adapter_accepts_debug_flag_directly(tmp_path, monkeypatch, capsys):
    """python run.py --root X --action check --debug works (flag, not env)."""
    monkeypatch.setenv("CHELATE_DEBUG", "")  # tracked, so enable() is reverted

    def handler(args):
        return {"status": "PASS", "evidence_level": "EXACT", "reason": "ok"}

    rc = adapter.dispatch("debug-flag", None, {"check": handler},
                          argv=["--root", str(tmp_path), "--action", "check",
                                "--debug"])
    out, err = capsys.readouterr()
    assert rc == 0
    assert "[chelate:debug]" in err
    # the flag also flips the process-wide switch for later calls
    assert os.environ.get("CHELATE_DEBUG") == "1"
    assert len([l for l in out.strip().splitlines() if l.strip()]) == 1


# --------------------------------------------------------------------------
# router wiring — real run_skill path (the mock-based router tests never
# execute it, so this integration test is the only guard for debug plumbing)
# --------------------------------------------------------------------------

def test_router_run_skill_debug_logs_real_subprocess(tmp_path, monkeypatch,
                                                     capsys):
    import csv as _csv

    from core.registry import load_default_registry
    reg = load_default_registry()
    rec = reg.get("data-profiler")
    assert rec is not None, "data-profiler must be registered"

    csv_path = tmp_path / "tiny.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["x", "y"])
        w.writerow(["1", "2"])
        w.writerow(["3", "4"])

    monkeypatch.setenv("CHELATE_DEBUG", "")  # tracked, so enable() is reverted
    record = router_module.run_skill(rec, str(tmp_path), "gate",
                                     ["--input", str(csv_path)],
                                     timeout=120, debug=True)
    err = capsys.readouterr().err
    assert record["status"] == "PASS", record
    assert f"{rec.name}: exec " in err
    assert f"{rec.name}: rc=" in err
    assert "[chelate:debug]" in err
