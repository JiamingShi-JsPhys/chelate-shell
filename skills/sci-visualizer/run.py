"""sci-visualizer — v1.3.0 generation meta-skill (thin adapter).

Owns the figure-generation engine in-process. Static scientific charts are
rendered by the co-located ``scripts/engine.py`` (matplotlib/seaborn, the
engine the standalone figure-generator skill used to ship); gif/animation
inputs are frame-scanned with optional Pillow. This adapter only wires the
uniform CLI contract (--root/--action); the rendering logic lives in
``scripts/engine.py``.
"""
from __future__ import annotations

import pathlib
import sys

# Repo root and the skill's scripts/ dir importable regardless of the
# caller's cwd. The root is found by walking up to the directory that holds
# lib/chelate_core/, so the adapter does not depend on how deep the skill sits
# under skills/.
_HERE = pathlib.Path(__file__).resolve().parent
_REPO = next((p for p in _HERE.parents
              if (p / "lib" / "chelate_core" / "adapter.py").is_file()),
             _HERE.parents[1])
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_HERE / "scripts"))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "sci-visualizer"


def _configure(ap):
    ap.add_argument("--input", help="data file (.csv/.json) or frame seq (.gif)")
    ap.add_argument("--type", choices=("static", "gif", "animation"),
                   default="static")
    ap.add_argument("--chart", help="chart type for tabular input "
                                    "(bar/line/scatter/box; default: bar)")
    ap.add_argument("--x", help="column for the x axis (tabular input)")
    ap.add_argument("--y", help="column for the y axis (tabular input)")
    ap.add_argument("--hue", help="optional grouping column (tabular input)")
    ap.add_argument("--title", help="figure title "
                                    "(default: derived from the data)")


def _render_static(args):
    """static -> in-process engine.generate (matplotlib/seaborn)."""
    from engine import generate  # scripts/engine.py on sys.path (see above)
    return generate(
        data_path=args.input,
        chart=args.chart,
        x=args.x, y=args.y, hue=args.hue,
        title=args.title,
        root=args.root,
    )


def _scan_frames(args):
    """gif/animation -> Pillow frame scan (optional dep, UNVERIFIED if absent)."""
    try:
        from PIL import Image
    except Exception:
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": "Pillow not installed; cannot scan animation frames"}
    src = pathlib.Path(args.input)
    if not src.is_file():
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": f"input not found: {args.input}"}
    out_dir = pathlib.Path(args.root) / "process" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(src) as im:
            frames = getattr(im, "n_frames", 1)
            report = out_dir / f"{src.stem}_frames.txt"
            report.write_text(
                f"frames={frames}\nsize={im.size[0]}x{im.size[1]}\n",
                encoding="utf-8")
            return {"status": "PASS", "evidence_level": "EMPIRICAL",
                    "reason": f"scanned {frames} frame(s) of {src.name}",
                    "artifacts": [str(report)]}
    except Exception as exc:
        return {"status": "FAIL", "evidence_level": "UNVERIFIED",
                "reason": f"Pillow scan failed: {exc}"}


def _handler(args):
    if not args.input:
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": "no --input provided"}
    if args.type == "static":
        return _render_static(args)
    return _scan_frames(args)


if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, {"process": _handler},
        description="Generation meta-skill: static scientific charts "
                    "rendered in-process via scripts/engine.py; "
                    "gif/animation frame scan via optional Pillow."))
