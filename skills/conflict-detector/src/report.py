"""Reporter: render conflict lists to JSON / Markdown / CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Union

from .detect import Conflict

__all__ = ["render_json", "render_markdown", "render_csv", "write_report"]


def render_json(conflicts: List[Conflict]) -> str:
    return json.dumps([c.to_dict() for c in conflicts], indent=2, ensure_ascii=False)


def render_csv(conflicts: List[Conflict]) -> str:
    if not conflicts:
        return "level,kind,severity,source_a,source_b,claim_a,claim_b\n"
    lines = ["level,kind,severity,source_a,source_b,claim_a,claim_b"]
    for c in conflicts:
        row = [
            c.level, c.kind, c.severity, c.source_a, c.source_b, c.claim_a, c.claim_b,
        ]
        lines.append(",".join(_csv_quote(v) for v in row))
    return "\n".join(lines) + "\n"


def _csv_quote(v: Union[str, int, float, bool]) -> str:
    s = str(v)
    if any(ch in s for ch in ',"\n'):
        return '"' + s.replace('"', '""') + '"'
    return s


def render_markdown(conflicts: List[Conflict], run_id: str = "") -> str:
    lines = [f"# Conflict Report{(' -- ' + run_id) if run_id else ''}", ""]
    if not conflicts:
        lines.append("_No conflicts detected._")
        return "\n".join(lines) + "\n"
    lines.append(f"**Total:** {len(conflicts)} conflict(s)")
    lines.append("")
    lines.append("| Level | Kind | Severity | A (src) | B (src) |")
    lines.append("| --- | --- | --- | --- | --- |")
    for c in conflicts:
        lines.append(
            f"| {c.level} | {c.kind} | {c.severity} | `{c.claim_a}` ({c.source_a}) | `{c.claim_b}` ({c.source_b}) |"
        )
    return "\n".join(lines) + "\n"


def write_report(
    conflicts: List[Conflict],
    out_dir: Union[str, Path],
    fmt: str = "json",
    run_id: str = "",
) -> List[Path]:
    """Write the conflict list in the requested format(s); return paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for f in (fmt.split(",") if fmt else ["json"]):
        f = f.strip()
        if f == "json":
            p = out_dir / f"conflicts_{run_id or 'run'}.json"
            p.write_text(render_json(conflicts), encoding="utf-8")
        elif f == "csv":
            p = out_dir / f"conflicts_{run_id or 'run'}.csv"
            p.write_text(render_csv(conflicts), encoding="utf-8")
        elif f == "md":
            p = out_dir / f"conflicts_{run_id or 'run'}.md"
            p.write_text(render_markdown(conflicts, run_id), encoding="utf-8")
        else:
            raise ValueError(f"unknown report format: {f}")
        written.append(p)
    return written
