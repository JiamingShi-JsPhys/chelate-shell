"""Tests for :mod:`scripts.verify` (the mandatory verification gate)."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import snapshot, utils, verify
from scripts import organize, snapshot as snap


def _full_run(root: Path, mutate_after: bool = False):
    """Run organize + before/after snapshots, optionally mutating a file.

    Returns (session, vres) for downstream assertions.
    """
    before = snap.make_snapshot(root, phase="before")
    session = utils.OrganizeSession(root=root)
    organize.organize_folder(root, session=session)

    if mutate_after:
        # Simulate an unauthorized content change to a file that was NOT
        # moved (so it is tracked by C2/C5). ``inner.txt`` is promoted to
        # initial but not re-moved, making it the ideal tamper target.
        target = root / utils.TIER_ORGANIZE / utils.SUB_INIT / "inner.txt"
        if target.exists():
            target.write_text("TAMPERED", encoding="utf-8")
        else:
            # Fallback: tamper any file that survived in initial.
            for p in (root / utils.TIER_ORGANIZE / utils.SUB_INIT).iterdir():
                if p.is_file():
                    p.write_text("TAMPERED", encoding="utf-8")
                    break

    after = snap.make_snapshot(root, phase="after")
    vres = verify.verify(root, session=session, before=before, after=after)
    return session, vres


def test_verify_passes_on_clean_run(sample_task: Path) -> None:
    _, vres = _full_run(sample_task, mutate_after=False)
    assert vres.passed is True
    assert vres.error_count == 0


def test_verify_fails_on_content_change(task_with_readonly: Path) -> None:
    """Tamper a file that organize intentionally skips (a readonly file).

    A readonly file stays at its original path, so it is tracked by C2/C5 as
    an unmoved file -- corrupting it must flip both checks to failed. On
    platforms where chmod is a no-op (Windows) the file is simply writable;
    the test still works because we make it writable explicitly before the
    tamper write.
    """
    import os

    root = task_with_readonly
    locked = root / "locked.txt"
    assert locked.exists()

    before = snap.make_snapshot(root, phase="before")
    session = utils.OrganizeSession(root=root)
    organize.organize_folder(root, session=session)

    # Make the file writable (no-op on POSIX where it's already writable,
    # meaningful on Windows where chmod(0o444) was applied).
    try:
        os.chmod(locked, 0o644)
    except OSError:
        pass

    # Tamper the readonly (unmoved) file's content.
    locked.write_text("TAMPERED CONTENT", encoding="utf-8")

    after = snap.make_snapshot(root, phase="after")
    vres = verify.verify(root, session=session, before=before, after=after)

    # C2 (content integrity) and C5 (size) must fail -> overall failed.
    assert vres.passed is False
    c2 = next(c for c in vres.checks if c.code == "C2")
    c5 = next(c for c in vres.checks if c.code == "C5")
    assert c2.passed is False
    assert c5.passed is False


def test_report_written(sample_task: Path) -> None:
    session, vres = _full_run(sample_task)
    report = sample_task / utils.TIER_PROCESS / utils.VERIFY_REPORT_NAME
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Verification Report" in text
    assert "C1" in text and "C7" in text


def test_check_c1_counts(sample_task: Path) -> None:
    before = snap.make_snapshot(sample_task, phase="before")
    session = utils.OrganizeSession(root=sample_task)
    organize.organize_folder(sample_task, session=session)
    after = snap.make_snapshot(sample_task, phase="after")
    vres = verify.verify(
        sample_task, session=session, before=before, after=after,
        write_report=False,
    )
    c1 = next(c for c in vres.checks if c.code == "C1")
    # No files were deleted or created, only moved -> conservation holds.
    assert c1.passed is True


def test_check_c4_detects_unauthorized_delete(tmp_path: Path) -> None:
    # Manually craft a scenario: a before-file disappears in after without
    # being in the move log.
    root = tmp_path / "del_task"
    root.mkdir()
    (root / "keep.txt").write_text("keep")

    before = snap.make_snapshot(root, phase="before")
    session = utils.OrganizeSession(root=root)
    # No organize; just delete a file.
    (root / "keep.txt").unlink()
    after = snap.make_snapshot(root, phase="after")
    vres = verify.verify(
        root, session=session, before=before, after=after, write_report=False
    )
    c4 = next(c for c in vres.checks if c.code == "C4")
    assert c4.passed is False


def test_check_c7_structure_complete(sample_task: Path) -> None:
    _, vres = _full_run(sample_task)
    c7 = next(c for c in vres.checks if c.code == "C7")
    assert c7.passed is True


def test_check_c7_fails_when_structure_missing(tmp_path: Path) -> None:
    root = tmp_path / "no_struct"
    root.mkdir()
    (root / "a.txt").write_text("a")
    before = snap.make_snapshot(root, phase="before")
    session = utils.OrganizeSession(root=root)
    # No organize -> structure absent.
    after = snap.make_snapshot(root, phase="after")
    vres = verify.verify(
        root, session=session, before=before, after=after, write_report=False
    )
    c7 = next(c for c in vres.checks if c.code == "C7")
    assert c7.passed is False


def test_missing_snapshots_causes_failure(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    session = utils.OrganizeSession(root=root)
    vres = verify.verify(root, session=session, write_report=False)
    assert vres.passed is False
    assert any(c.code == "C0" for c in vres.checks)


def test_load_report_returns_none_when_absent(tmp_path: Path) -> None:
    root = tmp_path / "nr"
    root.mkdir()
    assert verify.load_report(root) is None


def test_severity_classification(sample_task: Path) -> None:
    # C6 is the only WARNING-level check; the rest are errors.
    _, vres = _full_run(sample_task)
    severities = {c.code: c.severity for c in vres.checks}
    assert severities["C6"] == "warning"
    assert severities["C1"] == "error"
    assert severities["C4"] == "error"
    assert severities["C7"] == "error"


def test_c8_passes_when_structure_complete(sample_task: Path) -> None:
    """After a full organize the structure is present -> C8 passes."""
    _, vres = _full_run(sample_task)
    c8 = next(c for c in vres.checks if c.code == "C8")
    assert c8.passed is True
    assert c8.severity == "warning"


def test_c8_warns_when_structure_missing(tmp_path: Path) -> None:
    """Loose files at the root but no three-tier structure -> C8 warns.

    This is the missed-init signal: the agent produced files but never ran
    init, so organize finds a bare folder. C8 must warn (never error,
    never block) and point at running init first.
    """
    root = tmp_path / "loose"
    root.mkdir()
    (root / "final_report.md").write_text("# final", encoding="utf-8")
    (root / "notes.txt").write_text("notes", encoding="utf-8")
    # no material/ process/ results/ yet
    assert utils.structure_complete(root) is False
    c8 = verify._run_c8(root, before=None)  # type: ignore[arg-type]
    assert c8.passed is False
    assert c8.severity == "warning"
    assert any("init" in d for d in c8.details)


def test_c8_ignores_tool_owned_root_files(tmp_path: Path) -> None:
    """Only the tool-owned .task-organizer.yml at the root is not "loose"."""
    root = tmp_path / "loose2"
    root.mkdir()
    (root / ".task-organizer.yml").write_text("# template", encoding="utf-8")
    c8 = verify._run_c8(root, before=None)  # type: ignore[arg-type]
    # no loose user files, so the message is the generic init hint
    assert c8.passed is False
    assert all(".task-organizer.yml" not in d for d in c8.details)
