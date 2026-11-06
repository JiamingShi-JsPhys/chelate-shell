"""snapshot.py -- mandatory before/after directory snapshots.

This is the integrity backbone of the *forced verification* pipeline:

- :func:`make_snapshot` produces a structured JSON document that records,
  for **every regular file** under the scan root:
  absolute path, relative path, size, mtime, type, SHA-256.
- Snapshots are written to ``process/YYYYMMDD_HHMMSS_<before|after>.json``.
- :func:`load_snapshot` / :func:`find_latest_snapshot` round-trip the
  documents for :mod:`verify`.
- When ``use_cache=True`` (the ``--mode=incremental`` tier), files whose
  ``size`` + ``mtime`` are unchanged since the last snapshot reuse the
  cached digest instead of being re-hashed -- see :mod:`hashcache`.

The snapshot is the single source of truth verify.py diffs against. If the
before/after pair ever disagrees on file count, content hash, or missing
files, verification fails and :mod:`rollback` is triggered.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from scripts import utils
from scripts.hashcache import HashCache

SNAPSHOT_SCHEMA_VERSION = 1


@dataclass
class SnapshotFile:
    """One entry in a snapshot document."""

    rel_path: str
    abs_path: str
    size: int
    mtime: float
    file_type: str
    sha256: str

    def to_dict(self) -> dict:
        return {
            "rel_path": self.rel_path,
            "abs_path": self.abs_path,
            "size": self.size,
            "mtime": self.mtime,
            "type": self.file_type,
            "sha256": self.sha256,
        }


@dataclass
class Snapshot:
    """The full snapshot document.

    Attributes
    ----------
    root: absolute path of the scanned folder.
    created_at: ISO-8601 timestamp.
    phase: "before" | "after".
    files: list of :class:`SnapshotFile`.
    """

    root: str
    created_at: str
    phase: str
    files: List[SnapshotFile] = field(default_factory=list)
    schema_version: int = SNAPSHOT_SCHEMA_VERSION

    @property
    def file_count(self) -> int:
        return len(self.files)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "root": self.root,
            "created_at": self.created_at,
            "phase": self.phase,
            "file_count": self.file_count,
            "files": [f.to_dict() for f in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        """Re-hydrate a :class:`Snapshot` from :meth:`to_dict` output."""
        files = [
            SnapshotFile(
                rel_path=f["rel_path"],
                abs_path=f["abs_path"],
                size=f["size"],
                mtime=f["mtime"],
                file_type=f["type"],
                sha256=f["sha256"],
            )
            for f in data.get("files", [])
        ]
        return cls(
            root=data.get("root", ""),
            created_at=data.get("created_at", ""),
            phase=data.get("phase", "before"),
            files=files,
            schema_version=data.get("schema_version", SNAPSHOT_SCHEMA_VERSION),
        )


def make_snapshot(
    root: Path,
    phase: str = "before",
    out_path: Optional[Path] = None,
    timestamp: Optional[str] = None,
    use_cache: bool = False,
    cache: Optional["HashCache"] = None,
) -> Snapshot:
    """Build a :class:`Snapshot` for *root* and optionally write it to JSON.

    Parameters
    ----------
    root:
        Folder to snapshot. Symlinks and hidden files are excluded from the
        SHA-256 list (they are recorded elsewhere by :mod:`scan`), keeping the
        snapshot focused on the regular files whose integrity we guarantee.
    phase:
        "before" or "after" -- used only for the file name and metadata.
    out_path:
        Optional explicit output path. If omitted, the file is placed under
        ``process/`` following the ``YYYYMMDD_HHMMSS_<phase>.json`` rule.
    timestamp:
        Optional explicit stamp. Defaults to now.
    use_cache:
        When True, consult :mod:`hashcache` so files whose ``size`` + ``mtime``
        are unchanged reuse the previous digest instead of being re-hashed.
        The cache is rebuilt from this snapshot and persisted afterwards.
        Defaults to False so the full-verification tier always re-hashes.
    cache:
        An explicit :class:`~scripts.hashcache.HashCache` to consult instead of
        loading one from disk. Handy for callers that want to inspect the
        hit/miss counters after the call (the tests do exactly this). Ignored
        when ``use_cache`` is False, which keeps ``--mode=full`` honest.

    Returns
    -------
    Snapshot:
        The in-memory snapshot (also written to *out_path* when present).
    """
    root = Path(root).resolve()
    ts = timestamp or utils.now_stamp()
    if cache is None and use_cache:
        cache = HashCache.load(root)
    snap = _build(root, phase, ts, cache=cache)

    if out_path is None:
        out_path = root / utils.TIER_PROCESS / utils.snapshot_filename(
            phase, ts
        )
    utils.write_json(out_path, snap.to_dict())

    if cache is not None:
        cache.rebuild(snap.files)
        cache.save()
    return snap


def _build(
    root: Path,
    phase: str,
    ts: str,
    cache: Optional[HashCache] = None,
) -> Snapshot:
    """Internal: fill a :class:`Snapshot` with every regular file's digest.

    Auto-generated pipeline files (index / log / snapshot / report) are
    *excluded* from the digest list so that taking an "after" snapshot does
    not ingest its own "before" sibling JSON. Verification (verify.py) treats
    those files as the allow-listed additions instead.

    When *cache* is given, a file whose ``size`` + ``mtime`` match the cached
    entry skips the SHA-256 computation entirely.
    """
    files: List[SnapshotFile] = []
    for p in sorted(root.rglob("*")):
        if p.is_dir() or p.is_symlink():
            continue
        if utils.is_hidden(p):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        # Skip the tool's own generated artifacts (they are checked as
        # allow-listed new files by verify, not as user content).
        if utils.is_allowed_new_file(rel):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        digest: Optional[str] = None
        if cache is not None:
            digest = cache.get(rel, st.st_size, st.st_mtime)
        if digest is None:
            try:
                digest = utils.sha256_file(p)
            except OSError:
                digest = "" # unreadable file -- record but mark with empty digest
            if cache is not None:
                cache.put(rel, st.st_size, st.st_mtime, digest)
        files.append(
            SnapshotFile(
                rel_path=rel,
                abs_path=str(p),
                size=st.st_size,
                mtime=st.st_mtime,
                file_type="file",
                sha256=digest,
            )
        )
    return Snapshot(
        root=str(root),
        created_at=ts,
        phase=phase,
        files=files,
    )


def load_snapshot(path: Union[str, Path]) -> Snapshot:
    """Load a previously written snapshot JSON document."""
    data = utils.read_json(Path(path))
    return Snapshot.from_dict(data)


def find_latest_snapshot(
    root: Path, phase: str = "before"
) -> Optional[Snapshot]:
    """Find the most recent snapshot of *phase* under ``process/``.

    Used by :mod:`verify` and :mod:`rollback` to locate the reference state
    without hard-coding a file name (timestamps are not predictable).
    """
    snap_dir = Path(root) / utils.TIER_PROCESS
    if not snap_dir.is_dir():
        return None

    candidates: List[tuple] = []
    for p in snap_dir.iterdir():
        if not p.is_file():
            continue
        try:
            snap = load_snapshot(p)
        except Exception:
            continue
        if snap.phase == phase:
            candidates.append((p.name, snap))

    if not candidates:
        return None
    # File names start with a sortable YYYYMMDD_HHMMSS timestamp.
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][1]


def snapshot_file_names(
    root: Path, phase: str
) -> List[str]:
    """Return the on-disk file names of all *phase* snapshots under root."""
    snap_dir = Path(root) / utils.TIER_PROCESS
    if not snap_dir.is_dir():
        return []
    out: List[str] = []
    for p in snap_dir.iterdir():
        if p.is_file() and p.name.endswith(f"_{phase}.json"):
            out.append(p.name)
    out.sort()
    return out


def build_verification_inputs(
    root: Path,
    before: Optional[Snapshot] = None,
    after: Optional[Snapshot] = None,
) -> Dict[str, Snapshot]:
    """Locate (or accept) the before/after snapshots for verify.

    If *before* or *after* is omitted, the most recent snapshot of that phase
    is loaded from disk.
    """
    if before is None:
        before = find_latest_snapshot(root, "before")
    if after is None:
        after = find_latest_snapshot(root, "after")
    return {"before": before, "after": after}
