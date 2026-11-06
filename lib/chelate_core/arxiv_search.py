"""arXiv literature search core (arxiv SDK).

Returns normalized paper records (title, abstract, authors, dates, links,
categories, DOI, journal reference). The SDK is rate-limited politely
(3 s delay, 2 retries) and every failure is raised to the caller, which
maps it onto an UNVERIFIED gate — a network outage must never look like
"no results".
"""
from __future__ import annotations

from typing import List, Optional
from pathlib import Path

SORT_CHOICES = ("relevance", "lastUpdatedDate", "submittedDate")


def _sort_criterion(sort_by: str):
    import arxiv
    return {
        "relevance": arxiv.SortCriterion.Relevance,
        "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
        "submittedDate": arxiv.SortCriterion.SubmittedDate,
    }.get(sort_by, arxiv.SortCriterion.Relevance)


def search(query: str, max_results: int = 10,
           sort_by: str = "relevance") -> List[dict]:
    """Run one arXiv query; return the paper records (may be empty)."""
    import arxiv

    client = arxiv.Client(page_size=min(max_results, 100) or 10,
                          delay_seconds=3.0, num_retries=2)
    search_obj = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=_sort_criterion(sort_by),
    )
    papers = []
    for result in client.results(search_obj):
        papers.append({
            "title": result.title,
            "summary": result.summary,
            "authors": [a.name for a in result.authors],
            "published": result.published.isoformat() if result.published else None,
            "updated": result.updated.isoformat() if result.updated else None,
            "entry_id": result.entry_id,
            "pdf_url": result.pdf_url,
            "categories": list(result.categories),
            "doi": result.doi,
            "journal_ref": result.journal_ref,
        })
    return papers


def default_outdir(root: str):
    return Path(root) / "process" / "literature"


def resolve_outdir(root: str, outdir: Optional[str]):
    return Path(outdir) if outdir else default_outdir(root)
