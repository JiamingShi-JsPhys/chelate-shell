#!/usr/bin/env python
"""Stage C — local downsampling + Matplotlib plots of a recorded .cap.

Given a *recorded* .cap (real in-lab data, NOT AI-generated), this stage:

  1. probes the zip (R-04: clear error if not a valid .cap),
  2. decodes every DataSet's tmp record (12-byte layout, flag==1 only),
  3. rebuilds the time axis (start + k*interval),
  4. compresses each series to at most `--target-points` feature points
     (mean-segmentation: split the trace into equal segments, emit each
     segment's mean + a global peak/valley), and
  5. writes:
       stage_c/summary.json   — per-series: name, stats (mean/min/max/std),
                                 linear-fit (slope, intercept, r^2),
                                 feature points (<= target), all traceable
       stage_c/manifest.json  — traceability map (feature point -> tmp idx)
       stage_c/csv/*.csv      — full (t, v) series export for Excel screening
                                 of weak/buried peaks (R-05 support; the .cap
                                 itself is never modified)
       stage_c/plots/*.png    — original vs downsampled overlay (matplotlib;
                                 skipped with a warning if matplotlib missing)

The summary.json is what the host LLM receives in stage D. The raw
tens-of-thousands of rows NEVER leave this process (R-03 token firewall).

Usage::

    python scripts/process_cap.py --input recorded.cap --target-points 80 \
        --outdir work
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Try to use numpy for vectorized performance. Fallback to pure python if missing.
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _capx  # noqa: E402


def _safe_filename(label: str) -> str:
    """Sanitize the dataset label to a safe filename."""
    return re.sub(r"[^A-Za-z0-9]+", "_", label)[:40]


# ---------------------------------------------------------------------------
# Downsampling & Math
# ---------------------------------------------------------------------------
def _downsample(t: List[float], v: List[float],
                target: int) -> Tuple[List[int], List[Dict[str, Any]]]:
    """Compress (t, v) to <= target feature points via mean-segmentation.

    Returns (kept_indices, feature_points). A global peak and a global valley
    are always kept even if not a segment boundary.
    """
    n = len(v)
    if n == 0:
        return [], []
    target = max(2, min(target, n))
    if n <= target:
        return list(range(n)), [
            {"i": i, "t": t[i], "v": v[i], "kind": "point"} for i in range(n)
        ]

    kept: List[int] = []
    feats: List[Dict[str, Any]] = []

    if HAS_NUMPY:
        v_arr = np.array(v)
        peak_i = int(np.argmax(v_arr))
        valley_i = int(np.argmin(v_arr))
        
        # Use numpy array_split for clean segmentation
        segments = np.array_split(v_arr, target)
        offset = 0
        for s, seg_arr in enumerate(segments):
            if len(seg_arr) == 0:
                continue
            m = float(np.mean(seg_arr))
            lo = offset
            hi = offset + len(seg_arr) - 1
            mid = (lo + hi) // 2
            kept.append(mid)
            feats.append({"i": mid, "t": t[mid], "v": m, "kind": "seg_mean",
                          "lo": lo, "hi": hi})
            offset += len(seg_arr)
    else:
        # Pure Python fallback
        seg = n // target
        peak_i = v.index(max(v))
        valley_i = v.index(min(v))
        for s in range(target):
            lo = s * seg
            hi = min(n, lo + seg) if s < target - 1 else n
            if lo >= hi:
                continue
            m = sum(v[lo:hi]) / (hi - lo)
            mid = (lo + hi - 1) // 2
            kept.append(mid)
            feats.append({"i": mid, "t": t[mid], "v": m, "kind": "seg_mean",
                          "lo": lo, "hi": hi - 1})

    # Guarantee the extremes survive
    for special_i, kind in ((peak_i, "peak"), (valley_i, "valley")):
        if special_i not in kept:
            kept.append(special_i)
            feats.append({"i": special_i, "t": t[special_i], "v": v[special_i],
                          "kind": kind})
            
    kept = sorted(set(kept))
    kept_set = set(kept)
    feats = [f for f in feats if f["i"] in kept_set]
    return kept, feats


def _linfit(t: List[float], v: List[float]) -> Dict[str, Optional[float]]:
    """Ordinary least-squares fit v = a*t + b, with r^2."""
    n = len(t)
    if n < 2:
        return {"slope": 0.0, "intercept": float(v[0]) if v else 0.0, "r_squared": None}
        
    if HAS_NUMPY:
        t_arr, v_arr = np.array(t), np.array(v)
        slope, intercept = np.polyfit(t_arr, v_arr, 1)
        # Calculate R-squared
        v_pred = slope * t_arr + intercept
        ss_res = np.sum((v_arr - v_pred) ** 2)
        ss_tot = np.sum((v_arr - np.mean(v_arr)) ** 2)
        r2 = float(1 - (ss_res / ss_tot)) if ss_tot > 0 else None
        return {"slope": float(slope), "intercept": float(intercept), "r_squared": r2}
    else:
        mean_t = sum(t) / n
        mean_v = sum(v) / n
        sxx = sum((x - mean_t) ** 2 for x in t)
        sxy = sum((t[i] - mean_t) * (v[i] - mean_v) for i in range(n))
        syy = sum((x - mean_v) ** 2 for x in v)
        slope = sxy / sxx if sxx else 0.0
        intercept = mean_v - slope * mean_t
        r2 = (sxy * sxy / (sxx * syy)) if sxx and syy else None
        return {"slope": slope, "intercept": intercept, "r_squared": r2}


def _stats(v: List[float]) -> Dict[str, Optional[float]]:
    if not v:
        return {"mean": None, "min": None, "max": None, "std": None}
        
    if HAS_NUMPY:
        v_arr = np.array(v)
        return {
            "mean": float(np.mean(v_arr)),
            "min": float(np.min(v_arr)),
            "max": float(np.max(v_arr)),
            "std": float(np.std(v_arr, ddof=0))
        }
    else:
        m = sum(v) / len(v)
        std = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5 if len(v) > 1 else 0.0
        return {"mean": m, "min": min(v), "max": max(v), "std": std}


# ---------------------------------------------------------------------------
# Plotting & CSV
# ---------------------------------------------------------------------------
def _try_plot(plot_dir: Path, label: str,
              t: List[float], v: List[float], feats: List[Dict[str, Any]]) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
        
    try:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(t, v, lw=0.6, alpha=0.5, label="Raw Data")
        ax.plot([f["t"] for f in feats], [f["v"] for f in feats],
                marker="o", ms=3, lw=0, label=f"Downsampled ({len(feats)} pts)")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Value")
        ax.set_title(f"Series: {label}")
        ax.legend()
        fig.tight_layout()
        
        safe = _safe_filename(label)
        fig.savefig(plot_dir / f"{safe}.png", dpi=110)
        plt.close(fig)
        return True
    except Exception as e:
        print(f"  warning: failed to generate plot for {label}: {e}", file=sys.stderr)
        return False


def _write_csv(csv_dir: Path, label: str,
               t: List[float], v: List[float]) -> Path:
    """Export the full (t, v) series to CSV for spreadsheet screening."""
    csv_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(label)
    out = csv_dir / f"{safe}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time_s", "value"])
        for ti, vi in zip(t, v):
            w.writerow([f"{ti:.6g}", f"{vi:.6g}"])
    return out


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------
def run(input_path: Path, target_points: int, outdir: Path) -> int:
    outdir = outdir.resolve()
    stage = outdir / "stage_c"
    (stage / "plots").mkdir(parents=True, exist_ok=True)

    # R-04: clear error on a non-.cap, never silent.
    try:
        zf = _capx.open_cap_zip(input_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    datasets = _capx.extract_datasets(zf)
    if not datasets:
        print("error: no DataSets found in .cap; nothing to process", file=sys.stderr)
        return 2

    summary: List[Dict[str, Any]] = []
    manifest: Dict[str, Any] = {}
    n_plots = 0
    
    for d in datasets:
        label = d.dataset_name or f"series{d.index}"
        try:
            values = _capx.read_tmp_values(zf, d.file_name, d.data_cache_size)
        except ValueError as exc:
            print(f"  diagnostic: {label}: {exc}", file=sys.stderr)
            continue
            
        times = _capx.build_time_axis(d.cache_start, d.cache_interval, len(values))
        _write_csv(stage / "csv", label, times, values)
        
        kept, feats = _downsample(times, values, target_points)
        fit = _linfit([f["t"] for f in feats], [f["v"] for f in feats])
        
        entry = {
            "series": label,
            "tmp": d.file_name,
            "raw_points": len(values),
            "stats": _stats(values),
            "fit": fit,
            "feature_points": feats,
        }
        summary.append(entry)
        
        manifest[label] = {
            "tmp": d.file_name,
            "feature_idx": [f["i"] for f in feats],
            "kind": [f["kind"] for f in feats],
        }
        
        if _try_plot(stage / "plots", label, times, values, feats):
            n_plots += 1

    (stage / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (stage / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    total_features = sum(len(e["feature_points"]) for e in summary)
    print(f"stage C: {len(summary)} series -> stage_c/summary.json "
          f"({total_features} feature points, target {target_points}/series); "
          f"CSV -> stage_c/csv/; {n_plots} plots -> stage_c/plots/")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="capstone-labmate process", description="Stage C: downsample .cap")
    p.add_argument("--input", required=True, type=Path,
                   help="recorded .cap file (real in-lab data)")
    p.add_argument("--target-points", type=int, default=80,
                   help="max feature points per series (default 80)")
    p.add_argument("--outdir", required=True, type=Path,
                   help="working directory for artifacts")
    a = p.parse_args(argv)
    return run(a.input.resolve(), a.target_points, a.outdir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
