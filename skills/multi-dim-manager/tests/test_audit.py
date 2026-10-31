"""Tests for the audit log and run metadata."""

import json

from scripts.audit import AuditLog, RoundRecord, write_metadata


def _rec(round_no, status="success"):
    return RoundRecord(
        round_no=round_no, status=status, params={"a": round_no},
        input_hash="i" * 10, output_hash="o" * 10,
        timestamp="2026-01-01T00:00:00Z", plugin_exit=0,
        out_file="out.json", snapshot_pre={"f": "h1"}, snapshot_post={"f": "h2"},
    )


def test_record_and_reload(tmp_path):
    log = AuditLog(tmp_path / "audit_log.jsonl")
    log.record(_rec(1))
    log.record(_rec(2, status="failed"))
    entries = log.entries()
    assert len(entries) == 2
    assert entries[0].round_no == 1
    assert entries[1].status == "failed"


def test_get_and_last_successful(tmp_path):
    log = AuditLog(tmp_path / "audit_log.jsonl")
    log.record(_rec(1, status="failed"))
    log.record(_rec(2))
    log.record(_rec(3))
    assert log.get(2).round_no == 2
    assert log.get(99) is None
    assert log.last_successful().round_no == 3


def test_rounds_excludes_rolledback(tmp_path):
    log = AuditLog(tmp_path / "audit_log.jsonl")
    log.record(_rec(1))
    log.record(RoundRecord(round_no=1, status="rolledback", note="r"))
    assert len(log.rounds()) == 1
    assert log.rounds()[0].status == "success"


def test_record_is_jsonl_one_line_each(tmp_path):
    log = AuditLog(tmp_path / "audit_log.jsonl")
    log.record(_rec(1))
    text = tmp_path.joinpath("audit_log.jsonl").read_text(encoding="utf-8")
    assert text.count("\n") == 1
    json.loads(text.strip())


def test_write_metadata(tmp_path):
    p = tmp_path / "run_metadata.json"
    write_metadata(p, {"k": "v"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"k": "v"}
