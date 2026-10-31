"""figure-generator adapter -- thin CLI over scripts/engine.py.

Usage:
    python scripts/run.py --root <WS> --action process --input data.csv \
        --chart bar --x col1 --y col2 [--hue group] [--title "Fig 1"]
    python scripts/run.py --root <WS> --action process \
        --input sem_figure_input.json            # type: sem_path -> path fig

The adapter only parses arguments and delegates to engine.generate(); all
business logic lives in scripts/engine.py (v1.2.0, MIT).
"""
from __future__ import annotations

import os
import sys

# Make the repository root importable so `from lib.chelate_core import adapter`
# and `import engine` both resolve regardless of the caller's cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..")))
sys.path.insert(0, _HERE)

from lib.chelate_core import adapter  # noqa: E402

SKILL = "figure-generator"


def _handler(args):
    from engine import generate
    return generate(
        data_path=args.input,
        chart=args.chart,
        x=args.x, y=args.y, hue=args.hue,
        title=args.title,
        output_dir=args.output_dir,
        root=args.root,
    )


def _configure(ap):
    ap.add_argument("--input", required=False,
                    help="data file: a .csv table, or a .json spec "
                         "(a SEM spec with 'type': 'sem_path' draws a "
                         "path diagram; otherwise a generic JSON table)")
    ap.add_argument("--chart", default="bar",
                    choices=("bar", "line", "scatter"),
                    help="chart type for tabular input (default: bar); "
                         "ignored for a sem_path JSON")
    ap.add_argument("--x", help="column for the x axis (tabular input)")
    ap.add_argument("--y", help="column for the y axis (tabular input)")
    ap.add_argument("--hue", help="optional grouping column (tabular input)")
    ap.add_argument("--title",
                    help="figure title (default: derived from the data or "
                         "the chart type)")
    ap.add_argument("--output-dir",
                    help="output directory (defaults to "
                         "<root>/process/figures)")


if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, {"process": _handler},
        description="Figure generation processor (matplotlib/seaborn); "
                    "also renders SEM path diagrams from a sem_path JSON."))
