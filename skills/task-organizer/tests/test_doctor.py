"""Tests for the read-only ``doctor`` diagnostics command.

Doctor is a pure triage step: it inspects a folder, reports what looks
wrong (incomplete structure, stranded root files, stale/absent broadcast
index), and prints a single "next step".  It never mutates the folder --
these tests assert exactly that, plus the diagnostic correctness across
the four meaningful states: healthy, missed-init, stale broadcast,
absent broadcast, and a nonexistent root.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import doctor as _doc


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #
def _healthy_folder(root: Path) -> Path:
    """A folder that has been fully organized and broadcast (healthy)."""
    for sub in ("material/initial", "material/downloaded", "process", "results"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "material" / "initial" / "notes.txt").write_text("notes", encoding="utf-8")
    (root / "results" / "final_report.md").write_text("# R\nok", encoding="utf-8")
    from scripts import broadcast, utils
    bc = broadcast.broadcast(root, use_ai=False, max_files=5,
                             keywords_per_file=8, quiet=True)
    assert bc.ok
    return root


# ------------------------------------------------------------------ #
# tests
# ------------------------------------------------------------------ #
def test_doctor_reports_healthy_on_a_fully_organized_folder(tmp_path: Path) -> None:
    root = tmp_path / "task"
    _healthy_folder(root)
    res = _doc.doctor(root, quiet=True)
    assert res.ok, f"expected healthy, got: {res.summary_lines()}"
    assert res.structure_complete
    assert not res.loose_root_files
    assert not res.deliverable_loose_files
    assert res.broadcast_present and res.broadcast_fresh
    assert "healthy" in res.next_step


def test_doctor_flags_missed_init_and_advises_classify(tmp_path: Path) -> None:
    # A folder that has a results-looking file stranded at the root but no
    # structure -> doctor should call out the missed-init signal and point
    # at `init --classify`.
    root = tmp_path / "task"
    root.mkdir()
    (root / "final_report.md").write_text("# deliverable", encoding="utf-8")
    res = _doc.doctor(root, quiet=True)
    assert not res.structure_complete
    assert "final_report.md" in res.deliverable_loose_files
    assert "init --classify" in res.next_step


def test_doctor_flags_stale_broadcast_after_a_new_file(tmp_path: Path) -> None:
    import time
    root = _healthy_folder(tmp_path / "task")
    # Drop a *new* source file in after the broadcast was built.  Sleep past
    # the one-second generated_at grace window so its mtime strictly
    # post-dates the recorded generation time and is flagged stale.
    time.sleep(1.2)
    (root / "material" / "initial" / "fresh_note.txt").write_text(
        "new thing", encoding="utf-8"
    )
    res = _doc.doctor(root, quiet=True)
    assert res.broadcast_present
    assert not res.broadcast_fresh
    assert "broadcast" in res.next_step


def test_doctor_reports_absent_broadcast(tmp_path: Path) -> None:
    root = tmp_path / "task"
    for sub in ("material/initial", "material/downloaded", "process", "results"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "material" / "initial" / "notes.txt").write_text("n", encoding="utf-8")
    res = _doc.doctor(root, quiet=True)
    assert res.structure_complete
    assert not res.broadcast_present
    assert not res.broadcast_fresh


def test_doctor_on_nonexistent_root_reports_gracefully(tmp_path: Path) -> None:
    res = _doc.doctor(tmp_path / "does-not-exist", quiet=True)
    assert not res.structure_complete
    assert "does not exist" in res.next_step


def test_doctor_makes_no_changes_to_the_folder(tmp_path: Path) -> None:
    # The contract that makes doctor *always safe*: capture the full
    # (relpath, mtime, size) state before and after, and prove it is
    # byte-identical.
    import os

    root = _healthy_folder(tmp_path / "task")

    def _state() -> dict:
        out = {}
        for dirpath, _dirs, files in os.walk(root, followlinks=False):
            for fn in files:
                p = Path(dirpath) / fn
                try:
                    st = p.stat()
                    out[str(p)] = (round(st.st_mtime, 3), st.st_size)
                except OSError:
                    pass
        return out

    before = _state()
    _doc.doctor(root, quiet=True)
    after = _state()
    assert before == after, "doctor mutated the folder tree"
