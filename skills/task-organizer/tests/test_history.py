"""Tests for :mod:`scripts.history` -- operation history + undo/redo ."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import history, run, snapshot, utils


def _organized_task(tmp_path: Path) -> Path:
    """Build a task and run the full pipeline so a history file exists."""
    root = tmp_path / "task"
    root.mkdir()
    (root / "notes.txt").write_text("hello", encoding="utf-8")
    (root / "draft.txt").write_text("draft", encoding="utf-8")
    res = run.run(root)
    assert res.ok
    return root


# ---------------------------------------------------------------------------
# write_history
# ---------------------------------------------------------------------------


def test_write_history_creates_file(sample_task: Path) -> None:
    res = run.run(sample_task)
    assert res.history_path is not None
    assert res.history_path.exists()
    assert res.history_path.suffix == ".json"
    # It must live under process/history/.
    parent = res.history_path.parent
    assert parent.name == history.HISTORY_DIRNAME


def test_write_history_records_moved_actions(sample_task: Path) -> None:
    res = run.run(sample_task)
    h = history.History.from_dict(utils.read_json(res.history_path))
    # Only 'moved' records are persisted (skips are excluded).
    for a in h.actions:
        assert a.action == "move"
    assert len(h.actions) >= 1


def test_write_history_serialization_roundtrip(sample_task: Path) -> None:
    res = run.run(sample_task)
    h = history.History.from_dict(utils.read_json(res.history_path))
    # to_dict -> from_dict must preserve the action list.
    rehydrated = history.History.from_dict(h.to_dict())
    assert len(rehydrated.actions) == len(h.actions)
    assert rehydrated.root == h.root


# ---------------------------------------------------------------------------
# undo / redo
# ---------------------------------------------------------------------------


def test_undo_restores_original_locations(tmp_path: Path) -> None:
    root = _organized_task(tmp_path)
    notes = root / "process" / "notes.txt"
    assert notes.exists()
    # Use the newest history from the single organizing run.
    hfile = history.latest_history(root)
    assert hfile is not None

    hr = history.undo(hfile, root=root)
    assert hr.ok
    assert hr.conflicts == []
    # After undo the file is back at the root (its original location).
    assert (root / "notes.txt").exists()
    assert not notes.exists()


def test_redo_reapplies_after_undo(tmp_path: Path) -> None:
    root = _organized_task(tmp_path)
    hfile = history.latest_history(root)
    history.undo(hfile, root=root)
    assert (root / "notes.txt").exists()

    hr = history.redo(hfile, root=root)
    assert hr.ok
    # Redo moves the file back into the tier.
    assert (root / "process" / "notes.txt").exists()
    assert not (root / "notes.txt").exists()


def test_undo_with_lost_file_is_reported_not_crash(tmp_path: Path) -> None:
    root = _organized_task(tmp_path)
    hfile = history.latest_history(root)
    assert hfile is not None
    # Manually delete a moved file to simulate a lost source.
    target = root / "process" / "notes.txt"
    target.unlink()
    hr = history.undo(hfile, root=root)
    # undo should surface a conflict rather than raising.
    assert hr.conflicts
    # The lost move must be reported.
    assert any("notes" in c for c in hr.conflicts)


# ---------------------------------------------------------------------------
# latest_history
# ---------------------------------------------------------------------------


def test_latest_history_returns_newest(sample_task: Path) -> None:
    run.run(sample_task)
    latest = history.latest_history(sample_task)
    assert latest is not None
    assert latest.suffix == ".json"
    # A second run produces a newer file; latest must point to it.
    run.run(sample_task)
    latest2 = history.latest_history(sample_task)
    assert latest2 is not None
    assert latest2.name >= latest.name


def test_latest_history_missing_returns_none(tmp_path: Path) -> None:
    assert history.latest_history(tmp_path / "no_such") is None
