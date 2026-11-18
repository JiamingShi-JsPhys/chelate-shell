"""test-gate: a green exit code is not a green test run."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from conftest import REPO_ROOT, run_path_of
from lib.chelate_core import testgate

PY = sys.executable


def _outcome(stdout="", rc=0, timed_out=False, stderr=""):
    return {"command": [PY, "-c", "pass"], "rc": rc, "timed_out": timed_out,
            "seconds": 0.1, "stdout": stdout, "stderr": stderr,
            "cwd": "/tmp"}


# --------------------------------------------------------------------------
# the declaration
# --------------------------------------------------------------------------

def test_a_json_array_is_the_only_string_form_accepted():
    assert testgate.parse_command('["python", "-m", "pytest", "-q"]') == \
        ["python", "-m", "pytest", "-q"]
    assert testgate.parse_command(["pytest", "-q"]) == ["pytest", "-q"]


def test_a_plain_string_is_refused_because_it_needs_a_shell():
    with pytest.raises(testgate.TestGateError) as exc:
        testgate.parse_command("pytest -q tests/")
    assert "JSON array" in str(exc.value)


def test_the_declaration_supplies_command_and_timeout(tmp_path):
    (tmp_path / ".chelate").mkdir()
    (tmp_path / ".chelate" / "test-gate.json").write_text(
        json.dumps({"command": ["pytest"], "timeout": 30}), encoding="utf-8")
    declared = testgate.load_declaration(str(tmp_path))
    assert declared["command"] == ["pytest"]
    assert declared["timeout"] == 30


def test_an_unknown_declaration_key_is_refused(tmp_path):
    (tmp_path / ".chelate").mkdir()
    (tmp_path / ".chelate" / "test-gate.json").write_text(
        json.dumps({"command": ["pytest"], "shell": True}), encoding="utf-8")
    with pytest.raises(testgate.TestGateError) as exc:
        testgate.load_declaration(str(tmp_path))
    assert "unknown key" in str(exc.value)


def test_no_declaration_says_where_to_put_one(tmp_path):
    with pytest.raises(testgate.TestGateError) as exc:
        testgate.load_declaration(str(tmp_path))
    assert "test-gate.json" in str(exc.value)


# --------------------------------------------------------------------------
# reading the output
# --------------------------------------------------------------------------

def test_a_pytest_summary_is_counted():
    counts = testgate.summarise(
        "....F\n=== 1 failed, 3 passed, 2 skipped in 0.12s ===\n")
    assert counts["passed"] == 3 and counts["failed"] == 1
    assert counts["skipped"] == 2
    assert counts["framework"] == "pytest"


def test_unittest_ok_is_recognised():
    counts = testgate.summarise("Ran 4 tests in 0.002s\n\nOK\n")
    assert counts["summary"] == "OK"
    assert counts["framework"] == "unittest"


def test_crlf_output_is_read_the_same_way():
    """subprocess text mode returns CRLF on Windows, not LF."""
    counts = testgate.summarise("Ran 4 tests in 0.002s\r\n\r\nOK\r\n")
    assert counts["summary"] == "OK"
    assert testgate.verdict(_outcome("4 passed in 0.1s\r\n"), 60)["status"] \
        == "PASS"


def test_no_tests_ran_is_recognised_in_every_spelling():
    for text in ("no tests ran in 0.01s", "collected 0 items",
                 "Ran 0 tests in 0.000s"):
        assert testgate.summarise(text)["no_tests"] is True, text


# --------------------------------------------------------------------------
# the verdict
# --------------------------------------------------------------------------

def test_a_clean_run_passes():
    result = testgate.verdict(_outcome("4 passed in 0.1s"), 60)
    assert result["status"] == "PASS"
    assert result["data"]["passed"] == 4


def test_a_non_zero_exit_fails_even_without_a_summary():
    result = testgate.verdict(_outcome("boom", rc=2), 60)
    assert result["status"] == "FAIL"
    assert "exited 2" in result["reason"]


def test_a_red_summary_beats_a_green_exit_code():
    """A wrapper that swallows its child's status cannot turn red into green."""
    result = testgate.verdict(_outcome("1 failed, 2 passed in 0.1s", rc=0), 60)
    assert result["status"] == "FAIL"


def test_running_no_tests_is_unverified_not_pass():
    result = testgate.verdict(_outcome("no tests ran in 0.00s", rc=0), 60)
    assert result["status"] == "UNVERIFIED"
    assert "collected no tests" in result["reason"]


def test_a_zero_exit_with_no_readable_summary_is_unverified():
    """A command that merely succeeded is not evidence that a test ran."""
    result = testgate.verdict(_outcome("hello world", rc=0), 60)
    assert result["status"] == "UNVERIFIED"
    assert "no test summary" in result["reason"]


def test_a_timeout_is_unverified_because_the_result_is_unknown():
    result = testgate.verdict(_outcome("", rc=-1, timed_out=True), 5)
    assert result["status"] == "UNVERIFIED"
    assert "timed out after 5s" in result["reason"]


# --------------------------------------------------------------------------
# running it
# --------------------------------------------------------------------------

def test_the_executable_whitelist_is_enforced(tmp_path):
    with pytest.raises(Exception) as exc:
        testgate.run(str(tmp_path), ["definitely-not-a-program"])
    assert "whitelist" in str(exc.value)


def test_the_approval_hatch_does_not_reach_the_child(tmp_path, monkeypatch):
    monkeypatch.setenv("CHELATE_UNSAFE_AUTO_APPROVE", "1")
    outcome = testgate.run(
        str(tmp_path),
        [PY, "-c", "import os;print(os.environ.get("
                   "'CHELATE_UNSAFE_AUTO_APPROVE', 'absent'))"], timeout=60)
    assert "absent" in outcome["stdout"]


# --------------------------------------------------------------------------
# the adapter
# --------------------------------------------------------------------------

def _run_adapter(workspace, *extra):
    proc = subprocess.run(
        [PY, str(run_path_of("test-gate")), "--root", str(workspace), *extra],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120)
    lines = [line for line in proc.stdout.strip().splitlines() if line.strip()]
    assert lines, proc.stdout + proc.stderr
    return json.loads(lines[-1])


def test_the_adapter_writes_a_report_and_passes(workspace):
    payload = _run_adapter(
        workspace, "--command",
        json.dumps([PY, "-c", "print('3 passed in 0.01s')"]))
    assert payload["status"] == "PASS"
    reports = list((workspace / "process").glob("test_report_*.json"))
    assert reports, "the report a later reader checks must be written"
    saved = json.loads(reports[0].read_text(encoding="utf-8"))
    assert saved["data"]["passed"] == 3
    assert saved["data"]["command"][1] == "-c"


def test_the_adapter_reports_a_failing_suite_as_fail(workspace):
    payload = _run_adapter(
        workspace, "--command",
        json.dumps([PY, "-c",
                    "import sys;print('1 failed, 1 passed');sys.exit(1)"]))
    assert payload["status"] == "FAIL"
    assert "1 failed" in payload["reason"]


def test_the_adapter_degrades_when_nothing_is_declared(workspace):
    payload = _run_adapter(workspace)
    assert payload["status"] == "UNVERIFIED"
    assert "test-gate.json" in payload["reason"]
