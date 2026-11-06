"""bibtex-normalizer — ingest-stage .bib parsing, dedupe, re-emission (thin).

All parsing/normalization logic lives in lib/chelate_core/bibtex_norm.py;
this file only parses CLI arguments and maps outcomes onto the gate
contract:

    python run.py --root <workspace> --action normalize --input refs.bib

Dedupe rule (conservative): two entries collide when their normalized
citation key OR their (lowercased title, year) pair matches; the first
occurrence wins and later duplicates are recorded in the report.

Output (under <root>/process/bibtex/):
    <stem>.normalized.bib   the cleaned bibliography
    <stem>.report.json      {total, unique, duplicates:[...], fields_seen}
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter, bibtex_norm, paths  # noqa: E402

SKILL = "bibtex-normalizer"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ("bibtexparser",)


def _configure(ap) -> None:
    ap.add_argument("--input", required=True, help="path to the source .bib")
    ap.add_argument("--outdir", default="",
                    help="output directory (default <root>/process/bibtex)")


def _normalize(args) -> dict:
    cfg = adapter.load_config(SKILL_ROOT)
    adapter.require_deps(DEPENDENCIES, "BibTeX parsing")
    bib = paths.resolve_input(args.root, args.input)
    if not bib.is_file():
        raise adapter.Failed(f"input .bib not found: {bib}")
    try:
        report = bibtex_norm.normalize(
            bib, bibtex_norm.resolve_outdir(
                args.root, args.outdir or cfg.get("outdir", "")))
    except Exception as exc:
        raise adapter.Failed(
            f"BibTeX parse failed: {type(exc).__name__}: {exc}")
    artifacts = [report["bib_path"], report["json_path"]]
    if report["unique"] == 0:
        raise adapter.Degraded(f"no entries parsed from {bib.name}",
                               artifacts=artifacts)
    return {
        "status": "PASS", "evidence_level": "EMPIRICAL",
        "reason": (f"normalized {report['unique']}/{report['total']} entries "
                   f"({len(report['duplicates'])} duplicates removed)"),
        "artifacts": artifacts,
        "data": {"unique": report["unique"], "total": report["total"],
                 "duplicates": len(report["duplicates"])},
    }


HANDLERS = {"normalize": _normalize}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Parse, dedupe and normalize a .bib bibliography."))
