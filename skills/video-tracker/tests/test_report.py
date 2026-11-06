"""Tests for Markdown report rendering."""

from __future__ import annotations

from pathlib import Path

from scripts.report import _table, write_report, write_report_from_files


def _table_rows():
    rows = [
        ("metric", "value"),
        ("success_rate", "0.85"),
        ("lost_frames", "[3, 4]"),
    ]
    out = _table(rows)
    assert out.startswith("| metric")
    assert "0.85" in out


def test_table_empty():
    assert _table([]) == "_(no data)_\n"


def test_table_single_column():
    out = _table([("a",), ("b",)])
    assert "| a |" in out or "a" in out


def test_write_report(tmp_path):
    summary = {
        "video": "x.mp4",
        "fps": 30.0,
        "fps_source": "config",
        "n_frames": 100,
        "frame_width": 640,
        "frame_height": 480,
        "scale_cm_per_px": 0.05,
        "objects": [
            {
                "object": "ball",
                "roi": {"x": 1, "y": 2, "w": 3, "h": 4},
                "frames_tracked": 100,
                "success_rate": 0.9,
                "lost_frames": [5],
                "reinit_frames": [5],
                "tracker_losses": 1,
            }
        ],
    }
    p = write_report(summary, tmp_path / "rep.md")
    text = p.read_text(encoding="utf-8")
    assert "x.mp4" in text
    assert "ball" in text
    assert "success_rate" in text


def test_write_report_with_fft(tmp_path):
    summary = {
        "video": "x.mp4",
        "n_frames": 50,
        "objects": [],
        "fft": {
            "ball.x_px": {
                "dominant_freq_hz": 1.2,
                "dominant_amplitude": 3.4,
                "period_s": 0.83,
                "top_peaks": [(1.2, 3.4)],
            }
        },
    }
    p = write_report(summary, tmp_path / "rep.md")
    text = p.read_text(encoding="utf-8")
    assert "Spectral analysis" in text
    assert "ball.x_px" in text


def test_write_report_from_files(tmp_path):
    import json

    summary_path = tmp_path / "s.json"
    summary_path.write_text(
        json.dumps({"video": "v.mp4", "n_frames": 10, "objects": []}),
        encoding="utf-8",
    )
    fft_path = tmp_path / "f.json"
    fft_path.write_text(
        json.dumps(
            {"signals": [{"signal": "ball.x_px", "dominant_freq_hz": 0.5}]}
        ),
        encoding="utf-8",
    )
    p = write_report_from_files(summary_path, fft_path, tmp_path / "r.md")
    text = p.read_text(encoding="utf-8")
    assert "v.mp4" in text
    assert "Spectral analysis" in text
    assert "ball.x_px" in text


def test_write_report_from_files_no_fft(tmp_path):
    import json

    summary_path = tmp_path / "s.json"
    summary_path.write_text(
        json.dumps({"video": "v.mp4", "n_frames": 10, "objects": []}),
        encoding="utf-8",
    )
    p = write_report_from_files(summary_path, None, tmp_path / "r.md")
    text = p.read_text(encoding="utf-8")
    assert "Spectral analysis" not in text
