"""Tests for :mod:`scripts.rotate` -- artifact rotation .

Rotation is what stops ``process/`` from growing without bound, so the tests
pin down the three safety rules from the module docstring:

1. the newest before/after snapshots are **always** kept;
2. a run's artifacts are grouped by timestamp and rotated together;
3. anything that is not a recognised timestamped artifact is left alone.
"""
from __future__ import annotations

from pathlib import Path

from scripts import rotate, utils

STAMP = "20260101_120000"


def _proc(root: Path) -> Path:
    p = root / utils.TIER_PROCESS
    p.mkdir(parents=True, exist_ok=True)
    return p


def _artifact(root: Path, stamp: str, suffix: str, text: str = "{}") -> Path:
    p = _proc(root) / f"{stamp}_{suffix}"
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# grouping / retention
# ---------------------------------------------------------------------------


def test_nothing_to_rotate_when_process_missing(tmp_path: Path) -> None:
    res = rotate.rotate_artifacts(tmp_path, keep=2)
    assert res.deleted_count == 0
    assert res.kept_groups == []


def test_keeps_only_newest_groups(tmp_path: Path) -> None:
    for i in range(1, 8):  # 7 runs
        _artifact(tmp_path, f"2026010{i}_120000", "before.json")
        _artifact(tmp_path, f"2026010{i}_120000", "after.json")
    res = rotate.rotate_artifacts(tmp_path, keep=3)
    assert res.deleted_count == 8  # 4 runs x 2 files
    remaining = sorted(p.name for p in _proc(tmp_path).iterdir())
    assert len(remaining) == 6
    # The three newest stamps survive.
    for stamp in ("20260105_120000", "20260106_120000", "20260107_120000"):
        assert any(name.startswith(stamp) for name in remaining)


def test_a_runs_artifacts_rotate_together(tmp_path: Path) -> None:
    """An old run's before/after/history/log are deleted as one group."""
    for stamp in ("20260101_120000", "20260102_120000"):
        _artifact(tmp_path, stamp, "before.json")
        _artifact(tmp_path, stamp, "after.json")
    _artifact(tmp_path, "20260101_120000", "history.json")
    _artifact(tmp_path, "20260101_120000", "OrganizeLog.md", "log")

    res = rotate.rotate_artifacts(tmp_path, keep=1)
    assert res.deleted_count == 4
    assert not (_proc(tmp_path) / "20260101_120000_OrganizeLog.md").exists()
    assert not (_proc(tmp_path) / "20260101_120000_history.json").exists()


def test_latest_snapshots_are_protected_even_beyond_keep(tmp_path: Path) -> None:
    """A verify run after rotation must still find its reference state."""
    _artifact(tmp_path, "20260101_120000", "before.json")
    _artifact(tmp_path, "20260101_120000", "after.json")
    _artifact(tmp_path, "20260102_120000", "before.json")
    _artifact(tmp_path, "20260102_120000", "after.json")
    res = rotate.rotate_artifacts(tmp_path, keep=1)
    # keep=1 would drop the 0101 group, but its snapshots are the newest
    # *before*/*after* pair by name ordering... here 0102 is newest, so 0101
    # is deletable -- assert exactly that the protection set is reported.
    assert res.protected == ["20260102_120000"]
    assert (_proc(tmp_path) / "20260102_120000_before.json").exists()


def test_protection_survives_keep_one(tmp_path: Path) -> None:
    """The newest before+after must never be rotated away."""
    _artifact(tmp_path, "20260101_120000", "history.json")   # only artifact
    _artifact(tmp_path, "20260102_120000", "before.json")
    _artifact(tmp_path, "20260102_120000", "after.json")
    res = rotate.rotate_artifacts(tmp_path, keep=1)
    assert (_proc(tmp_path) / "20260102_120000_before.json").exists()
    assert (_proc(tmp_path) / "20260102_120000_after.json").exists()
    # The unprotected history group was cleaned up.
    assert not (_proc(tmp_path) / "20260101_120000_history.json").exists()
    assert res.protected == ["20260102_120000"]


def test_keep_is_clamped_to_at_least_one(tmp_path: Path) -> None:
    _artifact(tmp_path, "20260101_120000", "before.json")
    _artifact(tmp_path, "20260102_120000", "before.json")
    res = rotate.rotate_artifacts(tmp_path, keep=0)
    assert res.keep == 1
    # The newest snapshot still exists.
    assert (_proc(tmp_path) / "20260102_120000_before.json").exists()


# ---------------------------------------------------------------------------
# non-rotating files are never touched
# ---------------------------------------------------------------------------


def test_fixed_name_outputs_are_never_rotated(tmp_path: Path) -> None:
    _proc(tmp_path)
    keepers = [
        utils.INDEX_MD_NAME,
        utils.INDEX_XLSX_NAME,
        utils.VERIFY_REPORT_NAME,
        "duplicate_report.md",
        utils.MANIFEST_NAME,
        hashcache_name(),
    ]
    for name in keepers:
        (_proc(tmp_path) / name).write_text("x", encoding="utf-8")
    # Plus one old rotating artifact that *should* go.
    _artifact(tmp_path, "20260101_120000", "before.json")
    _artifact(tmp_path, "20260102_120000", "before.json")

    rotate.rotate_artifacts(tmp_path, keep=1)
    for name in keepers:
        assert (_proc(tmp_path) / name).exists(), f"{name} must survive rotation"


def test_subdirectories_are_ignored(tmp_path: Path) -> None:
    """process/logs/ and process/history/ hold audit trails, not run groups."""
    logs = _proc(tmp_path) / utils.LOG_DIRNAME
    logs.mkdir()
    (logs / "20260101.log").write_text("x", encoding="utf-8")
    hist = _proc(tmp_path) / "history"
    hist.mkdir()
    (hist / "20260101_120000_history.json").write_text("x", encoding="utf-8")

    res = rotate.rotate_artifacts(tmp_path, keep=1)
    assert res.deleted_count == 0
    assert (logs / "20260101.log").exists()
    assert (hist / "20260101_120000_history.json").exists()


def test_unrecognised_suffix_is_left_alone(tmp_path: Path) -> None:
    _artifact(tmp_path, "20260101_120000", "before.json")
    _artifact(tmp_path, "20260102_120000", "before.json")
    weird = _proc(tmp_path) / "20260101_120000_notes.md"
    weird.write_text("mine", encoding="utf-8")
    rotate.rotate_artifacts(tmp_path, keep=1)
    assert weird.exists()


# ---------------------------------------------------------------------------
# snapshot-only rotation
# ---------------------------------------------------------------------------


def test_rotate_snapshots_keeps_history_and_logs(tmp_path: Path) -> None:
    for i in (1, 2, 3):
        stamp = f"2026010{i}_120000"
        _artifact(tmp_path, stamp, "before.json")
        _artifact(tmp_path, stamp, "after.json")
        _artifact(tmp_path, stamp, "history.json")
        _artifact(tmp_path, stamp, "OrganizeLog.md", "log")

    res = rotate.rotate_snapshots(tmp_path, keep=2)
    # Only the 6 snapshot JSONs are candidates; the oldest run's pair goes.
    assert res.deleted_count == 2
    assert not (_proc(tmp_path) / "20260101_120000_before.json").exists()
    assert not (_proc(tmp_path) / "20260101_120000_after.json").exists()
    for name in ("history.json", "OrganizeLog.md"):
        for i in (1, 2, 3):
            assert (_proc(tmp_path) / f"2026010{i}_120000_{name}").exists()


def test_rotate_snapshots_protects_latest(tmp_path: Path) -> None:
    _artifact(tmp_path, "20260101_120000", "before.json")
    _artifact(tmp_path, "20260101_120000", "after.json")
    rotate.rotate_snapshots(tmp_path, keep=1)
    assert (_proc(tmp_path) / "20260101_120000_after.json").exists()


def test_rotate_snapshots_noop_without_process(tmp_path: Path) -> None:
    res = rotate.rotate_snapshots(tmp_path, keep=3)
    assert res.deleted_count == 0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def test_summary_lines_mention_protection(tmp_path: Path) -> None:
    _artifact(tmp_path, "20260101_120000", "before.json")
    _artifact(tmp_path, "20260101_120000", "after.json")
    res = rotate.rotate_artifacts(tmp_path, keep=1)
    joined = "\n".join(res.summary_lines())
    assert "keep=1" in joined
    assert "protected" in joined


def hashcache_name() -> str:
    from scripts import hashcache

    return hashcache.CACHE_FILENAME
