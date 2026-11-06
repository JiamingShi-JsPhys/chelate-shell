"""Tests for aggregation and CSV export."""

from scripts.aggregator import Summary, aggregate, write_csv
from scripts.audit import RoundRecord


def _records():
    return [
        RoundRecord(round_no=1, status="success", params={"a": 1, "b": "x"},
                    input_hash="i1", output_hash="o1", timestamp="t1"),
        RoundRecord(round_no=2, status="failed", params={"a": 2, "b": "y"},
                    input_hash="i2", output_hash="o2", timestamp="t2"),
        RoundRecord(round_no=1, status="rolledback", params={},
                    note="rollback action"),
    ]


def test_aggregate_rows_and_columns():
    s = aggregate(_records(), ["a", "b"])
    assert len(s.rows) == 2  # rollback excluded
    assert s.rows[0]["round"] == 1
    assert s.rows[0]["a"] == 1 and s.rows[0]["b"] == "x"
    assert s.rows[1]["status"] == "failed"


def test_summary_filter():
    s = aggregate(_records(), ["a"])
    only_failed = s.filter(status="failed")
    assert len(only_failed.rows) == 1
    assert only_failed.rows[0]["round"] == 2


def test_write_csv(tmp_path):
    s = aggregate(_records(), ["a", "b"])
    p = tmp_path / "out.csv"
    write_csv(s, p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("round")
    assert len(lines) == 3  # header + 2 rows


def test_write_csv_empty(tmp_path):
    s = Summary(rows=[])
    p = tmp_path / "empty.csv"
    write_csv(s, p)
    assert p.read_text(encoding="utf-8") == ""
