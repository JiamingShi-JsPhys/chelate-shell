"""index_xlsx.py -- generate ``Index.xlsx`` (openpyxl) with a Statistics sheet.

Two sheets are produced:
- **Index** -- one row per file, same fields as the Markdown index.
- **Statistics** -- counts grouped by source and type.

Graceful degradation
--------------------
``openpyxl`` is an optional runtime dependency. When it is not installed,
``write_index_xlsx`` returns ``None`` and records the reason in
*result.message* rather than raising -- so the overall organize pipeline
still completes (the Markdown index is always available as a fallback).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from scripts import index_md, utils


@dataclass
class XlsxResult:
    """Outcome of :func:`write_index_xlsx`."""

    path: Optional[Path] = None
    success: bool = False
    message: str = ""
    rows: List[index_md.IndexRow] = field(default_factory=list)


def _stats_by(rows: List[index_md.IndexRow]) -> Dict[str, Dict[str, int]]:
    """Aggregate row counts by source (then by type within each source)."""
    stats: Dict[str, Dict[str, int]] = {}
    for r in rows:
        by_src = stats.setdefault(r.source, {})
        by_src[r.file_type] = by_src.get(r.file_type, 0) + 1
    return stats


def write_index_xlsx(
    root: Path,
    rows: Optional[List[index_md.IndexRow]] = None,
    out_path: Optional[Path] = None,
) -> XlsxResult:
    """Write ``Index.xlsx`` under material/ (if openpyxl is available).

    Parameters
    ----------
    root:
        Task root; rows are collected from disk when omitted.
    rows:
        Explicit rows to write (reuses the Markdown index's collector).
    out_path:
        Optional custom output path.

    Returns
    -------
    XlsxResult:
        ``success`` True only when openpyxl was present and the file written.
        On missing dependency, ``success`` is False and ``message`` explains
        the degradation (the caller should not treat this as fatal).
    """
    root = Path(root).resolve()
    if rows is None:
        rows = index_md.build_rows(root)

    if out_path is None:
        out_path = root / utils.TIER_ORGANIZE / utils.INDEX_XLSX_NAME

    try:
        import openpyxl
        from openpyxl.styles import Font
    except ImportError:
        return XlsxResult(
            path=None,
            success=False,
            message="openpyxl not installed; skipped xlsx generation (install with: pip install openpyxl)",
            rows=rows,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Index"

    # Header.
    ws.append(index_md.COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for r in rows:
        ws.append(r.to_row())

    # Auto-width-ish (naive but helpful).
    for col_cells in ws.columns:
        try:
            width = max((len(str(c.value)) for c in col_cells if c.value), default=10)
            ws.column_dimensions[col_cells[0].column_letter].width = min(width + 2, 60)
        except Exception: # pragma: no cover - cosmetic only
            pass

    # Statistics sheet.
    ws2 = wb.create_sheet("Statistics")
    ws2.append(["source", "type", "count"])
    for cell in ws2[1]:
        cell.font = Font(bold=True)
    for source, by_type in _stats_by(rows).items():
        for ftype, n in by_type.items():
            ws2.append([source, ftype, n])

    try:
        wb.save(out_path)
    except OSError as exc:
        return XlsxResult(
            path=out_path,
            success=False,
            message=f"xlsx save failed: {exc}",
            rows=rows,
        )

    return XlsxResult(
        path=out_path,
        success=True,
        message="ok",
        rows=rows,
    )


def load_xlsx_rows(xlsx_path: Path) -> List[Dict[str, str]]:
    """Read the Index sheet of an existing xlsx back into row dicts.

    Returns [] when the file is absent or openpyxl is missing. Useful for
    external tooling and tests.
    """
    xlsx_path = Path(xlsx_path)
    if not xlsx_path.exists():
        return []
    try:
        import openpyxl
    except ImportError:
        return []

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    try:
        ws = wb["Index"]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return []
    header = [str(c) for c in rows[0]]
    out: List[Dict[str, str]] = []
    for row in rows[1:]:
        if all(v is None for v in row):
            continue
        out.append(dict(zip(header, row)))
    return out
