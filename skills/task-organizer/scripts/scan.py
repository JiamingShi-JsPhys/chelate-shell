"""scan.py -- recursive directory scanner.

Public API
----------
- :func:`scan` -- scan a folder and return a list of file records.
- :func:`iter_records` -- streaming iterator (lazy) for very large trees.
- :class:`FileRecord` -- one scanned entry with its metadata.

Behavior contract
----------------
- Recurses into sub-directories (except hidden ones).
- Identifies each entry as file / directory / symlink.
- Filters out hidden entries (any path component starts with ``.``).
- Records empty folders separately (they are *not* files, so they appear in
  ``empty_folders`` on the returned :class:`ScanResult`).
- Symlinks are recorded but never followed (type="symlink").
- Never raises on individual unreadable entries -- they are skipped and the
  reason is appended to ``errors``.
"""
from __future__ import annotations

import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Set


@dataclass
class FileRecord:
    """Metadata for one scanned entry.

    Attributes
    ----------
    path: absolute :class:`Path`.
    type: one of ``"file" | "dir" | "symlink"``.
    size: byte size (0 for directories/symlinks pointing to dirs).
    mtime: POSIX mtime as float.
    name: base name.
    """

    path: Path
    type: str
    size: int = 0
    mtime: float = 0.0
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.path.name

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "type": self.type,
            "size": self.size,
            "mtime": self.mtime,
            "name": self.name,
        }


@dataclass
class ScanResult:
    """Aggregated result of a scan.

    - ``files``: every regular file (including symlink-to-file).
    - ``dirs``: every non-empty directory.
    - ``empty_folders``: directories with zero children.
    - ``errors``: list of ``(path, reason)`` for entries that could not be
      fully inspected.
    """

    root: Path
    files: List[FileRecord] = field(default_factory=list)
    dirs: List[FileRecord] = field(default_factory=list)
    empty_folders: List[FileRecord] = field(default_factory=list)
    errors: List[tuple] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_dirs(self) -> int:
        return len(self.dirs) + len(self.empty_folders)

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "files": [f.to_dict() for f in self.files],
            "dirs": [d.to_dict() for d in self.dirs],
            "empty_folders": [e.to_dict() for e in self.empty_folders],
            "errors": [{"path": p, "reason": r} for p, r in self.errors],
        }


def _is_hidden(p: Path, root: Path) -> bool:
    """Return True if *p* (relative to *root*) has any hidden component.

    The root itself is never considered hidden.
    """
    try:
        rel = p.relative_to(root)
    except ValueError:
        return False
    for part in rel.parts:
        if part.startswith(".") and part not in (".", ".."):
            return True
    return False


def _stat_safe(p: Path) -> Optional[stat]:
    """Safe stat that returns None instead of raising."""
    try:
        return os.stat(p)
    except OSError:
        return None


def _classify(p: Path, st) -> Optional[str]:
    """Return 'file' | 'dir' | 'symlink' | None (unreadable)."""
    if p.is_symlink():
        return "symlink"
    if st is None:
        return None
    mode = st.st_mode
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "dir"
    # Other types (fifo, socket, device) -- treat as a skipped file.
    return "file"


def _collect(
    root: Path,
    files: List[FileRecord],
    dirs: List[FileRecord],
    empty_folders: List[FileRecord],
    errors: List[tuple],
) -> None:
    """Fill the record lists by walking *root* breadth-first."""
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if _is_hidden(child, root):
            continue

        st = _stat_safe(child)
        kind = _classify(child, st)
        if kind is None:
            errors.append((str(child), "stat failed"))
            continue

        # Determine empty-ness early so we can sort dirs vs empty_folders.
        is_empty = False
        size = 0
        mtime = 0.0
        try:
            if child.is_dir() and not child.is_symlink():
                is_empty = len(list(child.iterdir())) == 0
            if child.is_file() or child.is_symlink():
                if st is not None:
                    size = st.st_size
                    mtime = st.st_mtime
        except OSError as exc:
            errors.append((str(child), f"inspect failed: {exc}"))
            continue

        if kind == "dir":
            rec = FileRecord(path=child, type="dir", mtime=mtime)
            if is_empty:
                empty_folders.append(rec)
            else:
                dirs.append(rec)
                # Recurse only into non-empty, non-hidden directories.
                _collect(child, files, dirs, empty_folders, errors)
        else:
            # 'file' or 'symlink'
            files.append(
                FileRecord(
                    path=child,
                    type=kind,
                    size=size,
                    mtime=mtime,
                    name=child.name,
                )
            )


def iter_records(root: Path) -> Iterator[FileRecord]:
    """Lazy iterator over every file record under *root*.

    Useful when the tree is huge and callers do not need the aggregated
    :class:`ScanResult`.
    """
    result = scan(root)
    yield from result.files
    for d in result.dirs:
        yield d
    for e in result.empty_folders:
        yield e


def scan(root: Path) -> ScanResult:
    """Recursively scan *root* and return a :class:`ScanResult`.

    Parameters
    ----------
    root:
        Absolute path of the folder to scan. Hidden entries are filtered.

    Returns
    -------
    ScanResult:
        Aggregated files / dirs / empty_folders / errors.

    Notes
    -----
    - This function is *pure read* -- it never mutates the filesystem.
    - Symlinks are recorded as type="symlink" but are NOT followed.
    - Unreadable entries are captured in ``errors`` instead of raising.
    """
    if not root.is_dir():
        raise FileNotFoundError(f"scan target is not a directory: {root}")

    files: List[FileRecord] = []
    dirs: List[FileRecord] = []
    empty_folders: List[FileRecord] = []
    errors: List[tuple] = []

    _collect(Path(root).resolve(), files, dirs, empty_folders, errors)

    # Stable sort by path for deterministic downstream consumers.
    files.sort(key=lambda r: str(r.path))
    dirs.sort(key=lambda r: str(r.path))
    empty_folders.sort(key=lambda r: str(r.path))

    return ScanResult(
        root=Path(root).resolve(),
        files=files,
        dirs=dirs,
        empty_folders=empty_folders,
        errors=errors,
    )
