"""Tests for :mod:`scripts.dedupe` -- smart duplicate detection ."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import dedupe, snapshot, utils, verify


def _mk(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Exact duplicate detection
# ---------------------------------------------------------------------------


def test_find_exact_duplicates(sample_task: Path) -> None:
    # sample_task already has notes.txt + a symlink link.txt -> notes.txt, but
    # the symlink is skipped. Add two real identical files to guarantee a group.
    _mk(sample_task / "a.txt", "same content")
    _mk(sample_task / "b.txt", "same content")
    rep = dedupe.find_duplicates(sample_task)
    assert len(rep.exact_groups) >= 1
    # The 'a.txt' / 'b.txt' pair must appear together in some group.
    found = [g for g in rep.exact_groups if any(g.endswith("a.txt") for g in g)]
    assert found


def test_no_duplicates_when_unique(tmp_path: Path) -> None:
    _mk(tmp_path / "x.txt", "one")
    _mk(tmp_path / "y.txt", "two")
    rep = dedupe.find_duplicates(tmp_path)
    assert rep.exact_groups == []
    assert rep.similar_pairs == []


# ---------------------------------------------------------------------------
# Similar duplicate detection
# ---------------------------------------------------------------------------


def test_find_similar_duplicates(tmp_path: Path) -> None:
    base = "The quick brown fox jumps over the lazy dog. " * 40
    _mk(tmp_path / "doc1.txt", base)
    _mk(tmp_path / "doc2.txt", base[: len(base) - 5] + "!!!")
    rep = dedupe.find_duplicates(tmp_path)
    # doc1/doc2 are near-identical -> at least one similar pair (not exact).
    assert rep.similar_pairs, "expected a similar pair"
    ratios = [r for _a, _b, r in rep.similar_pairs]
    assert all(r >= dedupe.SIMILAR_THRESHOLD for r in ratios)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def test_write_report_creates_file(sample_task: Path) -> None:
    _mk(sample_task / "dup1.txt", "identical")
    _mk(sample_task / "dup2.txt", "identical")
    rep = dedupe.find_duplicates(sample_task)
    path = dedupe.write_report(sample_task, rep)
    assert path.exists()
    assert path.name == utils.DUPLICATE_REPORT_NAME
    text = path.read_text(encoding="utf-8")
    assert "Exact duplicate" in text


# ---------------------------------------------------------------------------
# Action modes
# ---------------------------------------------------------------------------


def test_report_mode_is_non_destructive(sample_task: Path) -> None:
    _mk(sample_task / "dup1.txt", "identical")
    _mk(sample_task / "dup2.txt", "identical")
    res = dedupe.run_dedupe(sample_task, action="report")
    assert res.ok
    assert res.action == "report"
    assert res.moved_count == 0
    # Neither file was moved; both still at their original locations.
    assert (sample_task / "dup1.txt").exists()
    assert (sample_task / "dup2.txt").exists()


def test_move_mode_quarantines_exact_dups(sample_task: Path) -> None:
    _mk(sample_task / "dup1.txt", "identical")
    _mk(sample_task / "dup2.txt", "identical")
    session = utils.OrganizeSession(root=sample_task)
    res = dedupe.run_dedupe(sample_task, action="move", session=session)
    assert res.action == "move"
    assert res.moved_count >= 1
    dup_dir = sample_task / utils.TIER_ORGANIZE / dedupe.DUPLICATES_DIRNAME
    assert dup_dir.is_dir()
    # At least one exact duplicate was relocated; originals are never deleted,
    # so the *total* number of files with this content is unchanged.
    total = sum(1 for p in sample_task.rglob("dup?.txt"))
    assert total == 2  # two copies, no loss


def test_move_mode_moves_are_session_recorded(sample_task: Path) -> None:
    _mk(sample_task / "dup1.txt", "identical")
    _mk(sample_task / "dup2.txt", "identical")
    session = utils.OrganizeSession(root=sample_task)
    dedupe.run_dedupe(sample_task, action="move", session=session)
    # Every quarantine move must be recorded so verify/rollback can audit it.
    assert any(rec.status == "moved" for rec in session.move_records)


def test_run_dedupe_verified_move_passes(sample_task: Path) -> None:
    _mk(sample_task / "dup1.txt", "identical")
    _mk(sample_task / "dup2.txt", "identical")
    res = dedupe.run_dedupe_verified(sample_task, action="move")
    assert res.ok
    assert res.moved_count >= 1


def test_run_dedupe_report_action_uses_plain_path(sample_task: Path) -> None:
    res = dedupe.run_dedupe_verified(sample_task, action="report")
    assert res.ok
    assert res.action == "report"
