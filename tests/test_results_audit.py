"""The promotion log, and what it can and cannot vouch for.

The approval gate binds ``router.promote()``. It cannot stop a process that
writes into ``results/`` with its own hands — a shell, an editor, an agent's
file tool — so ``promote()`` records every file it copied, and
``audit_results()`` names everything else.

These tests pin both halves: the log is written with the token that
authorised it, and an intrusion into ``results/`` is reported by name
instead of passing silently.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT
from core import approval, router

STAMP = "20260101T000000Z"


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "process" / "gates").mkdir(parents=True)
    (ws / "process" / "profile.json").write_text('{"rows": 3}', encoding="utf-8")
    (ws / "process" / "gates" / "data-profiler.json").write_text(
        '{"status": "PASS"}', encoding="utf-8")
    return ws


def test_no_results_directory_is_not_an_error(tmp_path: Path) -> None:
    report = router.audit_results(str(tmp_path))
    assert report["ok"] is True
    assert report["promotions"] == 0


def test_a_promotion_is_recorded_with_the_token_that_authorised_it(
        tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    dst = router.promote(str(ws), STAMP,
                         {"source": "token", "nonce": "abc123"})
    assert dst is not None

    report = router.audit_results(str(ws))
    assert report["ok"] is True
    assert report["promotions"] == 1

    log = ws / "results" / router.PROMOTION_LOG
    entry = json.loads(log.read_text(encoding="utf-8").strip())
    assert entry["approval"]["nonce"] == "abc123"
    assert entry["action"] == "promote"
    assert "results/promoted_%s/profile.json" % STAMP in entry["files"]


def test_a_file_placed_by_hand_is_named(tmp_path: Path) -> None:
    """The bypass an agent actually performs: write results/ directly."""
    ws = _workspace(tmp_path)
    router.promote(str(ws), STAMP)
    (ws / "results" / "handwritten.md").write_text(
        "delivered without a token", encoding="utf-8")

    report = router.audit_results(str(ws))
    assert report["ok"] is False
    assert report["unapproved"] == ["results/handwritten.md"]
    assert report["modified"] == []


def test_a_promoted_file_changed_afterwards_is_named(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    router.promote(str(ws), STAMP)
    target = ws / "results" / f"promoted_{STAMP}" / "profile.json"
    target.write_text('{"rows": 999}', encoding="utf-8")

    report = router.audit_results(str(ws))
    assert report["ok"] is False
    assert report["modified"] == [f"results/promoted_{STAMP}/profile.json"]
    assert report["unapproved"] == []


def test_pipeline_reports_are_not_mistaken_for_deliverables(
        tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    (ws / "results").mkdir()
    (ws / "results" / f"pipeline_report_{STAMP}.json").write_text(
        json.dumps({k: None for k in router.REPORT_KEYS}), encoding="utf-8")
    assert router.audit_results(str(ws))["ok"] is True


def test_a_deliverable_named_like_a_report_is_not_hidden(
        tmp_path: Path) -> None:
    """The exemption is by name *and* shape, not by name alone."""
    ws = _workspace(tmp_path)
    (ws / "results").mkdir()
    (ws / "results" / f"pipeline_report_{STAMP}.json").write_text(
        json.dumps({"deliverable": "not a report at all"}), encoding="utf-8")

    report = router.audit_results(str(ws))
    assert report["ok"] is False
    assert report["unapproved"] == [
        f"results/pipeline_report_{STAMP}.json"]


def test_a_forged_log_entry_is_not_believed(tmp_path: Path) -> None:
    """Hand-writing a log line is the next move for an agent that read it."""
    ws = _workspace(tmp_path)
    # A key exists once anything approved in this workspace; mint it the way
    # a promotion would, then forge the line an agent would add.
    approval.sign(str(ws), {"mint": "key"}, create=True)
    router.promote(str(ws), STAMP, {"source": "token", "nonce": "real"})

    smuggled = ws / "results" / "smuggled.md"
    smuggled.write_text("never approved", encoding="utf-8")
    digest = hashlib.sha256(smuggled.read_bytes()).hexdigest()
    forged = {
        "action": "promote", "stamp": "x", "at": "2026-01-01T00:00:00Z",
        "promoted_to": "results/promoted_x",
        "approval": {"source": "token", "nonce": "forged"},
        "files": {"results/smuggled.md": digest},
    }
    with (ws / "results" / router.PROMOTION_LOG).open(
            "a", encoding="utf-8") as fh:
        fh.write(json.dumps(forged) + "\n")

    report = router.audit_results(str(ws))
    assert report["ok"] is False
    assert report["unapproved"] == ["results/smuggled.md"]
    tampered = report["tampered"]
    assert isinstance(tampered, list)
    assert any("signature" in item for item in tampered)


def test_a_corrupt_log_line_is_reported_not_raised(tmp_path: Path) -> None:
    """An agent can append junk; that must not be a way to silence the audit."""
    ws = _workspace(tmp_path)
    router.promote(str(ws), STAMP)
    with (ws / "results" / router.PROMOTION_LOG).open(
            "a", encoding="utf-8") as fh:
        fh.write("[]\n")

    report = router.audit_results(str(ws))
    assert report["ok"] is False
    assert report["tampered"] == ["line 2: not an object"]


def test_cli_audit_exits_non_zero_when_something_is_unapproved(
        tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    router.promote(str(ws), STAMP)

    clean = subprocess.run(
        [sys.executable, "cli.py", "audit", "--root", str(ws)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        stdin=subprocess.DEVNULL)
    assert clean.returncode == 0, clean.stdout + clean.stderr

    (ws / "results" / "smuggled.csv").write_text("a,b\n", encoding="utf-8")
    dirty = subprocess.run(
        [sys.executable, "cli.py", "audit", "--root", str(ws)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
        stdin=subprocess.DEVNULL)
    assert dirty.returncode == 1
    assert "smuggled.csv" in dirty.stdout
