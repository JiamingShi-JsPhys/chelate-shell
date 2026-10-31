"""Standardized data export: CSV trajectories, JSON summaries, batch rollup.

All writers are pure (numpy only for math), so they are fully testable
without OpenCV. Raw video files are never modified — output lands under
the configured output directory.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .errors import TrackerError
from .tracker import ObjectResult

CSV_HEADER = ["frame", "time_s", "x_px", "y_px", "confidence", "reinit"]
CSV_HEADER_CM = CSV_HEADER + ["x_cm", "y_cm"]


def write_csv(results: list[ObjectResult], path: Path,
              scale: float | None = None) -> Path:
    """Write one standardized CSV with one column group per object.

    Columns: ``frame, time_s`` plus, per object,
    ``<name>_x_px, <name>_y_px, <name>_confidence, <name>_reinit``
    (and ``<name>_x_cm, <name>_y_cm`` when *scale* is given).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ["frame", "time_s"]
    for res in results:
        cols = [f"{res.name}_x_px", f"{res.name}_y_px",
                f"{res.name}_confidence", f"{res.name}_reinit"]
        if scale is not None:
            cols += [f"{res.name}_x_cm", f"{res.name}_y_cm"]
        header += cols
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        n_cols_per_obj = len(header) - 2
        n = max((len(r.points) for r in results), default=0)
        for i in range(n):
            row: list = []
            if i < len(results[0].points):
                row += [results[0].points[i].frame,
                        results[0].points[i].time_s]
            for res in results:
                if i < len(res.points):
                    p = res.points[i]
                    row += [p.x_px, p.y_px, p.confidence, p.reinit]
                    if scale is not None:
                        row += [round(p.x_px * scale, 3),
                                round(p.y_px * scale, 3)]
                else:
                    row += [""] * n_cols_per_obj
            writer.writerow(row)
    return path


def write_summary(summary: dict, path: Path) -> Path:
    """Write the video-level summary JSON (non-destructive, pretty)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def write_batch_summary(summaries: list[dict], path: Path) -> Path:
    """Aggregate per-video summaries into one batch JSON rollup."""
    if not summaries:
        raise TrackerError("write_batch_summary needs at least one summary")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rollup = {
        "n_videos": len(summaries),
        "total_frames": sum(s.get("n_frames", 0) for s in summaries),
        "objects_tracked": sum(len(s.get("objects", [])) for s in summaries),
        "videos": summaries,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rollup, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def load_summary(path: Path) -> dict:
    """Load a previously written summary JSON back into a dict."""
    p = Path(path)
    if not p.exists():
        raise TrackerError(f"summary not found: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TrackerError(f"summary is not valid JSON: {p}") from exc


def load_csv_rows(path: Path) -> list[list]:
    """Read back a standardized CSV (all cells as strings)."""
    p = Path(path)
    if not p.exists():
        raise TrackerError(f"csv not found: {p}")
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))
