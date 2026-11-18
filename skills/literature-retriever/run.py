"""literature-retriever — ingest-stage literature search (thin adapter).

arXiv search logic lives in lib/chelate_core/arxiv_search.py; Crossref,
PubMed and DOI resolution live in lib/chelate_core/scholar_search.py, which
is standard library only — a machine without the `arxiv` SDK can still use
those three sources. This file parses CLI arguments, dispatches, and maps
outcomes onto the gate contract:

    python run.py --root <workspace> --action search --query "topological \
insulator" --max-results 10 [--sort-by relevance]
    python run.py --root <workspace> --action search --query "twisted bilayer \
graphene" --source crossref --format bibtex
    python run.py --root <workspace> --action search --query 10.1038/nature14539 \
--source doi

Output (under <root>/process/literature/):
    literature_<stamp>.json   {query, source, max_results, count, papers:[{title,
        summary, authors, published, updated, entry_id, pdf_url, categories,
        doi, journal_ref}]}
    literature_<stamp>.bib    only with --format bibtex|both
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, next(
    (p for p in (_HERE, os.path.dirname(_HERE),
                 os.path.dirname(os.path.dirname(_HERE)),
                 os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
     if os.path.isdir(os.path.join(p, "lib", "chelate_core"))),
    os.path.abspath(os.path.join(_HERE, "..", ".."))))

from lib.chelate_core import adapter, arxiv_search, scholar_search  # noqa: E402

SKILL = "literature-retriever"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ("arxiv",)
SOURCES = ("arxiv", "crossref", "pubmed", "doi")


def _configure(ap) -> None:
    ap.add_argument("--query", required=True,
                    help="keyword phrase (or a DOI with --source doi)")
    ap.add_argument("--source", choices=SOURCES, default="arxiv",
                    help="where to search (default: arxiv)")
    ap.add_argument("--max-results", type=int, default=None,
                    help="papers to retrieve (default: assets/config.yaml)")
    ap.add_argument("--sort-by", choices=arxiv_search.SORT_CHOICES,
                    default=None,
                    help="arXiv sort order (ignored by the other sources)")
    ap.add_argument("--format", choices=("json", "bibtex", "both"),
                    default="json",
                    help="also write a .bib alongside the JSON")
    ap.add_argument("--outdir", default="",
                    help="output directory (default <root>/process/literature)")


def _retrieve(args, max_results: int, sort_by: str):
    """Route to the source; the arXiv SDK is only required when it is used."""
    if args.source == "arxiv":
        adapter.require_deps(DEPENDENCIES, "arXiv search")
        return arxiv_search.search(args.query, max_results, sort_by)
    return scholar_search.search(args.source, args.query, max_results)


def _search(args) -> dict:
    cfg = adapter.load_config(SKILL_ROOT)
    max_results = args.max_results or int(cfg.get("max_results", 10))
    sort_by = args.sort_by or cfg.get("sort_by", "relevance")
    try:
        papers = _retrieve(args, max_results, sort_by)
    except scholar_search.NotFound as exc:
        # A DOI Crossref does not know is a definite answer, not an outage —
        # but it is still no evidence, so the gate degrades rather than passes.
        raise adapter.Degraded(f"DOI not registered: {exc}")
    except scholar_search.ScholarError as exc:
        raise adapter.Degraded(f"{args.source} query failed: {exc}")
    except Exception as exc:
        raise adapter.Degraded(
            f"{args.source} query failed (network/API): {type(exc).__name__}: {exc}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "query": args.query,
        "source": args.source,
        "max_results": max_results,
        "sort_by": sort_by,
        "count": len(papers),
        "retrieved_at": stamp,
        "papers": papers,
    }
    out_dir = str(arxiv_search.resolve_outdir(args.root, args.outdir))
    out_path = adapter.bootstrap().write_json(
        out_dir, f"literature_{stamp}.json", payload)
    artifacts = [out_path]
    if args.format in ("bibtex", "both") and papers:
        bib_path = os.path.join(out_dir, f"literature_{stamp}.bib")
        with open(bib_path, "w", encoding="utf-8") as fh:
            fh.write(scholar_search.to_bibtex(papers))
        artifacts.append(bib_path)
    if not papers:
        raise adapter.Degraded(
            f"{args.source} returned 0 hits for {args.query!r}",
            artifacts=artifacts)
    return {"status": "PASS", "evidence_level": "EMPIRICAL",
            "reason": f"retrieved {len(papers)} papers from {args.source} "
                      f"for {args.query!r}",
            "artifacts": artifacts,
            "data": {"count": len(papers), "max_results": max_results,
                     "source": args.source}}


HANDLERS = {"search": _search}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Search arXiv, Crossref or PubMed (or resolve a DOI) and "
                    "store JSON in process/."))
