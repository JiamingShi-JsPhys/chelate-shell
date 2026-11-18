"""code-gate: eight fixed rules, and a refusal to pass an empty target."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from conftest import REPO_ROOT, run_path_of
from lib.chelate_core import codegate

PY = sys.executable


def _rules(source, **kwargs):
    return [item["rule"] for item in codegate.check_source(source, "x.py",
                                                           **kwargs)]


def _write(directory, name, text):
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# the rules
# --------------------------------------------------------------------------

def test_a_bare_except_is_a_finding():
    assert "bare-except" in _rules("try:\n    pass\nexcept:\n    pass\n")


def test_an_exception_swallowed_with_pass_is_a_finding():
    source = "try:\n    pass\nexcept ValueError:\n    pass\n"
    assert "swallowed-error" in _rules(source)


def test_a_mutable_default_argument_is_a_finding():
    assert "mutable-default" in _rules("def f(items=[]):\n    return items\n")
    assert "mutable-default" in _rules("def g(cfg={}):\n    return cfg\n")


def test_comparison_with_none_using_equality_is_a_finding():
    assert "eq-none" in _rules("def f(x):\n    return x == None\n")


def test_a_star_import_is_a_finding():
    assert "star-import" in _rules("from os import *\n")


def test_a_function_past_the_line_budget_is_a_finding():
    body = "\n".join(f"    x{i} = {i}" for i in range(20))
    assert "long-function" in _rules(f"def f():\n{body}\n", max_lines=10)


def test_a_function_past_the_argument_budget_is_a_finding():
    assert "too-many-args" in _rules("def f(a, b, c):\n    return a\n",
                                     max_args=2)


def test_a_file_that_does_not_parse_is_a_syntax_finding():
    findings = codegate.check_source("def f(:\n", "x.py")
    assert [item["rule"] for item in findings] == ["syntax-error"]
    assert findings[0]["line"] == 1


def test_clean_source_has_no_findings():
    source = ("def add(a, b):\n"
              "    try:\n"
              "        return a + b\n"
              "    except TypeError:\n"
              "        raise\n")
    assert codegate.check_source(source, "x.py") == []


def test_findings_are_sorted_by_line():
    source = ("from os import *\n"
              "def f(x, items=[]):\n"
              "    return x == None\n")
    lines = [item["line"] for item in codegate.check_source(source, "x.py")]
    assert lines == sorted(lines)


# --------------------------------------------------------------------------
# the tree walk
# --------------------------------------------------------------------------

def test_a_directory_with_no_python_is_not_a_pass(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("hi", encoding="utf-8")
    report = codegate.check_tree(str(tmp_path), "docs")
    assert report["files"] == 0
    assert report["ok"] is False


def test_caches_and_generated_zones_are_skipped(tmp_path):
    _write(tmp_path, "src/app.py", "def f():\n    return 1\n")
    _write(tmp_path, "__pycache__/app.py", "from os import *\n")
    _write(tmp_path, "process/snapshot.py", "from os import *\n")
    report = codegate.check_tree(str(tmp_path), ".")
    assert report["files"] == 1
    assert report["finding_count"] == 0


def test_a_target_outside_the_workspace_is_refused(tmp_path):
    outside = tmp_path.parent / "elsewhere.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(Exception) as exc:
        codegate.check_tree(str(tmp_path), str(outside))
    assert "escapes the workspace" in str(exc.value)


def test_a_missing_target_is_refused(tmp_path):
    with pytest.raises(codegate.CodeGateError):
        codegate.check_tree(str(tmp_path), "nope")


def test_ruff_is_off_unless_asked(tmp_path):
    _write(tmp_path, "ok.py", "def f():\n    return 1\n")
    report = codegate.check(str(tmp_path), "ok.py")
    assert report["ruff"] == {"enabled": False, "note": "", "findings": [],
                              "count": 0}


def test_asking_for_ruff_without_it_says_so(tmp_path, monkeypatch):
    """The absent path must be testable on a machine that has ruff too."""
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec",
        lambda name, *a, **k: None if name == "ruff" else real(name, *a, **k))
    _write(tmp_path, "ok.py", "def f():\n    return 1\n")
    report = codegate.check(str(tmp_path), "ok.py", ruff=True)
    assert "not installed" in report["ruff"]["note"]


# --------------------------------------------------------------------------
# the adapter
# --------------------------------------------------------------------------

def _run_adapter(workspace, *extra):
    proc = subprocess.run(
        [PY, str(run_path_of("code-gate")), "--root", str(workspace), *extra],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120)
    lines = [line for line in proc.stdout.strip().splitlines() if line.strip()]
    assert lines, proc.stdout + proc.stderr
    return json.loads(lines[-1])


def test_the_adapter_fails_and_names_the_first_finding(workspace):
    _write(workspace, "src/bad.py",
           "from os import *\n\n\ndef f(a, b, c, d, e, g, h, i):\n"
           "    try:\n        return a\n    except:\n        return b\n")
    payload = _run_adapter(workspace, "--input", "src")
    assert payload["status"] == "FAIL"
    assert "src/bad.py" in payload["reason"]
    reports = list((workspace / "process").glob("code_report_*.json"))
    assert reports
    saved = json.loads(reports[0].read_text(encoding="utf-8"))
    assert saved["by_rule"]["star-import"] == 1
    assert saved["by_rule"]["bare-except"] == 1


def test_the_adapter_passes_clean_source(workspace):
    _write(workspace, "src/ok.py", "def f(a):\n    return a\n")
    payload = _run_adapter(workspace, "--input", "src")
    assert payload["status"] == "PASS"
    assert "8 fixed rule" in payload["reason"]


def test_the_adapter_degrades_when_there_is_nothing_to_check(workspace):
    (workspace / "src").mkdir()
    payload = _run_adapter(workspace, "--input", "src")
    assert payload["status"] == "UNVERIFIED"
    assert "no Python files" in payload["reason"]
