"""Aggregate per-round audit records into a flat, filterable table."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import RoundRecord


@dataclass
class Summary:
    """A flattened view of all recorded rounds."""

    rows: List[Dict[str, Any]]

    def filter(self, **criteria) -> "Summary":
        """Return a new summary keeping rows matching all given field values."""
        kept = []
        for row in self.rows:
            ok = True
            for key, val in criteria.items():
                if row.get(key) != val:
                    ok = False
                    break
            if ok:
                kept.append(row)
        return Summary(rows=kept)


def aggregate(
    records: List[RoundRecord], param_keys: List[str]
) -> Summary:
    """Flatten round records into summary rows.

    Each row carries the round number, status, short hashes, timestamp, and one
    column per parameter dimension.
    """
    rows: List[Dict[str, Any]] = []
    for r in records:
        if r.status == "rolledback":
            continue
        row: Dict[str, Any] = {
            "round": r.round_no,
            "status": r.status,
            "input_hash": r.input_hash[:10],
            "output_hash": r.output_hash[:10],
            "timestamp": r.timestamp,
        }
        for k in param_keys:
            row[k] = r.params.get(k)
        rows.append(row)
    return Summary(rows=rows)


def write_csv(summary: Summary, path: Path) -> None:
    """Write the summary table as CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not summary.rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(summary.rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary.rows)
