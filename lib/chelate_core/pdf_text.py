"""PDF text extraction core (PyMuPDF / fitz).

Extraction policy:
  - one section per page, with an explicit `===== PAGE i/n =====` marker so
    downstream skills can cite page numbers;
  - a JSON sidecar records source, metadata, per-page char counts;
  - zero extracted characters means the PDF is a scan without a text layer
    (reported by the caller as UNVERIFIED, never silently PASSed).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def parse_pages(spec: str, n_pages: int) -> List[int]:
    """Parse '1-5,8' (1-based, inclusive) into sorted 0-based page indices.

    An empty spec means "all pages"; a non-empty spec that parses to nothing
    (e.g. "abc") also falls back to all pages rather than extracting none.
    """
    if not spec:
        return list(range(n_pages))
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError:
                continue
            for i in range(max(1, lo), min(n_pages, hi) + 1):
                pages.add(i - 1)
        else:
            try:
                i = int(part)
            except ValueError:
                continue
            if 1 <= i <= n_pages:
                pages.add(i - 1)
    return sorted(pages) if pages else list(range(n_pages))


def extract(pdf_path: Path, pages_spec: str, outdir: Path) -> dict:
    """Extract text from `pdf_path`; write <stem>.txt + <stem>.json sidecar.

    Raises whatever PyMuPDF raises for an unreadable file — the adapter
    converts that into a controlled UNVERIFIED gate.
    """
    import fitz  # PyMuPDF

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as doc:
        n_pages = doc.page_count
        indices = parse_pages(pages_spec, n_pages)
        sections = []
        for i in indices:
            page = doc.load_page(i)
            text = page.get_text("text")
            sections.append(f"===== PAGE {i + 1}/{n_pages} =====\n{text.strip()}\n")
        meta = doc.metadata or {}
    full_text = "\n".join(sections)
    stem = Path(pdf_path).stem
    txt_path = outdir / f"{stem}.txt"
    txt_path.write_text(full_text, encoding="utf-8")
    sidecar = {
        "source": str(pdf_path),
        "title": meta.get("title", ""),
        "pages_total": n_pages,
        "pages_extracted": [i + 1 for i in indices],
        "chars": len(full_text),
        "per_page": [{"page": i + 1, "chars": len(s)} for i, s in
                     zip(indices, sections)],
        "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    json_path = outdir / f"{stem}.json"
    json_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    sidecar["text_path"] = str(txt_path)
    sidecar["json_path"] = str(json_path)
    return sidecar


def default_outdir(root: str) -> Path:
    return Path(root) / "process" / "fulltext"


def resolve_outdir(root: str, outdir: Optional[str]) -> Path:
    return Path(outdir) if outdir else default_outdir(root)
