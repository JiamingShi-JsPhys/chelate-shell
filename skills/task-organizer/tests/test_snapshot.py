"""Tests for :mod:`scripts.snapshot`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import snapshot, utils


def test_make_snapshot_before_creates_file(sample_task: Path) -> None:
    snap = snapshot.make_snapshot(sample_task, phase="before")
    proc = sample_task / utils.TIER_PROCESS
    files = list(proc.iterdir())
    names = [p.name for p in files if p.name.endswith("_before.json")]
    assert len(names) == 1
    # Snapshots are stored under process/.
    assert any(p.name.endswith("_before.json") for p in files)
    # The in-memory object reflects the files on disk.
    assert snap.file_count == len(snap.files)
    # Each entry has the required fields.
    for entry in snap.files:
        assert entry.rel_path
        assert entry.sha256 # non-empty digest for readable files
        assert entry.file_type == "file"


def test_make_snapshot_after_creates_file(sample_task: Path) -> None:
    snap = snapshot.make_snapshot(sample_task, phase="after")
    proc = sample_task / utils.TIER_PROCESS
    names = [p.name for p in proc.iterdir() if p.name.endswith("_after.json")]
    assert len(names) == 1


def test_snapshot_excludes_hidden(sample_task: Path) -> None:
    snap = snapshot.make_snapshot(sample_task, phase="before")
    rels = [f.rel_path for f in snap.files]
    assert not any(r.endswith(".hidden.md") for r in rels)


def test_snapshot_excludes_symlink(sample_task: Path) -> None:
    snap = snapshot.make_snapshot(sample_task, phase="before")
    rels = [f.rel_path for f in snap.files]
    # A symlink is not a regular file; the digest list should not include it
    # as its own entry (the target notes.txt appears exactly once).
    counts = [r for r in rels if r.endswith("notes.txt")]
    assert len(counts) == 1


def test_load_snapshot_roundtrip(sample_task: Path) -> None:
    snap = snapshot.make_snapshot(sample_task, phase="before")
    proc = sample_task / utils.TIER_PROCESS
    json_path = next(p for p in proc.iterdir() if p.name.endswith("_before.json"))

    loaded = snapshot.load_snapshot(json_path)
    assert loaded.file_count == snap.file_count
    assert loaded.phase == "before"
    # Dictionaries match key-by-key.
    assert loaded.to_dict()["files"] == snap.to_dict()["files"]


def test_find_latest_snapshot(sample_task: Path) -> None:
    snapshot.make_snapshot(sample_task, phase="before")
    found = snapshot.find_latest_snapshot(sample_task, "before")
    assert found is not None
    assert found.phase == "before"


def test_find_latest_snapshot_none_when_absent(sample_task: Path) -> None:
    found = snapshot.find_latest_snapshot(sample_task, "after")
    assert found is None


def test_snapshot_file_names(sample_task: Path) -> None:
    snapshot.make_snapshot(sample_task, phase="before")
    snapshot.make_snapshot(sample_task, phase="after")
    before_names = snapshot.snapshot_file_names(sample_task, "before")
    after_names = snapshot.snapshot_file_names(sample_task, "after")
    assert len(before_names) == 1
    assert len(after_names) == 1
    assert before_names[0].endswith("_before.json")
    assert after_names[0].endswith("_after.json")


def test_build_verification_inputs(sample_task: Path) -> None:
    snapshot.make_snapshot(sample_task, phase="before")
    snapshot.make_snapshot(sample_task, phase="after")
    inputs = snapshot.build_verification_inputs(sample_task)
    assert inputs["before"] is not None
    assert inputs["after"] is not None


def test_snapshot_deterministic_digest(sample_task: Path) -> None:
    """Same file content -> same SHA-256 across two snapshots."""
    s1 = snapshot.make_snapshot(sample_task, phase="before")
    s2 = snapshot.make_snapshot(sample_task, phase="before")
    d1 = {f.rel_path: f.sha256 for f in s1.files}
    d2 = {f.rel_path: f.sha256 for f in s2.files}
    assert d1 == d2


def test_snapshot_size_matches(sample_task: Path) -> None:
    snap = snapshot.make_snapshot(sample_task, phase="before")
    entry = next(f for f in snap.files if f.rel_path.endswith("notes.txt"))
    assert entry.size == len("hello notes")
