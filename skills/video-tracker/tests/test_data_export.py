"""Tests for standardized CSV / JSON export."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.data_export import (
    load_csv_rows,
    load_summary,
    write_batch_summary,
    write_csv,
    write_summary,
)
from scripts.errors import TrackerError
from scripts.tracker import ObjectResult, ObjectROI, TrajectoryPoint


def _res(name="ball", n=4):
    roi = ObjectROI(name, 0, 0, 1, 1)
    points = [
        TrajectoryPoint(i, i / 30.0, 10.0 + i, 20.0 - i, 1.0 if i < 2 else 0.0,
                        i == 2)
        for i in range(n)
    ]
    r = ObjectResult(name=name, roi=roi, points=points)
    r.lost_frames = [i for i in range(n) if i >= 2][:2]
    r.reinit_frames = [2]
    return r


def test_write_csv_no_scale(tmp_path):
    p = write_csv([_res()], tmp_path / "out" / "a.csv")
    rows = load_csv_rows(p)
    assert rows[0] == ["frame", "time_s", "ball_x_px", "ball_y_px",
                       "ball_confidence", "ball_reinit"]
    assert len(rows) == 5  # header + 4 points
    assert rows[1][0] == "0"


def test_write_csv_with_scale(tmp_path):
    p = write_csv([_res()], tmp_path / "b.csv", scale=0.5)
    rows = load_csv_rows(p)
    assert rows[0][-2:] == ["ball_x_cm", "ball_y_cm"]
    # x_px=10 -> x_cm=5.0
    assert rows[1][len(rows[0]) - 2] == "5.0"


def test_write_csv_multiple_objects(tmp_path):
    p = write_csv([_res("a"), _res("b", n=3)], tmp_path / "c.csv")
    rows = load_csv_rows(p)
    header = rows[0]
    assert "a_x_px" in header and "b_x_px" in header
    # b has only 3 points; row 4 should leave b's cells empty.
    assert rows[4][header.index("b_x_px")] == ""


def test_write_summary_roundtrip(tmp_path):
    summary = {"n_frames": 10, "fps": 30.0, "objects": [{"object": "x"}]}
    p = write_summary(summary, tmp_path / "s.json")
    loaded = load_summary(p)
    assert loaded == summary


def test_load_summary_missing(tmp_path):
    with pytest.raises(TrackerError):
        load_summary(tmp_path / "nope.json")


def test_load_summary_bad_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(TrackerError):
        load_summary(p)


def test_write_batch_summary(tmp_path):
    s1 = {"n_frames": 10, "objects": [{"object": "a"}]}
    s2 = {"n_frames": 20, "objects": [{"object": "b"}, {"object": "c"}]}
    p = write_batch_summary([s1, s2], tmp_path / "batch.json")
    loaded = load_summary(p)
    assert loaded["n_videos"] == 2
    assert loaded["total_frames"] == 30
    assert loaded["objects_tracked"] == 3


def test_write_batch_summary_empty(tmp_path):
    with pytest.raises(TrackerError):
        write_batch_summary([], tmp_path / "b.json")


def test_object_success_rate():
    r = _res()
    # 4 points, frames 2 and 3 lost -> success = 2/4
    assert r.success_rate == pytest.approx(0.5)


def test_object_success_rate_empty():
    r = ObjectResult(name="x", roi=ObjectROI("x", 0, 0, 1, 1))
    assert r.success_rate == 0.0


def test_object_rows_with_scale():
    r = _res()
    rows = r.rows(scale=2.0)
    assert len(rows[0]) == 8  # 6 base + x_cm + y_cm
    # x_px=10 -> x_cm=20
    assert rows[0][6] == pytest.approx(20.0)


def test_object_summary_shape():
    s = _res().summary()
    assert s["object"] == "ball"
    assert s["frames_tracked"] == 4
    assert s["lost_frames"] == [2, 3]
    assert s["reinit_frames"] == [2]
    assert s["success_rate"] == pytest.approx(0.5)
