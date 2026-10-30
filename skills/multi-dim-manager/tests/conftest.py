"""Shared fixtures and helpers for the multi-dim-manager test suite."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "multi-dim-manager"


def write_plugin(directory, kind: str = "ok") -> str:
    """Write a small fake compute plugin and return its command template.

    kind: ok | fail | error | silent | sleep
    The command honours the {PARAMS}/{OUT} placeholders and uses the same
    interpreter that runs the tests.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "plugin.py"
    if kind == "ok":
        body = (
            "import sys, json\n"
            "from pathlib import Path\n"
            "params = json.loads(Path(sys.argv[1]).read_text())\n"
            "Path(sys.argv[2]).write_text(json.dumps({'ok': True, 'n': len(params)}))\n"
            "raise SystemExit(0)\n"
        )
    elif kind == "fail":
        body = (
            "import sys, json\n"
            "from pathlib import Path\n"
            "params = json.loads(Path(sys.argv[1]).read_text())\n"
            "Path(sys.argv[2]).write_text(json.dumps({'ok': False}))\n"
            "raise SystemExit(1)\n"
        )
    elif kind == "error":
        body = "import sys\nraise SystemExit(2)\n"
    elif kind == "silent":
        body = "import sys\nraise SystemExit(0)\n"
    elif kind == "sleep":
        body = "import sys, time\ntime.sleep(2)\nraise SystemExit(0)\n"
    else:
        raise ValueError(f"unknown plugin kind {kind!r}")
    script.write_text(body, encoding="utf-8")
    return f"{sys.executable} {script} {{PARAMS}} {{OUT}}"


def make_config(path, *, space, critical_paths, plugin_cmd,
                timeout=None, auto_rollback=True, workdir=None, output=None):
    """Write a JSON experiment config and return its Path."""
    cfg = {
        "param_space": {"dimensions": space},
        "critical_paths": critical_paths,
        "plugin": {"command": plugin_cmd, "timeout": timeout},
        "auto_rollback": auto_rollback,
    }
    if workdir is not None:
        cfg["workdir"] = str(workdir)
    if output is not None:
        cfg["output"] = str(output)
    p = Path(path)
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


@pytest.fixture
def plugin_factory(tmp_path):
    """Return a callable that writes a plugin of a given kind in tmp_path."""
    return lambda kind="ok": write_plugin(tmp_path / "bin", kind)
