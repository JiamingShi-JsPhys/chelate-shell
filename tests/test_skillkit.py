"""Scaffolding, linting and the doctor census."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from core import skillkit


def _repo_cli(*args, cwd=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "cli.py", *args],
        cwd=cwd or os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True, text=True, encoding="utf-8", env=env)


# --------------------------------------------------------------------------
# skill new
# --------------------------------------------------------------------------

def test_new_writes_the_mechanical_half(tmp_path):
    report = skillkit.new("sample-gate", "gates", root=str(tmp_path))
    folder = tmp_path / "skills" / "sample-gate"
    assert sorted(report["written"]) == ["LICENSE", "README.md", "SKILL.md",
                                         "manifest.json", "run.py"]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "sample-gate"
    assert manifest["stage"] == "gates"
    assert manifest["entrypoint"] == "run.py"
    assert (folder / "run.py").is_file()


def test_new_refuses_a_name_that_would_break_the_routing_table(tmp_path):
    for bad in ("Sample", "with space", "-leading", "a"):
        with pytest.raises(skillkit.SkillKitError):
            skillkit.new(bad, "gates", root=str(tmp_path))


def test_new_refuses_an_unknown_stage(tmp_path):
    with pytest.raises(skillkit.SkillKitError) as exc:
        skillkit.new("sample", "nonsense", root=str(tmp_path))
    assert "stage must be one of" in str(exc.value)


def test_new_refuses_to_overwrite(tmp_path):
    skillkit.new("sample-gate", "gates", root=str(tmp_path))
    with pytest.raises(skillkit.SkillKitError) as exc:
        skillkit.new("sample-gate", "gates", root=str(tmp_path))
    assert "already exists" in str(exc.value)


# --------------------------------------------------------------------------
# skill lint
# --------------------------------------------------------------------------

def test_lint_names_what_a_release_would_discover(tmp_path):
    skillkit.new("sample-gate", "gates", root=str(tmp_path))
    folder = tmp_path / "skills" / "sample-gate"
    (folder / "LICENSE").unlink()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["name"] = "other-name"
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = skillkit.lint(str(tmp_path))
    problems = " | ".join(item["problem"] for item in report["problems"])
    assert "missing LICENSE" in problems
    assert "!= folder" in problems
    assert report["ok"] is False


def test_the_shipped_tree_lints_clean():
    report = skillkit.lint()
    assert report["ok"] is True, report["problems"]


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

def test_doctor_names_the_gates_that_would_degrade(tmp_path, monkeypatch):
    import cli
    import importlib.util

    real = importlib.util.find_spec
    blocked = {"sympy", "rdkit", "pandas", "requests", "pint", "numpy"}
    monkeypatch.setattr(
        importlib.util, "find_spec",
        lambda name, *a, **k: None if name in blocked else real(name, *a, **k))
    args = type("Args", (), {"root": str(tmp_path), "verbose": False})()
    import contextlib
    import io
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli.cmd_doctor(args)
    report = json.loads(buffer.getvalue())
    assert code == 0
    assert "formula-validator" in report["gates_would_degrade"]
    assert "quantitative-validator" in report["gates_would_degrade"]
    assert report["install"].startswith("pip install ")
    assert "sympy" in report["install"]


def test_doctor_reports_a_clean_machine_as_clean(tmp_path):
    result = _repo_cli("doctor", "--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["skills"] == 25
    assert isinstance(report["gates_would_degrade"], list)


# --------------------------------------------------------------------------
# the CLI surfaces
# --------------------------------------------------------------------------

def test_skill_lint_exits_zero_on_the_real_tree():
    result = _repo_cli("skill", "lint")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_broker_status_says_how_to_start_one(tmp_path):
    result = _repo_cli("broker", "status", "--root", str(tmp_path))
    assert result.returncode == 2
    assert "broker start" in result.stdout


def test_lint_caps_the_routing_description(tmp_path):
    """The description is read in every session, used or not; keep it short."""
    folder = tmp_path / "skills" / "x-gate"
    folder.mkdir(parents=True)
    (folder / "run.py").write_text("", encoding="utf-8")
    (folder / "README.md").write_text("x", encoding="utf-8")
    (folder / "LICENSE").write_text("MIT", encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({
        "name": "x-gate", "version": "1.0.0", "stage": "gates",
        "input_types": ["csv"], "output_type": "gate_result",
        "entrypoint": "run.py", "description": "d"}), encoding="utf-8")
    body = """---
name: x-gate
description: >
  INSERT_DESCRIPTION
---

## When NOT to use

- never
"""
    (folder / "SKILL.md").write_text(
        body.replace("INSERT_DESCRIPTION", "word " * 40), encoding="utf-8")
    report = skillkit.lint(str(tmp_path))
    assert report["ok"] is False
    assert any("description is" in p["problem"] for p in report["problems"])


def test_every_shipped_description_is_within_the_cap():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    report = skillkit.lint(repo)
    assert report["ok"] is True, report["problems"]


def test_lint_refuses_a_broken_reference_link(tmp_path):
    folder = tmp_path / "skills" / "y-gate"
    folder.mkdir(parents=True)
    (folder / "run.py").write_text("", encoding="utf-8")
    (folder / "README.md").write_text("x", encoding="utf-8")
    (folder / "LICENSE").write_text("MIT", encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({
        "name": "y-gate", "version": "1.0.0", "stage": "gates",
        "input_types": ["csv"], "output_type": "gate_result",
        "entrypoint": "run.py", "description": "d"}), encoding="utf-8")
    body = """---
name: y-gate
description: >
  Short description.
---

## Quick Execution

- run it
- see [the details](references/missing.md)

## When NOT to use

- never
"""
    (folder / "SKILL.md").write_text(body, encoding="utf-8")
    report = skillkit.lint(str(tmp_path))
    assert any("does not exist" in p["problem"] for p in report["problems"])


def test_lint_refuses_an_orphan_reference(tmp_path):
    folder = tmp_path / "skills" / "z-gate"
    folder.mkdir(parents=True)
    (folder / "references").mkdir()
    (folder / "references" / "extra.md").write_text("x", encoding="utf-8")
    (folder / "run.py").write_text("", encoding="utf-8")
    (folder / "README.md").write_text("x", encoding="utf-8")
    (folder / "LICENSE").write_text("MIT", encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({
        "name": "z-gate", "version": "1.0.0", "stage": "gates",
        "input_types": ["csv"], "output_type": "gate_result",
        "entrypoint": "run.py", "description": "d"}), encoding="utf-8")
    (folder / "SKILL.md").write_text(
        """---
name: z-gate
description: >
  Short description.
---

## When NOT to use

- never
""", encoding="utf-8")
    report = skillkit.lint(str(tmp_path))
    assert any("never linked" in p["problem"] for p in report["problems"])
