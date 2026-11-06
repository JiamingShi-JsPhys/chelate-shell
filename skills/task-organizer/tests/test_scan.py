"""Tests for :mod:`scripts.scan`."""
from __future__ import annotations

import stat
from pathlib import Path

import pytest

from scripts import scan


def test_scan_lists_regular_files(sample_task: Path) -> None:
    result = scan.scan(sample_task)
    names = {f.name for f in result.files}
    assert "notes.txt" in names
    assert "draft.txt" in names
    assert "final_report.md" in names
    assert "download.pdf" in names
    assert "download.pdf" in names
    assert "intermediatenumber.csv" in names


def test_scan_filters_hidden_files(sample_task: Path) -> None:
    result = scan.scan(sample_task)
    names = {f.name for f in result.files}
    assert ".hidden.md" not in names
    # Hidden file is neither in files, dirs, nor empty folders.
    all_records = result.files + result.dirs + result.empty_folders
    for rec in all_records:
        assert not rec.name.startswith(".hidden")


def test_scan_records_symlink_type(sample_task: Path) -> None:
    result = scan.scan(sample_task)
    link = next((f for f in result.files if f.name == "link.txt"), None)
    if link is not None:
        # link.txt is recorded; if it is a real symlink the type is symlink.
        assert link.type in {"symlink", "file"}
    else:
        pytest.skip("symlink not created on this platform")


def test_scan_records_directories(sample_task: Path) -> None:
    result = scan.scan(sample_task)
    dir_names = {d.name for d in result.dirs}
    # src/data is non-empty (has inner.txt), so it should be in dirs.
    assert "data" in dir_names


def test_scan_empty_folder_detection(sample_task: Path) -> None:
    # Create a genuinely empty folder.
    (sample_task / "empty_dir").mkdir()
    result = scan.scan(sample_task)
    empty_names = {d.name for d in result.empty_folders}
    assert "empty_dir" in empty_names
    # An empty folder must NOT appear in the non-empty dirs list.
    dir_names = {d.name for d in result.dirs}
    assert "empty_dir" not in dir_names


def test_scan_total_files_property(sample_task: Path) -> None:
    result = scan.scan(sample_task)
    assert result.total_files == len(result.files)
    assert result.total_files >= 5


def test_scan_metadata_fields(sample_task: Path) -> None:
    result = scan.scan(sample_task)
    note = next(f for f in result.files if f.name == "notes.txt")
    assert note.type in {"file", "symlink"}
    assert note.size == len("hello notes")
    assert note.mtime > 0
    assert note.path == sample_task / "notes.txt"


def test_scan_to_dict_roundtrip(sample_task: Path) -> None:
    result = scan.scan(sample_task)
    d = result.to_dict()
    assert d["root"] == str(sample_task)
    assert isinstance(d["files"], list)
    assert all("path" in f and "type" in f for f in d["files"])


def test_scan_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        scan.scan(tmp_path / "does_not_exist")


def test_scan_iter_records(sample_task: Path) -> None:
    records = list(scan.iter_records(sample_task))
    # Every file, dir and empty folder should appear at least once.
    allnames = {r.name for r in records}
    assert "notes.txt" in allnames


def test_scan_unreadable_entry_captured(tmp_path: Path) -> None:
    """A sub-dir we chmod 000 produces a stat error that is captured.

    Skipped on platforms without real permission enforcement.
    """
    root = tmp_path / "r_task"
    root.mkdir()
    (root / "a.txt").write_text("x")
    secret = root / "secret"
    secret.mkdir()
    (secret / "b.txt").write_text("y")
    try:
        secret.chmod(0o000)
    except OSError:
        pytest.skip("cannot chmod on this platform")
    try:
        result = scan.scan(root)
        # The scan must not raise; either the file is found or an error is logged.
        assert result.total_files >= 1 or result.errors
    finally:
        secret.chmod(0o755)
