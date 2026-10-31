"""Tests for Markdown report rendering."""

from scripts.aggregator import Summary, aggregate
from scripts.audit import RoundRecord
from scripts.report import _table, write_draft, write_markdown


def _summary():
    recs = [
        RoundRecord(round_no=1, status="success", params={"a": 1},
                    input_hash="i1", output_hash="o1", timestamp="t1"),
        RoundRecord(round_no=2, status="failed", params={"a": 2},
                    input_hash="i2", output_hash="o2", timestamp="t2"),
    ]
    return aggregate(recs, ["a"])


def test_write_markdown(tmp_path):
    p = tmp_path / "results_summary.md"
    write_markdown(_summary(), p)
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# Results Summary")
    assert "| round |" in text
    assert "success" in text and "failed" in text


def test_write_draft(tmp_path):
    recs = [
        RoundRecord(round_no=1, status="success", params={"a": 1}),
        RoundRecord(round_no=2, status="failed", params={"a": 2}),
    ]
    p = tmp_path / "report_draft.md"
    write_draft(recs, _summary(), p)
    text = p.read_text(encoding="utf-8")
    assert "Total rounds executed" in text
    assert "success" in text and "failed" in text
    assert "Draft generated" in text


def test_empty_summary_renders_placeholder(tmp_path):
    md = _table([])
    assert "No rounds recorded" in md
    p = tmp_path / "results_summary.md"
    write_markdown(Summary(rows=[]), p)
    assert "Results Summary" in p.read_text(encoding="utf-8")
