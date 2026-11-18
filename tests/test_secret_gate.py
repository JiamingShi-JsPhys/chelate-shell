"""secret-gate: credentials are found by shape, reported by fingerprint."""
from __future__ import annotations

import json
import subprocess
import sys

from conftest import REPO_ROOT, run_path_of
from lib.chelate_core import secret_scan

AWS = "AKIA" + "Q" * 16
GITHUB = "ghp_" + "a1B2c3D4" * 5          # 40 characters after the prefix
PRIVATE = "-----BEGIN RSA PRIVATE KEY-----"


def _tree(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_an_aws_key_is_found_without_the_key_in_the_report(tmp_path):
    _tree(tmp_path, "config.py", f'KEY = "{AWS}"\n')
    report = secret_scan.scan(str(tmp_path))
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["rule"] == "aws-access-key"
    assert finding["path"] == "config.py"
    assert finding["line"] == 1
    assert AWS not in json.dumps(report)


def test_the_fingerprint_is_stable_and_matches_the_secret():
    assert secret_scan.fingerprint("abc") == secret_scan.fingerprint("abc")
    assert secret_scan.fingerprint("abc") != secret_scan.fingerprint("abd")
    assert len(secret_scan.fingerprint("abc")) == 12


def test_github_slack_and_private_key_shapes(tmp_path):
    _tree(tmp_path, "a.txt", f"token={GITHUB}\n")
    _tree(tmp_path, "b.txt", "xoxb-1234567890-abcdef\n")
    _tree(tmp_path, "c.pem", PRIVATE + "\n")
    rules = {f["rule"] for f in secret_scan.scan(str(tmp_path))["findings"]}
    assert {"github-token", "slack-token", "private-key-block"} <= rules


def test_an_assignment_is_caught_even_without_a_known_shape(tmp_path):
    _tree(tmp_path, "settings.yaml", 'api_key: "9f8e7d6c5b4a3210zyxw"\n')
    report = secret_scan.scan(str(tmp_path))
    assert report["findings"][0]["rule"] == "secret-assignment"


def test_ordinary_prose_is_not_a_finding(tmp_path):
    _tree(tmp_path, "notes.md",
          "Set the token in your environment.\npassword handling is a topic.\n")
    assert secret_scan.scan(str(tmp_path))["findings"] == []


def test_shape_rules_win_over_assignment_rules(tmp_path):
    """One credential, one finding — not a shape hit plus a context hit."""
    _tree(tmp_path, "x.py", f'aws_key = "{AWS}"\n')
    findings = secret_scan.scan(str(tmp_path))["findings"]
    assert [f["rule"] for f in findings] == ["aws-access-key"]


def test_the_allowlist_suppresses_by_fingerprint_and_counts_it(tmp_path):
    _tree(tmp_path, "x.py", f'KEY = "{AWS}"\n')
    fp = secret_scan.scan(str(tmp_path))["findings"][0]["fingerprint"]
    allow = tmp_path / "allow.json"
    allow.write_text(json.dumps({"fingerprints": [fp]}), encoding="utf-8")
    report = secret_scan.scan(str(tmp_path), allowlist=str(allow))
    assert report["findings"] == []
    assert report["allowed"] == 1


def test_the_allowlist_suppresses_one_rule_in_one_file(tmp_path):
    _tree(tmp_path, "docs/example.md", 'api_key: "0123456789abcdef"\n')
    _tree(tmp_path, "src/app.py", 'api_key: "0123456789abcdef"\n')
    allow = tmp_path / "allow.json"
    allow.write_text(json.dumps({"entries": [
        {"rule": "secret-assignment", "path": "docs/example.md"}]}),
        encoding="utf-8")
    report = secret_scan.scan(str(tmp_path), allowlist=str(allow))
    assert [f["path"] for f in report["findings"]] == ["src/app.py"]


def test_a_line_pragma_exempts_only_that_line(tmp_path):
    _tree(tmp_path, "fixture.py",
          f'FAKE = "{AWS}"  # chelate-secret-allow\n'
          f'REAL = "{AWS}"\n')
    findings = secret_scan.scan(str(tmp_path))["findings"]
    assert [f["line"] for f in findings] == [2]


def test_a_named_pragma_exempts_only_that_rule(tmp_path):
    _tree(tmp_path, "fixture.py",
          'api_key: "0123456789abcdef"  # chelate-secret-allow: secret-assignment\n')
    assert secret_scan.scan(str(tmp_path))["findings"] == []


def test_caches_and_git_are_skipped(tmp_path):
    _tree(tmp_path, ".git/config", f'KEY = "{AWS}"\n')
    _tree(tmp_path, "node_modules/x.js", f'KEY = "{AWS}"\n')
    _tree(tmp_path, "__pycache__/x.py", f'KEY = "{AWS}"\n')
    _tree(tmp_path, "real.py", "print('clean')\n")
    report = secret_scan.scan(str(tmp_path))
    assert report["files_scanned"] == 1
    assert report["findings"] == []


def test_binary_files_are_skipped(tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00" + AWS.encode())
    _tree(tmp_path, "readme.txt", "nothing here\n")
    report = secret_scan.scan(str(tmp_path))
    assert report["files_scanned"] == 1


def test_findings_are_sorted_for_a_deterministic_report(tmp_path):
    _tree(tmp_path, "b.py", f'A = "{AWS}"\n')
    _tree(tmp_path, "a.py", f'B = "{AWS}"\nC = "{AWS}"\n')
    findings = secret_scan.scan(str(tmp_path))["findings"]
    assert [(f["path"], f["line"]) for f in findings] == [
        ("a.py", 1), ("a.py", 2), ("b.py", 1)]


# --------------------------------------------------------------------------
# the adapter
# --------------------------------------------------------------------------

def _run(workspace, *extra):
    proc = subprocess.run(
        [sys.executable, str(run_path_of("secret-gate")),
         "--root", str(workspace), "--action", "scan", *extra],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120)
    lines = [line for line in proc.stdout.strip().splitlines() if line.strip()]
    assert lines, proc.stdout + proc.stderr
    return json.loads(lines[-1]), proc


def test_the_adapter_passes_a_clean_tree(workspace):
    (workspace / "process").mkdir(exist_ok=True)
    (workspace / "process" / "note.txt").write_text("fine\n", encoding="utf-8")
    payload, _ = _run(workspace)
    assert payload["status"] == "PASS"
    assert "1 file" in payload["reason"]


def test_the_adapter_fails_and_never_prints_the_secret(workspace):
    (workspace / "process").mkdir(exist_ok=True)
    (workspace / "process" / "leak.py").write_text(
        f'KEY = "{AWS}"\n', encoding="utf-8")
    payload, proc = _run(workspace)
    assert payload["status"] == "FAIL"
    assert "leak.py:1" in payload["reason"]
    assert AWS not in proc.stdout and AWS not in proc.stderr


def test_the_adapter_degrades_on_an_empty_tree(workspace):
    payload, _ = _run(workspace, "--path", "process")
    assert payload["status"] == "UNVERIFIED"
    assert "nothing" in payload["reason"].lower() or \
        "no text files" in payload["reason"]
