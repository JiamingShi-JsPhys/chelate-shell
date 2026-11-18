"""deck-exporter — processors-stage Markdown → self-contained HTML deck.

Engine: lib/chelate_core/deck.py

    python run.py --root <WS> --action build --name deck

Images become data URIs, CSS is inline, and a deck that would embed an
absolute path is refused rather than sanitised.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, next(
    (p for p in (_HERE, os.path.dirname(_HERE),
                 os.path.dirname(os.path.dirname(_HERE)),
                 os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
     if os.path.isdir(os.path.join(p, "lib", "chelate_core"))),
    os.path.abspath(os.path.join(_HERE, "..", ".."))))

from lib.chelate_core import adapter, deck  # noqa: E402

SKILL = "deck-exporter"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ()


def _configure(ap) -> None:
    ap.add_argument("--name", default="deck",
                    help="deck name, used in the file name")


def _build(args) -> dict:
    try:
        report = deck.build(args.root, args.name)
    except deck.DeckLeak as exc:
        raise adapter.Failed(str(exc), evidence_level="EXACT")
    except deck.DeckError as exc:
        raise adapter.Degraded(f"nothing to export: {exc}")
    skipped = len(report["images_skipped"])
    return {
        "status": "PASS", "evidence_level": "EXACT",
        "reason": (f"{report['slides']} slides from "
                   f"{len(report['sources'])} report(s), "
                   f"{len(report['images_inlined'])} image(s) inlined"
                   + (f", {skipped} left out" if skipped else "")),
        "artifacts": [report["path"]],
        "data": {"slides": report["slides"], "bytes": report["bytes"],
                 "sources": report["sources"],
                 "images_inlined": len(report["images_inlined"]),
                 "images_skipped": skipped},
    }


HANDLERS = {"build": _build}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Turn the Markdown reports in process/ into one "
                    "self-contained HTML deck with no absolute paths."))
