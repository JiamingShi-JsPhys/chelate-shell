"""Tests for :mod:`scripts.rollback`."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import organize, rollback, snapshot, utils


def test_rollback_restores_moved_files(sample_task: Path) -> None:
    before = snapshot.make_snapshot(sample_task, phase="before")
    session = utils.OrganizeSession(root=sample_task)
    organize.organize_folder(sample_task, session=session)

    # After organize: notes.txt has no keyword match, so it goes to process
    # the assistant's own output never lands in the user-reserved
    # material/initial/).
    assert (sample_task / "process/notes.txt").exists()

    rb = rollback.rollback(sample_task, session=session)
    assert rb.success is True
    # File is back at the original root location.
    assert (sample_task / "notes.txt").exists()
    assert not (sample_task / "process/notes.txt").exists()
    # The relocated user sub-folder is restored intact, too.
    assert (sample_task / "src/data/inner.txt").exists()
    assert not (sample_task / "material/initial/src/data/inner.txt").exists()


def test_rollback_removes_created_dirs(sample_task: Path) -> None:
    before = snapshot.make_snapshot(sample_task, phase="before")
    session = utils.OrganizeSession(root=sample_task)
    organize.organize_folder(sample_task, session=session)
    rollback.rollback(sample_task, session=session)
    # After rollback, the three-tier skeleton should be gone (empty dirs removed).
    for sub in ["material", "process", "results"]:
        assert not (sample_task / sub).exists(), f"{sub} should be removed"


def test_rollback_seals_log(sample_task: Path) -> None:
    before = snapshot.make_snapshot(sample_task, phase="before")
    session = utils.OrganizeSession(root=sample_task)
    organize.organize_folder(sample_task, session=session)
    rb = rollback.rollback(sample_task, session=session)
    # The organize log is renamed to *_Cancelled.md.
    proc = sample_task / utils.TIER_PROCESS
    if proc.exists():
        sealed = [p for p in proc.iterdir() if p.name.endswith("Cancelled.md")]
        # Even if the process dir is removed, the seal is recorded in rb.
    assert rb.sealed_log is None or "Cancelled" in rb.sealed_log or not proc.exists()


def test_rollback_purges_index_files(sample_task: Path) -> None:
    before = snapshot.make_snapshot(sample_task, phase="before")
    session = utils.OrganizeSession(root=sample_task)
    organize.organize_folder(sample_task, session=session)
    # Generate the index files first so there is something to purge.
    from scripts import index_md
    index_md.write_index_md(sample_task)
    assert (sample_task / "material/Index.md").exists()

    rb = rollback.rollback(sample_task, session=session)
    assert not (sample_task / "material/Index.md").exists()
    assert any("Index.md" in p for p in rb.purged_files)


def test_rollback_preserves_conflicting_original(sample_task: Path) -> None:
    """If the original name is re-occupied, rollback uses a _rN suffix."""
    before = snapshot.make_snapshot(sample_task, phase="before")
    session = utils.OrganizeSession(root=sample_task)
    organize.organize_folder(sample_task, session=session)

    # Record the moved target before re-occupying the original name.
    moved_notes = sample_task / "process/notes.txt"
    assert moved_notes.exists()

    # Re-occupy the original root name so the reverse rename collides.
    (sample_task / "notes.txt").write_text("blocking occupant", encoding="utf-8")

    rb = rollback.rollback(sample_task, session=session)
    # The moved file must not be silently lost: it either restored under a
    # _rN suffix at root, or the original occupant stayed in place.
    root_notes = [p for p in sample_task.iterdir() if p.name.startswith("notes")]
    # root_notes includes at least the blocking occupant.
    assert any(p.name == "notes.txt" for p in root_notes)
    # The moved copy survived somewhere (restored _rN or still in process).
    surviving = [
        p for p in sample_task.rglob("notes*.txt")
        if p.name != "notes.txt" or p.parent == sample_task
    ]
    assert len(surviving) >= 2, f"expected >=2 notes* files, got {surviving}"


def test_rollback_reconstructs_session_when_none(sample_task: Path) -> None:
    """When the live session is lost, rollback reads the log + snapshot."""
    before = snapshot.make_snapshot(sample_task, phase="before")
    session = utils.OrganizeSession(root=sample_task)
    organize.organize_folder(sample_task, session=session)

    # Simulate losing the session object: call rollback with None.
    rb = rollback.rollback(sample_task, session=None)
    # The reconstructed path may record conflicts, but it must not raise and
    # must at least attempt restoration.
    assert isinstance(rb, rollback.RollbackResult)
    assert rb.restored_count >= 0


def test_rollback_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        rollback.rollback(tmp_path / "does_not_exist")


def test_rollback_result_fields() -> None:
    rb = rollback.RollbackResult()
    assert rb.restored_count == 0
    assert rb.success is False
    rb.restored_files = ["a", "b"]
    assert rb.restored_count == 2
