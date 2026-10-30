"""literature-retriever — ingest-stage arXiv search (thin adapter).

All search logic lives in lib/chelate_core/arxiv_search.py; this file only
parses CLI arguments and maps outcomes onto the gate contract:

    python run.py --root <workspace> --action search --query "topological \
insulator" --max-results 10 [--sort-by relevance]

Output (under <root>/process/literature/):
    literature_<stamp>.json   {query, max_results, count, papers:[{title,
        summary, authors, published, updated, entry_id, pdf_url, categories,
        doi, journal_ref}]}
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter, arxiv_search  # noqa: E402

SKILL = "literature-retriever"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ("arxiv",)


def _configure(ap) -> None:
    ap.add_argument("--query", required=True, help="keyword phrase for arXiv")
    ap.add_argument("--max-results", type=int, default=None,
                    help="papers to retrieve (default: assets/config.yaml)")
    ap.add_argument("--sort-by", choices=arxiv_search.SORT_CHOICES,
                    default=None, help="sort order (default: config.yaml)")
    ap.add_argument("--outdir", default="",
                    help="output directory (default <root>/process/literature)")


def _search(args) -> dict:
    cfg = adapter.load_config(SKILL_ROOT)
    adapter.require_deps(DEPENDENCIES, "arXiv search")
    max_results = args.max_results or int(cfg.get("max_results", 10))
    sort_by = args.sort_by or cfg.get("sort_by", "relevance")
    try:
        papers = arxiv_search.search(args.query, max_results, sort_by)
    except Exception as exc:
        raise adapter.Degraded(
            f"arXiv query failed (network/API): {type(exc).__name__}: {exc}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "query": args.query,
        "max_results": max_results,
        "sort_by": sort_by,
        "count": len(papers),
        "retrieved_at": stamp,
        "papers": papers,
    }
    out_path = adapter.bootstrap().write_json(
        str(arxiv_search.resolve_outdir(args.root, args.outdir)),
        f"literature_{stamp}.json", payload)
    if not papers:
        raise adapter.Degraded(f"arXiv returned 0 hits for {args.query!r}",
                               artifacts=[out_path])
    return {"status": "PASS", "evidence_level": "EMPIRICAL",
            "reason": f"retrieved {len(papers)} papers for {args.query!r}",
            "artifacts": [out_path],
            "data": {"count": len(papers), "max_results": max_results}}


HANDLERS = {"search": _search}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Search arXiv by keyword and store JSON in process/."))
