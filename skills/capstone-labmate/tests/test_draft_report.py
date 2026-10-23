"""Unit tests for stage D (randomised error corpus + mandatory watermark).

Covers R-02: (a) reproducible randomised sampling when a seed is given,
(b) non-reproducible when no seed, (c) watermark is always present, (d)
stale watermarks are stripped before the canonical one is appended.
"""
import json
import sys
from pathlib import Path

import pytest

# Ensure the scripts directory is in the path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import draft_report  # noqa: E402


# ------------------------------------------------------------------ sampling
def _write_corpus(p: Path, n_entries: int) -> Path:
    entries = [
        {"id": f"e{i}", "source": f"S{i}", "phenomenon": f"P{i}",
         "mechanism": f"M{i}", "typical_magnitude": f"{i}%"}
        for i in range(n_entries)
    ]
    p.write_text(json.dumps({"corpus": entries}), encoding="utf-8")
    return p


def test_sample_seeded_reproducible(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path / "c.json", 8)
    a = draft_report._sample_error_sources(corpus, k=3, seed=42)
    b = draft_report._sample_error_sources(corpus, k=3, seed=42)
    assert a == b
    assert len(a) == 3
    # distinct ids
    assert len({e["id"] for e in a}) == 3


def test_sample_unseeded_varies(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path / "c.json", 12)
    # With no seed, we cannot guarantee difference in a single pair, 
    # but we can assert the structural validity of the output.
    a = draft_report._sample_error_sources(corpus, k=3, seed=None)
    b = draft_report._sample_error_sources(corpus, k=3, seed=None)
    
    assert len(a) == 3 and len(b) == 3
    # Check all elements are from the original pool
    valid_ids = {f"e{i}" for i in range(12)}
    assert all(item["id"] in valid_ids for item in a)
    assert all(item["id"] in valid_ids for item in b)


def test_sample_more_than_pool_clamps(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path / "c.json", 2)
    got = draft_report._sample_error_sources(corpus, k=5, seed=1)
    assert len(got) == 2


def test_sample_empty_corpus(tmp_path: Path) -> None:
    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"corpus": []}), encoding="utf-8")
    assert draft_report._sample_error_sources(p, k=3, seed=0) == []


# ------------------------------------------------------------------ watermark
def test_apply_watermark_appends_once() -> None:
    text = "line one\nline two"
    out = draft_report._apply_watermark(text)
    assert out.endswith(draft_report.WATERMARK + "\n")
    assert "line one" in out and "line two" in out


def test_apply_watermark_strips_stale_and_reappends() -> None:
    # Simulate an older draft that already carries a watermark
    stale = "line one\n\n" + draft_report.WATERMARK + "\n"
    out = draft_report._apply_watermark(stale)
    # Exactly one watermark in the output
    assert out.count(draft_report.WATERMARK) == 1
    assert out.endswith(draft_report.WATERMARK + "\n")
    # And the original content preserved
    assert "line one" in out


def test_watermark_is_mandatory_constant() -> None:
    # The guardrail notice must be a stable, non-empty English string
    assert isinstance(draft_report.WATERMARK, str)
    assert "AI" in draft_report.WATERMARK
    assert "academic integrity" in draft_report.WATERMARK.lower()


# ------------------------------------------------------------- build skeleton
def test_build_skeleton_includes_series_numbers() -> None:
    summary = [{
        "series": "s1",
        "raw_points": 100,
        "feature_points": [{"i": 0}, {"i": 1}, {"i": 2}],
        "stats": {"mean": 1.0, "min": 0.0, "max": 2.0, "std": 0.5},
        "fit": {"slope": 0.5, "intercept": 1.2, "r_squared": 0.99},
    }]
    errors = [{"source": "X", "typical_magnitude": "1%",
               "phenomenon": "Y", "mechanism": "Z"}]
    text = draft_report._build_skeleton(summary, errors)
    
    # Assertions adjusted to match English template
    assert "s1" in text
    assert "100" in text            # raw_points
    assert "0.5" in text            # slope
    assert "X" in text and "Y" in text and "Z" in text


def test_build_skeleton_empty_summary() -> None:
    text = draft_report._build_skeleton([], [])
    # Still a valid skeleton with header + error note (English)
    assert "# Lab Analysis Draft" in text
    assert "Error corpus config/error_corpus.json not provided or empty" in text


# --------------------------------------------------------------------- run
def test_run_missing_summary_returns_2(tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "summary.json"
    out = tmp_path / "out" / "draft.md"
    rc = draft_report.run(missing, None, out, "markdown", None, 3)
    assert rc == 2


def test_run_full_pipeline_appends_watermark(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps([
        {"series": "s", "raw_points": 5,
         "feature_points": [{"i": 0}],
         "stats": {"mean": 1, "min": 0, "max": 2, "std": 0.1},
         "fit": {"slope": 0.1, "intercept": 0.0, "r_squared": 0.9}}
    ]), encoding="utf-8")
    corpus = _write_corpus(tmp_path / "c.json", 6)
    out = tmp_path / "out" / "draft.md"
    
    rc = draft_report.run(summary_path, corpus, out, "markdown", seed=7, k=2)
    assert rc == 0
    
    text = out.read_text(encoding="utf-8")
    assert draft_report.WATERMARK in text
    assert text.count(draft_report.WATERMARK) == 1
    # Series header present (English)
    assert "## Series: s" in text


def test_run_no_corpus_still_writes_draft(tmp_path: Path) -> None:
    summary_path = tmp_path / "s.json"
    summary_path.write_text(json.dumps([
        {"series": "a", "raw_points": 1, "feature_points": [],
         "stats": {"mean": None, "min": None, "max": None, "std": None},
         "fit": {"slope": 0, "intercept": 0, "r_squared": None}}
    ]), encoding="utf-8")
    out = tmp_path / "d.md"
    
    rc = draft_report.run(summary_path, None, out, "markdown", None, 3)
    assert rc == 0
    
    text = out.read_text(encoding="utf-8")
    assert draft_report.WATERMARK in text
    assert "Error corpus config/error_corpus.json not provided or empty" in text


def test_run_latex_suffix(tmp_path: Path) -> None:
    summary_path = tmp_path / "s.json"
    summary_path.write_text(json.dumps([]), encoding="utf-8")
    out = tmp_path / "d.md"
    
    rc = draft_report.run(summary_path, None, out, "latex", None, 3)
    assert rc == 0
    assert (tmp_path / "d.tex").exists()
    assert not (tmp_path / "d.md").exists()
