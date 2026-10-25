"""Tests for :mod:`scripts.hashcache` -- incremental hashing .

The cache is a pure optimisation, so the tests focus on the two properties
that make it safe:

- a digest is reused **only** when both ``size`` and ``mtime`` still match;
- a corrupt / missing cache degrades to "re-hash everything" instead of
  failing the run.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import List

from scripts import hashcache, utils


class _FakeSnapshotFile:
    """Minimal stand-in exposing the four attributes rebuild() needs."""

    def __init__(self, rel_path: str, size: int, mtime: float, sha256: str) -> None:
        self.rel_path = rel_path
        self.size = size
        self.mtime = mtime
        self.sha256 = sha256


def _files(*specs) -> List[_FakeSnapshotFile]:
    return [_FakeSnapshotFile(*s) for s in specs]


# ---------------------------------------------------------------------------
# path
# ---------------------------------------------------------------------------


def test_cache_path_is_hidden_under_process(tmp_path: Path) -> None:
    cache = hashcache.HashCache(root=tmp_path)
    assert cache.path == tmp_path / utils.TIER_PROCESS / hashcache.CACHE_FILENAME
    # Leading dot keeps it out of snapshots and verify's addition check.
    assert hashcache.CACHE_FILENAME.startswith(".")


def test_cache_file_is_not_an_allowed_new_file(tmp_path: Path) -> None:
    """The cache must never be mistaken for a pipeline artifact."""
    rel = f"{utils.TIER_PROCESS}/{hashcache.CACHE_FILENAME}"
    assert utils.is_allowed_new_file(rel) is False


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------


def test_miss_on_empty_cache(tmp_path: Path) -> None:
    cache = hashcache.HashCache(root=tmp_path)
    assert cache.get("a.txt", 10, 1.0) is None
    assert cache.misses == 1 and cache.hits == 0


def test_hit_when_size_and_mtime_match(tmp_path: Path) -> None:
    cache = hashcache.HashCache(root=tmp_path)
    cache.put("a.txt", 10, 1.0, "deadbeef")
    assert cache.get("a.txt", 10, 1.0) == "deadbeef"
    assert cache.hits == 1


def test_miss_when_size_differs(tmp_path: Path) -> None:
    cache = hashcache.HashCache(root=tmp_path)
    cache.put("a.txt", 10, 1.0, "deadbeef")
    assert cache.get("a.txt", 11, 1.0) is None


def test_miss_when_mtime_differs(tmp_path: Path) -> None:
    cache = hashcache.HashCache(root=tmp_path)
    cache.put("a.txt", 10, 1.0, "deadbeef")
    assert cache.get("a.txt", 10, 2.0) is None


def test_empty_digest_is_never_a_hit(tmp_path: Path) -> None:
    cache = hashcache.HashCache(root=tmp_path)
    cache.put("a.txt", 10, 1.0, "")
    assert cache.get("a.txt", 10, 1.0) is None


# ---------------------------------------------------------------------------
# rebuild
# ---------------------------------------------------------------------------


def test_rebuild_replaces_stale_entries(tmp_path: Path) -> None:
    cache = hashcache.HashCache(root=tmp_path)
    cache.put("gone.txt", 1, 1.0, "old")
    cache.rebuild(_files(("a.txt", 10, 1.0, "aaa")))
    assert "gone.txt" not in cache.entries
    assert cache.entries["a.txt"].sha256 == "aaa"


def test_rebuild_accepts_snapshot_objects(tmp_path: Path) -> None:
    from scripts import snapshot

    root = tmp_path / "task"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")
    snap = snapshot.make_snapshot(root, phase="before", out_path=None)
    cache = hashcache.HashCache(root=root)
    cache.rebuild(snap.files)
    assert cache.entries["a.txt"].sha256 == snap.files[0].sha256


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    cache = hashcache.HashCache(root=tmp_path)
    cache.put("a.txt", 10, 1.5, "aaa")
    cache.put("sub/b.bin", 20, 2.5, "bbb")
    written = cache.save()
    assert written is not None and written.exists()

    loaded = hashcache.HashCache.load(tmp_path)
    assert loaded.get("a.txt", 10, 1.5) == "aaa"
    assert loaded.get("sub/b.bin", 20, 2.5) == "bbb"


def test_load_corrupt_cache_is_empty(tmp_path: Path) -> None:
    proc = tmp_path / utils.TIER_PROCESS
    proc.mkdir(parents=True)
    (proc / hashcache.CACHE_FILENAME).write_text("{ oops", encoding="utf-8")
    cache = hashcache.HashCache.load(tmp_path)
    assert cache.entries == {}


def test_load_cache_with_wrong_shape_is_empty(tmp_path: Path) -> None:
    proc = tmp_path / utils.TIER_PROCESS
    proc.mkdir(parents=True)
    (proc / hashcache.CACHE_FILENAME).write_text(
        '{"entries": "not-a-dict"}', encoding="utf-8"
    )
    cache = hashcache.HashCache.load(tmp_path)
    assert cache.entries == {}


def test_cache_path_helper(tmp_path: Path) -> None:
    assert hashcache.cache_path(tmp_path) == (
        tmp_path / utils.TIER_PROCESS / hashcache.CACHE_FILENAME
    )


def test_moved_file_misses_the_cache(tmp_path: Path) -> None:
    """A relocated file is keyed by relative path, so it must be re-hashed."""
    root = tmp_path / "task"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")
    st = (root / "a.txt").stat()
    cache = hashcache.HashCache(root=root)
    cache.put("a.txt", st.st_size, st.st_mtime, "cached-digest")
    # Same bytes, different location -> different key -> miss.
    assert cache.get("process/a.txt", st.st_size, st.st_mtime) is None


def test_stats_reports_hits_and_misses(tmp_path: Path) -> None:
    cache = hashcache.HashCache(root=tmp_path)
    cache.put("a.txt", 1, 1.0, "x")
    cache.get("a.txt", 1, 1.0)
    cache.get("b.txt", 1, 1.0)
    assert cache.stats() == {"hits": 1, "misses": 1}


def test_real_file_digest_is_reused(tmp_path: Path) -> None:
    """End-to-end: an untouched file is hashed once, then served from cache."""
    root = tmp_path / "task"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")
    st = (root / "a.txt").stat()
    digest = utils.sha256_file(root / "a.txt")

    cache = hashcache.HashCache(root=root)
    assert cache.get("a.txt", st.st_size, st.st_mtime) is None
    cache.put("a.txt", st.st_size, st.st_mtime, digest)
    assert cache.get("a.txt", st.st_size, st.st_mtime) == digest

    # Touching the file (new mtime) invalidates the entry.
    time.sleep(0.01)
    (root / "a.txt").write_text("hello!", encoding="utf-8")
    st2 = (root / "a.txt").stat()
    assert cache.get("a.txt", st2.st_size, st2.st_mtime) is None
