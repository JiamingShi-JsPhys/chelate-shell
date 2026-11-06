"""Tests for :mod:`scripts.sources` -- the provenance manifest .

The manifest is the authoritative answer to "where does this file go", so
these tests pin down the two guarantees it exists for:

- **provenance beats filename** (a user file named ``download_notes.pdf``
  is still the user's material);
- **user material is verbatim** (never renamed).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import sources, utils


# ---------------------------------------------------------------------------
# construction / path
# ---------------------------------------------------------------------------


def test_manifest_path_is_under_process(tmp_path: Path) -> None:
    man = sources.SourceManifest(root=tmp_path)
    assert man.path == tmp_path / utils.TIER_PROCESS / sources.MANIFEST_NAME


def test_load_missing_manifest_is_empty(tmp_path: Path) -> None:
    man = sources.SourceManifest.load(tmp_path)
    assert man.counts() == {"user": 0, "downloaded": 0}


def test_load_corrupt_manifest_is_empty(tmp_path: Path) -> None:
    proc = tmp_path / utils.TIER_PROCESS
    proc.mkdir(parents=True)
    (proc / sources.MANIFEST_NAME).write_text("{ not json", encoding="utf-8")
    man = sources.SourceManifest.load(tmp_path)
    assert man.counts() == {"user": 0, "downloaded": 0}


def test_load_non_dict_manifest_is_empty(tmp_path: Path) -> None:
    proc = tmp_path / utils.TIER_PROCESS
    proc.mkdir(parents=True)
    (proc / sources.MANIFEST_NAME).write_text("[1, 2, 3]", encoding="utf-8")
    man = sources.SourceManifest.load(tmp_path)
    assert man.counts() == {"user": 0, "downloaded": 0}


# ---------------------------------------------------------------------------
# registration / queries
# ---------------------------------------------------------------------------


def test_add_and_kind_of(tmp_path: Path) -> None:
    man = sources.SourceManifest(root=tmp_path)
    assert man.add(sources.KIND_USER, "notes.txt") is True
    assert man.kind_of("notes.txt") == sources.KIND_USER
    assert man.is_verbatim("notes.txt") is True


def test_add_is_idempotent_and_preserves_metadata(tmp_path: Path) -> None:
    man = sources.SourceManifest(root=tmp_path)
    assert man.add(sources.KIND_USER, "a.txt", url="http://x", note="n") is True
    first_at = man.user[0].at
    # Second registration changes nothing -- the original stamp survives.
    assert man.add(sources.KIND_USER, "a.txt", url="http://other") is False
    assert man.user[0].url == "http://x"
    assert man.user[0].at == first_at


def test_add_matches_on_basename_only(tmp_path: Path) -> None:
    man = sources.SourceManifest(root=tmp_path)
    man.add(sources.KIND_USER, "a.txt")
    # A path is registered (and looked up) by its basename.
    assert man.kind_of("some/deep/a.txt") == sources.KIND_USER


def test_downloaded_wins_over_user(tmp_path: Path) -> None:
    """Same name, both provenances recorded: the download is the more
    specific claim, so it wins (the assistant fetched this very file)."""
    man = sources.SourceManifest(root=tmp_path)
    man.add(sources.KIND_USER, "paper.pdf")
    man.add(sources.KIND_DOWNLOADED, "paper.pdf")
    assert man.kind_of("paper.pdf") == sources.KIND_DOWNLOADED
    # ... and it is therefore *not* protected by the verbatim guarantee.
    assert man.is_verbatim("paper.pdf") is False


def test_kind_of_unknown_returns_none(tmp_path: Path) -> None:
    man = sources.SourceManifest(root=tmp_path)
    assert man.kind_of("nope.txt") is None


def test_record_user_files_counts_new_only(tmp_path: Path) -> None:
    man = sources.SourceManifest(root=tmp_path)
    added = man.record_user_files([tmp_path / "a.txt", tmp_path / "b.txt"])
    assert added == 2
    assert man.record_user_files([tmp_path / "a.txt", tmp_path / "c.txt"]) == 1
    assert sorted(man.names(sources.KIND_USER)) == ["a.txt", "b.txt", "c.txt"]


def test_remove_clears_both_lists(tmp_path: Path) -> None:
    man = sources.SourceManifest(root=tmp_path)
    man.add(sources.KIND_USER, "x.txt")
    man.add(sources.KIND_DOWNLOADED, "x.txt")
    assert man.remove("x.txt") is True
    assert man.kind_of("x.txt") is None
    assert man.remove("x.txt") is False


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    man = sources.SourceManifest(root=tmp_path)
    man.add(sources.KIND_USER, "my_notes.txt", note="hand-written")
    man.add(sources.KIND_DOWNLOADED, "paper.pdf", url="https://arxiv.org/abs/1")
    written = man.save()
    assert written is not None and written.exists()

    loaded = sources.SourceManifest.load(tmp_path)
    assert loaded.kind_of("my_notes.txt") == sources.KIND_USER
    assert loaded.is_verbatim("my_notes.txt") is True
    assert loaded.kind_of("paper.pdf") == sources.KIND_DOWNLOADED
    assert loaded.downloaded[0].url == "https://arxiv.org/abs/1"


def test_save_tolerates_bare_string_shorthand(tmp_path: Path) -> None:
    proc = tmp_path / utils.TIER_PROCESS
    proc.mkdir(parents=True)
    (proc / sources.MANIFEST_NAME).write_text(
        '{"user": ["legacy.txt"], "downloaded": []}', encoding="utf-8"
    )
    man = sources.SourceManifest.load(tmp_path)
    assert man.kind_of("legacy.txt") == sources.KIND_USER


def test_manifest_is_path_whitelisted_for_verify(tmp_path: Path) -> None:
    """The manifest must not count as an unauthorized new file."""
    assert utils.is_allowed_new_file(f"{utils.TIER_PROCESS}/{sources.MANIFEST_NAME}")


def test_is_manifest_is_path_exact() -> None:
    """A user file that merely happens to be called sources.json is NOT the
    manifest -- it must stay visible to integrity verification."""
    assert sources.is_manifest("process/sources.json")
    assert sources.is_manifest("process\\sources.json")
    assert not sources.is_manifest("sources.json")
    assert not sources.is_manifest("material/initial/sources.json")


def test_manifest_path_helper(tmp_path: Path) -> None:
    assert sources.manifest_path(tmp_path) == (
        tmp_path / utils.TIER_PROCESS / sources.MANIFEST_NAME
    )
