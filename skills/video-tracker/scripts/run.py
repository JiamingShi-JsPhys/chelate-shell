#!/usr/bin/env python3
"""video-tracker CLI.

Subcommands:

    probe   Inspect video container metadata without tracking.
    track   Track all declared objects; write CSV + JSON under the output dir.
    fft     Run FFT spectrum analysis over an existing CSV + summary JSON.
    report  (Re)generate the combined report + spectra PNG from outputs.
    demo    Run a built-in synthetic pendulum demo (no video needed).

All outputs are written under the configured ``output`` directory; the raw
video is never modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python scripts/run.py` (no package context) as well as
# `python -m scripts.run`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "scripts"

from . import __version__  # noqa: E402
from .config import load_config  # noqa: E402
from .errors import TrackerError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="video-tracker",
                                description="Extract motion data from experiment videos.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd")

    def _common(sp):
        sp.add_argument("--config", required=True, help="config JSON/YAML path")
        sp.add_argument("--output", help="override the config's output directory")
        sp.add_argument("--video-index", type=int, default=0,
                       help="which video in the config to process (default 0)")

    sp = sub.add_parser("probe", help="show container metadata (no tracking)")
    _common(sp)

    sp = sub.add_parser("track", help="track objects, write CSV + JSON")
    _common(sp)

    sp = sub.add_parser("fft", help="FFT spectrum over an existing CSV+JSON")
    _common(sp)
    sp.add_argument("--no-plots", action="store_true",
                   help="skip PNG figures (JSON report only)")

    sp = sub.add_parser("physics",
                       help="physics-consistency probes over an existing CSV+JSON")
    _common(sp)
    sp.add_argument("--family", default="unknown",
                   choices=["linear", "circular", "harmonic",
                            "lissajous", "damped", "spiral", "unknown"],
                   help="expected motion law (selects the conservation invariant)")
    sp.add_argument("--fx", type=float, default=None,
                   help="design frequency of the x motion (Hz)")
    sp.add_argument("--fy", type=float, default=None,
                   help="design frequency of the y motion (Hz)")
    sp.add_argument("--cx", type=float, default=None,
                   help="equilibrium x of the design motion (pixels)")
    sp.add_argument("--cy", type=float, default=None,
                   help="equilibrium y of the design motion (pixels)")
    sp.add_argument("--reference-csv", default=None,
                   help="optional reference CSV (ground truth) for per-object deltas")
    sp.add_argument("--per-object", default=None,
                   help='JSON string of per-object physics params, e.g. '
                        '\'{"A": {"family":"lissajous","fx":0.5,"fy":0.6,'
                        '"cx":200,"cy":180}}\'. Overrides the global --family/'
                        '--fx/--fy/--cx/--cy on a per-object basis (needed for '
                        'multi-object videos where each body follows a different law)')

    sp = sub.add_parser("report", help="regenerate report + spectra PNG")
    _common(sp)

    sp = sub.add_parser("demo", help="run the built-in synthetic demo")
    sp.add_argument("--config", help="optional config (output dir / fps override)")
    sp.add_argument("--output", help="output directory (default ./output/demo)")

    return p


def _probe(cv2, path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise TrackerError(f"could not open video: {path}")
    info = {
        "path": str(path),
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "n_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "duration_s": 0.0,
    }
    info["duration_s"] = (
        round(info["n_frames"] / info["fps"], 3) if info["fps"] > 0 else 0.0
    )
    cap.release()
    return info


def cmd_probe(cfg, args) -> int:
    import cv2

    infos = [_probe(cv2, v) for v in cfg.videos]
    print(json.dumps(infos, indent=2))
    return 0


def _output_root(cfg, args) -> Path:
    out = Path(args.output) if args.output else cfg.output
    return out


def cmd_track(cfg, args) -> int:
    from .data_export import write_csv, write_summary
    from .tracker import track_video

    cfg.validate(require_fps=False)
    out = _output_root(cfg, args)
    out.mkdir(parents=True, exist_ok=True)

    summary, results = track_video(cfg, args.video_index)
    base = Path(summary["video"]).name
    csv_path = out / f"{base}_tracking.csv"
    write_csv(results, csv_path, cfg.scale_cm_per_px)
    json_path = out / f"{base}_summary.json"
    write_summary(summary, json_path)
    print(json.dumps(
        {
            "csv": str(csv_path),
            "json": str(json_path),
            "n_frames": summary["n_frames"],
            "fps": summary["fps"],
            "objects": [r["object"] for r in summary["objects"]],
            "success_rates": {
                o["object"]: o["success_rate"] for o in summary["objects"]
            },
        },
        indent=2,
    ))
    return 0


def cmd_fft(cfg, args) -> int:
    from .data_export import load_csv_rows, load_summary
    from .fft_analyzer import analyze_object, write_spectra
    from .tracker import ObjectResult, TrajectoryPoint

    out = _output_root(cfg, args)
    base = Path(cfg.videos[args.video_index]).name
    csv_path = out / f"{base}_tracking.csv"
    json_path = out / f"{base}_summary.json"
    summary = load_summary(json_path)
    rows = load_csv_rows(csv_path)

    fps = float(cfg.fps if cfg.fps is not None else summary.get("fps") or 30.0)
    results: list[ObjectResult] = []
    for i, obj in enumerate(cfg.objects):
        name = obj.name
        prefix = f"{name}_"
        x_col = next((c for c in rows[0] if c == f"{prefix}x_px"), None)
        y_col = next((c for c in rows[0] if c == f"{prefix}y_px"), None)
        if x_col is None or y_col is None:
            raise TrackerError(
                f"CSV missing columns for object {name!r} ({prefix}x_px / y_px)"
            )
        x_idx = rows[0].index(x_col)
        y_idx = rows[0].index(y_col)
        points = []
        for row in rows[1:]:
            frame_i = int(float(row[0]))
            time_s = float(row[1])
            x = float(row[x_idx])
            y = float(row[y_idx])
            points.append(TrajectoryPoint(frame_i, time_s, x, y, 1.0, False))
        results.append(ObjectResult(name=name, roi=obj, points=points))

    specs = []
    analyses = []
    for res in results:
        oa = analyze_object(res.points, res.name, fps, cfg.scale_cm_per_px,
                            cfg.fft_max_freq, cfg.fft_top_peaks)
        analyses.append(oa.to_dict())
        specs.append(oa.x)
        specs.append(oa.y)
        if oa.x_cm is not None and oa.y_cm is not None:
            specs.append(oa.x_cm)
            specs.append(oa.y_cm)

    png = None if args.no_plots else out / f"{base}_spectra.png"
    json_report = out / f"{base}_fft.json"
    traj = {
        r.name: ([p.x_px for p in r.points], [p.y_px for p in r.points])
        for r in results
    }
    write_spectra(specs, json_report, png, trajectories=traj)
    print(json.dumps(
        {"fft_json": str(json_report), "png": str(png) if png else None,
         "analyses": analyses},
        indent=2, ensure_ascii=False,
    ))
    return 0


def cmd_physics(cfg, args) -> int:
    from .data_export import load_csv_rows, load_summary
    from .physics import compare_trajectories, score_trajectory
    from .tracker import ObjectResult, TrajectoryPoint

    out = _output_root(cfg, args)
    base = Path(cfg.videos[args.video_index]).name
    csv_path = out / f"{base}_tracking.csv"
    json_path = out / f"{base}_summary.json"
    summary = load_summary(json_path)
    rows = load_csv_rows(csv_path)

    fps = float(cfg.fps if cfg.fps is not None else summary.get("fps") or 30.0)
    dt = 1.0 / fps
    center = (args.cx, args.cy) if (args.cx is not None or args.cy is not None) else None

    def _object_points(obj_name: str) -> list[TrajectoryPoint]:
        prefix = f"{obj_name}_"
        x_col = next((c for c in rows[0] if c == f"{prefix}x_px"), None)
        y_col = next((c for c in rows[0] if c == f"{prefix}y_px"), None)
        if x_col is None or y_col is None:
            raise TrackerError(
                f"CSV missing columns for object {obj_name!r} "
                f"({prefix}x_px / {prefix}y_px)"
            )
        xi, yi = rows[0].index(x_col), rows[0].index(y_col)
        pts: list[TrajectoryPoint] = []
        for row in rows[1:]:
            if not row or row[xi] == "" or row[yi] == "":
                continue
            pts.append(TrajectoryPoint(int(float(row[0])), float(row[1]),
                                       float(row[xi]), float(row[yi]), 1.0, False))
        return pts

    def _ref_points(path, obj_name: str) -> list[TrajectoryPoint]:
        rrows = load_csv_rows(Path(path))
        prefix = f"{obj_name}_"
        xc = next((c for c in rrows[0] if c == f"{prefix}x_px"), None)
        yc = next((c for c in rrows[0] if c == f"{prefix}y_px"), None)
        if xc is None or yc is None:
            return []
        xi, yi = rrows[0].index(xc), rrows[0].index(yc)
        pts = []
        for row in rrows[1:]:
            if not row or row[xi] == "" or row[yi] == "":
                continue
            pts.append((float(row[xi]), float(row[yi])))
        return pts

    reports: dict[str, dict] = {}
    # Per-object params override (for multi-object videos where each body
    # follows a different law). args.per_object is a JSON string; if a
    # body has its own entry, that entry's family/fx/fy/cx/cy wins over
    # the global args.
    per_obj = json.loads(args.per_object) if args.per_object else {}
    for obj in cfg.objects:
        o = per_obj.get(obj.name, {})
        fam = o.get("family", args.family)
        fx = o.get("fx", args.fx)
        fy = o.get("fy", args.fy)
        c = o.get("center") or center
        pts = _object_points(obj.name)
        xs = [p.x_px for p in pts]
        ys = [p.y_px for p in pts]
        if args.reference_csv:
            ref = _ref_points(args.reference_csv, obj.name)
            if len(ref) >= 4:
                ref_x = [a for a, _ in ref]
                ref_y = [b for _, b in ref]
                # align to the candidate's sample count (min length)
                m = min(len(xs), len(ref_x))
                rep = compare_trajectories(
                    xs[:m], ys[:m], ref_x[:m], ref_y[:m],
                    dt, fam, fx, fy, c,
                )
                rep["reference_points"] = m
            else:
                rep = score_trajectory(xs, ys, dt, fam, fx, fy, c)
        else:
            rep = score_trajectory(xs, ys, dt, fam, fx, fy, c)
        rep["n_points"] = len(xs)
        rep["object"] = obj.name
        reports[obj.name] = rep

    out_path = out / f"{base}_physics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"fps": fps, "family": args.family,
                   "objects": [reports[o.name] for o in cfg.objects]},
                  fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(json.dumps({"physics_json": str(out_path),
                      "objects": [o.name for o in cfg.objects],
                      "family": args.family}, indent=2))
    return 0


def cmd_report(cfg, args) -> int:
    from .report import write_report_from_files

    out = _output_root(cfg, args)
    base = Path(cfg.videos[args.video_index]).name
    summary_path = out / f"{base}_summary.json"
    fft_path = out / f"{base}_fft.json"
    p = write_report_from_files(summary_path, fft_path, out / f"{base}_report.md")
    print(json.dumps({"report": str(p)}, indent=2))
    return 0


def cmd_demo(cfg, args) -> int:
    import numpy as np

    from .data_export import write_csv, write_summary
    from .fft_analyzer import analyze_object, write_spectra
    from .tracker import ObjectResult, TrajectoryPoint

    out = Path(args.output) if args.output else Path("output/demo")
    if cfg is not None and args.output is None:
        out = cfg.output / "demo"
    out.mkdir(parents=True, exist_ok=True)

    fps = 30.0
    if cfg is not None and cfg.fps:
        fps = float(cfg.fps)
    # Use an odd number of samples to exercise the odd-length FFT branch.
    n_samples = int(round(fps * 4.0)) | 1  # force odd
    t = np.arange(n_samples) / fps
    x = 100.0 * np.sin(2 * np.pi * 0.5 * t) + 200.0
    y = 50.0 * np.cos(2 * np.pi * 0.25 * t) + 150.0
    points = [
        TrajectoryPoint(i, float(ti), float(xi), float(yi), 1.0, False)
        for i, (ti, xi, yi) in enumerate(zip(t, x, y))
    ]
    from .config import ObjectROI

    res = ObjectResult(
        name="demo_pendulum",
        roi=ObjectROI("demo_pendulum", 0, 0, 1, 1),
        points=points,
    )
    summary = {
        "video": "demo:synthetic_pendulum",
        "fps": fps,
        "fps_source": "demo",
        "n_frames": len(points),
        "frame_width": 0,
        "frame_height": 0,
        "objects": [res.summary()],
        "scale_cm_per_px": None,
    }
    csv_path = write_csv([res], out / "demo_tracking.csv")
    write_summary(summary, out / "demo_summary.json")
    from .fft_analyzer import write_spectra

    oa = analyze_object(res.points, "demo_pendulum", fps, None, None, 5)
    specs = [oa.x, oa.y]
    json_path, png = write_spectra(
        specs,
        out / "demo_fft.json",
        out / "demo_spectra.png",
        trajectories={
            "demo_pendulum": ([p.x_px for p in points], [p.y_px for p in points])
        },
    )
    print(json.dumps(
        {
            "csv": str(csv_path),
            "summary": str(out / "demo_summary.json"),
            "fft_json": str(json_path),
            "png": str(png) if png else None,
            "n_frames": len(points),
        },
        indent=2,
    ))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 2
    try:
        cfg = None
        if args.cmd != "demo" or args.config:
            cfg = load_config(args.config) if getattr(args, "config", None) else None
        if args.cmd == "demo":
            return cmd_demo(cfg, args)
        return {
            "probe": cmd_probe,
            "track": cmd_track,
            "fft": cmd_fft,
            "physics": cmd_physics,
            "report": cmd_report,
        }[args.cmd](cfg, args)
    except TrackerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
