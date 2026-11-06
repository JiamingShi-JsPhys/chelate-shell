"""latex-exporter adapter -- thin CLI over scripts/engine.py.

Usage:
    python scripts/run.py --root <WS> --action process [--name report.tex]

The adapter only parses arguments and delegates to engine.export(); all
business logic (the Markdown->LaTeX subset converter and the document
assembler) lives in scripts/engine.py.

Input contract:
    --root <WS>   the workspace. The engine reads every Markdown report under
                  <WS>/process/ and every graphic (.pdf/.png/.jpg/.jpeg/.eps)
                  under <WS>/process/figures/, then writes a single compilable
                  .tex to <WS>/process/latex/<name>.
    --name        output filename (default merged_report.tex).

No heavy dependency (no pandoc): the converter is pure standard library.
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..")))
sys.path.insert(0, _HERE)

from lib.chelate_core import adapter  # noqa: E402

SKILL = "latex-exporter"


def _handler(args):
    from engine import export
    return export(root=args.root, out_name=args.name or "merged_report.tex")


def _configure(ap):
    ap.add_argument("--name", default="merged_report.tex",
                    help="output .tex filename (default: merged_report.tex)")


if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, {"export": _handler},
        description="Merge process/ Markdown reports + process/figures/ "
                    "graphics into a standard .tex file (pure stdlib, no "
                    "pandoc)."))
