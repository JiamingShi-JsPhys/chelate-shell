"""Shared pytest fixtures for task-organizer tests.

Layout:

- ``sample_task``: an on-disk task folder built under tmp_path, containing a
  realistic mix of files that exercise every placement rule, plus edge cases
  (hidden file, symlink, nested loose file, an already-present standard dir).
- ``empty_task``: a task folder with no files.
- ``task_with_readonly``: a task containing one read-only file (POSIX-safe).

All fixtures are directory-based so tests can assert real filesystem state.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the project root (which contains the ``scripts`` package) is importable
# regardless of how pytest is invoked (from repo root, from task-organizer/,
# or via an IDE). This makes the suite runnable out-of-the-box.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _make_file(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture()
def sample_task(tmp_path: Path) -> Path:
    """Build a representative task folder.

    provenance model -- the destination is decided by *who produced
    the file*, never by its name:

    Top-level files:
      - ``draft.txt``              -> process (draft keyword)
      - ``final_report.md``        -> results (final keyword)
      - ``intermediatenumber.csv`` -> process (intermediate keyword)
      - ``notes.txt``              -> process (no keyword -> assistant output)
      - ``download.pdf``           -> process (a *name* containing "download"
                                      is NOT provenance; only
                                      ``mark-downloaded`` makes it a download)

    Edge cases:
      - ``.hidden.md`` hidden, must be skipped
      - a symlink ``link.txt`` must be skipped
      - a sub-folder ``src/`` is relocated **whole** into material/initial/
    """
    root = tmp_path / "task"
    root.mkdir()

    _make_file(root / "notes.txt", "hello notes")
    _make_file(root / "draft.txt", "draft content")
    _make_file(root / "final_report.md", "# final report")
    _make_file(root / "download.pdf", "binary-ish")
    _make_file(root / "intermediatenumber.csv", "a,b\n1,2")

    # Hidden file -- must never be touched.
    _make_file(root / ".hidden.md", "secret")

    # Symlink -- must be skipped.
    link = root / "link.txt"
    try:
        link.symlink_to(root / "notes.txt")
    except (OSError, NotImplementedError): # pragma: no cover - e.g. no symlink perm
        link.write_text("not-a-real-symlink", encoding="utf-8")

    # A user sub-folder -- relocated whole, structure preserved.
    _make_file(root / "src" / "data" / "inner.txt", "inner loose file")

    return root


@pytest.fixture()
def user_task(tmp_path: Path) -> Path:
    """A folder the user filled by hand and then ran ``init`` on.

    Everything in here is the user's own material, so it must end up in
    ``material/initial/`` with names and structure untouched.
    """
    root = tmp_path / "user_task"
    root.mkdir()
    _make_file(root / "my_notes.txt", "my notes")
    _make_file(root / "download_notes.pdf", "user file whose NAME says download")
    _make_file(root / "papers" / "a.txt", "paper a")
    _make_file(root / "papers" / "b.txt", "paper b")

    from scripts import init as init_mod

    init_mod.init_folder(root)
    return root


@pytest.fixture()
def empty_task(tmp_path: Path) -> Path:
    """A task folder with no files at all."""
    root = tmp_path / "empty_task"
    root.mkdir()
    return root


@pytest.fixture()
def task_with_readonly(tmp_path: Path) -> Path:
    """A task containing one read-only file (best-effort chmod)."""
    root = tmp_path / "readonly_task"
    root.mkdir()
    _make_file(root / "locked.txt", "cannot move")
    _make_file(root / "normal.txt", "can move")
    try:
        root.joinpath("locked.txt").chmod(0o444)
    except OSError: # pragma: no cover - Windows may ignore chmod
        pass
    return root


@pytest.fixture()
def pre_snapshot(sample_task: Path):
    """A helper that captures a before-snapshot of *sample_task*.

    Returns ``(snapshot_object, snapshot_json_path)``.
    """
    from scripts import snapshot

    snap = snapshot.make_snapshot(sample_task, phase="before")
    proc = sample_task / "process"
    json_path = next(p for p in proc.iterdir() if p.name.endswith("_before.json"))
    return snap, json_path
