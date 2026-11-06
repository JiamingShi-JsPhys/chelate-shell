"""fulltext-extractor — ingest-stage PDF text extraction (thin adapter).

All extraction logic lives in lib/chelate_core/pdf_text.py; this file only
parses CLI arguments and maps outcomes onto the gate contract:

    python run.py --root <workspace> --action extract --input paper.pdf \
        [--pages 1-5] [--outdir process/fulltext]

Outputs (under <root>/process/fulltext/):
    <stem>.txt     full text, one page per section, page markers preserved
    <stem>.json    {source, pages, chars, per_page:[{page, chars}], ...}
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter, paths, pdf_text  # noqa: E402

SKILL = "fulltext-extractor"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ("pypdf",)  # pypdf is available in every target interpreter; pdfminer is used when present


def _configure(ap) -> None:
    ap.add_argument("--input", required=True, help="path to the source PDF")
    ap.add_argument("--pages", default="",
                    help="1-based page selection, e.g. '1-5,8' (default: all)")
    ap.add_argument("--outdir", default="",
                    help="output directory (default <root>/process/fulltext)")


def _extract(args) -> dict:
    cfg = adapter.load_config(SKILL_ROOT)
    adapter.require_deps(DEPENDENCIES, "PDF extraction")
    pdf = paths.resolve_input(args.root, args.input)
    if not pdf.is_file():
        raise adapter.Failed(f"input PDF not found: {pdf}")
    try:
        info = pdf_text.extract(pdf, args.pages or cfg.get("pages", ""),
                                pdf_text.resolve_outdir(
                                    args.root, args.outdir or cfg.get("outdir", "")))
    except Exception as exc:
        raise adapter.Degraded(
            f"PDF unreadable or not a valid document: "
            f"{type(exc).__name__}: {exc}")
    artifacts = [info["text_path"], info["json_path"]]
    if info["chars"] == 0:
        raise adapter.Degraded(
            f"no extractable text in {pdf.name} (scanned image PDF?)",
            artifacts=artifacts)
    return {
        "status": "PASS", "evidence_level": "EMPIRICAL",
        "reason": (f"extracted {info['chars']} chars from "
                   f"{len(info['pages_extracted'])}/{info['pages_total']} "
                   f"pages of {pdf.name}"),
        "artifacts": artifacts,
        "data": {"chars": info["chars"],
                 "pages_extracted": info["pages_extracted"]},
    }


HANDLERS = {"extract": _extract}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Extract text from a local PDF (pdfminer.six, pypdf fallback)."))
