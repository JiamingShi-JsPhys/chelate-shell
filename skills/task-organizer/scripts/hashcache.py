"""hashcache.py -- incremental hashing cache.

Why this exists
---------------
The full mode hashes **every** file on every run. On a large research
folder that is the dominant cost, and it is pure waste for the files that
nobody touched since the last run.

This module keeps a small JSON document under ``process/.hash_cache.json``
mapping ``rel_path -> (size, mtime, sha256)``. A file is only re-hashed
when its ``size`` **or** ``mtime`` differs from the cached entry -- the
classic "stat-only" incremental heuristic. Static files are therefore
free, and only new / modified / freshly-moved files pay for a digest.

Safety model
------------
- The cache is a **pure optimisation**: a stale entry can only make
  verification *more* permissive in incremental mode, never in full mode
  (full mode never consults the cache). Incremental mode is documented as
  the "weekly cleanup" tier; ``--mode=full`` remains the guarantee tier.
- The file is hidden (leading dot), so it never appears in snapshots or in
  verify's C6 addition check -- it cannot perturb the forced verification.
- The cache is rebuilt from the snapshot it was derived from, so it can
  never drift away from an on-disk reality we actually observed.
- Deleting the file is always safe: the next run simply re-hashes.

The cache is keyed by *relative* path. A file that was moved therefore
misses the cache and is re-hashed -- which is exactly what we want, since
verification must still prove the moved file's content is intact.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from scripts import utils

#: File name of the cache document, stored directly under ``process/``.
CACHE_FILENAME = ".hash_cache.json"

CACHE_SCHEMA_VERSION = 1


@dataclass
class CacheEntry:
    """One cached digest together with the stat pair that validates it."""

    size: int
    mtime: float
    sha256: str

    def to_dict(self) -> dict:
        return {"size": self.size, "mtime": self.mtime, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, d: dict) -> "CacheEntry":
        return cls(
            size=int(d.get("size", -1)),
            mtime=float(d.get("mtime", -1.0)),
            sha256=str(d.get("sha256", "")),
        )

    def matches(self, size: int, mtime: float) -> bool:
        """True when a file with this ``(size, mtime)`` may reuse the digest."""
        return self.size == size and self.mtime == mtime and bool(self.sha256)


@dataclass
class HashCache:
    """In-memory view of the on-disk hash cache for one task root."""

    root: Path
    entries: Dict[str, CacheEntry] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    # -- construction ------------------------------------------------------

    @property
    def path(self) -> Path:
        """Absolute path of the cache document (``<root>/process/.hash_cache.json``)."""
        return Path(self.root) / utils.TIER_PROCESS / CACHE_FILENAME

    @classmethod
    def load(cls, root: Path) -> "HashCache":
        """Load the cache for *root*; a missing/corrupt file yields an empty cache."""
        cache = cls(root=Path(root))
        p = cache.path
        if not p.is_file():
            return cache
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Unreadable cache is never fatal -- just start over.
            return cache
        raw = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return cache
        for rel, entry in raw.items():
            if isinstance(entry, dict):
                cache.entries[str(rel)] = CacheEntry.from_dict(entry)
        return cache

    # -- lookup / update ---------------------------------------------------

    def get(self, rel_path: str, size: int, mtime: float) -> Optional[str]:
        """Return a reusable digest for *rel_path*, or ``None`` to re-hash."""
        entry = self.entries.get(rel_path)
        if entry is not None and entry.matches(size, mtime):
            self.hits += 1
            return entry.sha256
        self.misses += 1
        return None

    def put(self, rel_path: str, size: int, mtime: float, sha256: str) -> None:
        """Record (or refresh) the digest for *rel_path*."""
        self.entries[rel_path] = CacheEntry(size=size, mtime=mtime, sha256=sha256)

    def rebuild(self, files) -> None:
        """Replace the cache contents with the digest table of *files*.

        *files* is any iterable of :class:`scripts.snapshot.SnapshotFile`
        (or anything exposing ``rel_path`` / ``size`` / ``mtime`` /
        ``sha256``). Rebuilding (rather than merging) is what keeps the
        cache from accumulating stale entries for files that moved away.
        """
        self.entries = {}
        for f in files:
            self.entries[f.rel_path] = CacheEntry(
                size=f.size, mtime=f.mtime, sha256=f.sha256
            )

    # -- persistence -------------------------------------------------------

    def save(self) -> Optional[Path]:
        """Persist the cache. Never raises; returns the written path or None."""
        p = self.path
        try:
            utils.write_json(
                p,
                {
                    "schema_version": CACHE_SCHEMA_VERSION,
                    "root": str(Path(self.root).resolve()),
                    "entries": {k: v.to_dict() for k, v in self.entries.items()},
                },
            )
            return p
        except OSError:
            return None

    def stats(self) -> Dict[str, int]:
        """Return ``{"hits": .., "misses": ..}`` for logging / tests."""
        return {"hits": self.hits, "misses": self.misses}


def cache_path(root: Path) -> Path:
    """Return the cache document path for *root* without loading it."""
    return HashCache(root=root).path
