"""Tests for non-destructive rollback."""

import pytest

from scripts.audit import AuditLog, RoundRecord
from scripts.errors import RollbackError
from scripts.rollback import rollback_to
from scripts.snapshot import snapshot


def _build_audit(work, store, tmp_path):
    (work / "data").mkdir(parents=True, exist_ok=True)
    (work / "data" / "x.json").write_text("round-state", encoding="utf-8")
    log = AuditLog(tmp_path / "audit_log.jsonl")
    post = snapshot(work, ["data/x.json"], store, 1, "post")
    log.record(
        RoundRecord(
            round_no=1, status="success", params={"a": 1},
            input_hash="i", output_hash="o",
            snapshot_post=post.to_dict()["files"],
        )
    )
    return log


def test_rollback_to_new_directory(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    store = tmp_path / "store"
    log = _build_audit(work, store, tmp_path)
    target = rollback_to(log, 1, work, store, force=False)
    assert target == work.parent / "work.rollback_0001"
    assert (target / "data" / "x.json").read_text(encoding="utf-8") == "round-state"


def test_rollback_force_overwrites_workdir(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    store = tmp_path / "store"
    log = _build_audit(work, store, tmp_path)
    # change live content first
    (work / "data" / "x.json").write_text("changed", encoding="utf-8")
    target = rollback_to(log, 1, work, store, force=True)
    assert target == work
    assert (work / "data" / "x.json").read_text(encoding="utf-8") == "round-state"


def test_rollback_is_audited(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    store = tmp_path / "store"
    log = _build_audit(work, store, tmp_path)
    rollback_to(log, 1, work, store, force=False)
    rollbacks = [r for r in log.entries() if r.status == "rolledback"]
    assert len(rollbacks) == 1
    assert "round 1" in rollbacks[0].note


def test_rollback_unknown_round(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    log = AuditLog(tmp_path / "audit_log.jsonl")
    with pytest.raises(RollbackError):
        rollback_to(log, 5, work, tmp_path / "store")


def test_rollback_missing_snapshot(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    log = AuditLog(tmp_path / "audit_log.jsonl")
    log.record(
        RoundRecord(round_no=1, status="success", snapshot_post={})
    )
    with pytest.raises(RollbackError):
        rollback_to(log, 1, work, tmp_path / "store")
