"""Unit tests for the document-evolution-tracker core modules."""

from __future__ import annotations

from pathlib import Path

from src.align import align_versions
from src.config import EvoConfig, Granularity, load_config
from src.diff_blocks import BlockDiff, diff_blocks, split_blocks
from src.lineage import build_lineage
from src.versioning import Version, discover_versions


# ---------------------------------------------------------------------------
# versioning.py
# ---------------------------------------------------------------------------

def test_discover_sequential_orders_by_number(tmp_path: Path) -> None:
    (tmp_path / "v3.md").write_text("3")
    (tmp_path / "v1.md").write_text("1")
    (tmp_path / "v2.md").write_text("2")
    versions = discover_versions(tmp_path, "sequential")
    assert [v.version_id for v in versions] == ["v1.md", "v2.md", "v3.md"]


def test_discover_timestamp_orders_by_stamp(tmp_path: Path) -> None:
    (tmp_path / "2026-01-05.md").write_text("a")
    (tmp_path / "2026-01-01.md").write_text("b")
    (tmp_path / "2026-01-03.md").write_text("c")
    versions = discover_versions(tmp_path, "timestamp")
    ids = [v.version_id for v in versions]
    assert ids == ["2026-01-01.md", "2026-01-03.md", "2026-01-05.md"]


def test_discover_missing_dir_raises(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(FileNotFoundError):
        discover_versions(tmp_path / "nope", "sequential")


def test_discover_non_doc_files_ignored(tmp_path: Path) -> None:
    (tmp_path / "v1.md").write_text("1")
    (tmp_path / "notes.txt.bak").write_text("x")
    versions = discover_versions(tmp_path, "sequential")
    assert [v.version_id for v in versions] == ["v1.md"]


# ---------------------------------------------------------------------------
# diff_blocks.py
# ---------------------------------------------------------------------------

def test_split_blocks_line() -> None:
    blocks = split_blocks("a\n\nb\nc", Granularity.LINE)
    assert blocks == ["a", "b", "c"]


def test_split_blocks_paragraph() -> None:
    text = "para one\n\npara two\n\npara three"
    blocks = split_blocks(text, Granularity.PARAGRAPH)
    assert blocks == ["para one", "para two", "para three"]


def test_split_blocks_sentence() -> None:
    text = "First. Second! Third?"
    blocks = split_blocks(text, Granularity.SENTENCE)
    assert blocks == ["First.", "Second!", "Third?"]


def test_diff_blocks_added_removed() -> None:
    d = diff_blocks("alpha\n\nbeta", "alpha\n\ngamma", Granularity.PARAGRAPH)
    assert isinstance(d, BlockDiff)
    # "beta" removed, "gamma" added, "alpha" equal.
    tags = [c.tag for c in d.changes]
    assert "removed" in tags and "added" in tags
    assert d.added == 1
    assert d.removed == 1


def test_diff_blocks_identical_no_changes() -> None:
    d = diff_blocks("same\n\ntext", "same\n\ntext", Granularity.PARAGRAPH)
    assert d.changes == []
    assert d.added == d.removed == d.modified == 0


def test_diff_blocks_to_dict_roundtrip() -> None:
    d = diff_blocks("a", "b")
    payload = d.to_dict()
    assert payload["old"] == "old"
    assert payload["new"] == "new"
    assert isinstance(payload["changes"], list)


# ---------------------------------------------------------------------------
# align.py
# ---------------------------------------------------------------------------

def test_align_versions_yields_pairwise(tmp_path: Path) -> None:
    (tmp_path / "v1.md").write_text("one")
    (tmp_path / "v2.md").write_text("two")
    (tmp_path / "v3.md").write_text("three")
    versions = discover_versions(tmp_path, "sequential")
    diffs = align_versions(versions, Granularity.LINE)
    assert len(diffs) == 2
    assert diffs[0].old_label == "v1.md" and diffs[0].new_label == "v2.md"


def test_align_single_version_empty(tmp_path: Path) -> None:
    (tmp_path / "v1.md").write_text("only")
    versions = discover_versions(tmp_path, "sequential")
    assert align_versions(versions) == []


# ---------------------------------------------------------------------------
# lineage.py
# ---------------------------------------------------------------------------

def _versions(tmp_path: Path, contents: dict) -> list:
    for name, text in contents.items():
        (tmp_path / name).write_text(text)
    return discover_versions(tmp_path, "sequential")


def test_lineage_introduced_retained_dropped(tmp_path: Path) -> None:
    versions = _versions(tmp_path, {
        "v1.md": "Alpha baseline",
        "v2.md": "Alpha learned",
        "v3.md": "only other text",
    })
    texts = {v.version_id: v.path.read_text(encoding="utf-8") for v in versions}
    lineage = build_lineage(versions, texts, concepts=["Alpha"])
    states = [n.state for n in lineage["Alpha"]]
    assert states == ["introduced", "retained", "dropped"]


def test_lineage_auto_detect_headings(tmp_path: Path) -> None:
    versions = _versions(tmp_path, {
        "v1.md": "# Intro\n\n# Method\n",
        "v2.md": "# Intro\n\n# Method\n\n# Results\n",
    })
    texts = {v.version_id: v.path.read_text(encoding="utf-8") for v in versions}
    lineage = build_lineage(versions, texts, concepts=None, auto_detect_headings=True)
    assert "Intro" in lineage
    assert "Results" in lineage
    # "Results" is introduced only in v2.
    res_states = {n.version_id: n.state for n in lineage["Results"]}
    assert res_states["v2.md"] == "introduced"


def test_lineage_no_concepts_no_auto() -> None:
    v = [Version(version_id="v1.md", path=Path("v1.md"))]
    assert build_lineage(v, {"v1.md": "text"}, concepts=None, auto_detect_headings=False) == {}


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------

def test_config_validate_bad_granularity(tmp_path: Path) -> None:
    import yaml

    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"tracking_id": "t", "versions_dir": "x", "granularity": "bogus"}), encoding="utf-8")
    try:
        load_config(p)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_config_validate_bad_naming(tmp_path: Path) -> None:
    import yaml

    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"tracking_id": "t", "versions_dir": "x", "version_naming": "bogus"}), encoding="utf-8")
    try:
        load_config(p)
        assert False, "expected ValueError"
    except ValueError:
        pass
