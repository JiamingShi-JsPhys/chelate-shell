"""Report rendering for the document-evolution-tracker.

Renders the evolution timeline (pairwise diffs + concept lineage) to
Markdown and JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .diff_blocks import BlockDiff
from .lineage import LineageNode

__all__ = [
    "render_timeline_markdown",
    "render_timeline_json",
    "write_timeline",
]


def render_timeline_markdown(
    versions: List[str],
    diffs: List[BlockDiff],
    lineage: Dict[str, List[LineageNode]],
    tracking_id: str = "",
) -> str:
    lines: List[str] = []
    lines.append(f"# Document Evolution Timeline{(' -- ' + tracking_id) if tracking_id else ''}")
    lines.append("")
    lines.append(f"**Versions:** {', '.join(versions)}")
    lines.append(f"**Diffs:** {len(diffs)} transition(s)")
    lines.append("")

    for d in diffs:
        lines.append(f"## {d.old_label} -> {d.new_label}")
        lines.append("")
        lines.append(
            f"- added: **{d.added}**, removed: **{d.removed}**, modified: **{d.modified}**"
        )
        if d.changes:
            lines.append("")
            lines.append("| Change | Block |")
            lines.append("| --- | --- |")
            for c in d.changes[:50]:  # cap the table
                block = c.new_block if c.tag == "added" else c.old_block
                preview = block[:60] + ("..." if len(block) > 60 else "")
                lines.append(f"| {c.tag} | {preview} |")
        lines.append("")

    if lineage:
        lines.append("## Concept Lineage")
        lines.append("")
        lines.append("| Concept | " + " | ".join(versions) + " |")
        lines.append("| --- |" + " --- |" * len(versions))
        for concept, nodes in lineage.items():
            cells = []
            by_ver = {n.version_id: n for n in nodes}
            for vid in versions:
                n = by_ver.get(vid)
                cells.append(n.state if n else "-")
            lines.append(f"| {concept} | " + " | ".join(cells) + " |")
        lines.append("")

    return "\n".join(lines)


def render_timeline_json(
    versions: List[str],
    diffs: List[BlockDiff],
    lineage: Dict[str, List[LineageNode]],
) -> str:
    payload = {
        "versions": versions,
        "diffs": [d.to_dict() for d in diffs],
        "lineage": {c: [n.to_dict() for n in nodes] for c, nodes in lineage.items()},
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def write_timeline(
    versions: List[str],
    diffs: List[BlockDiff],
    lineage: Dict[str, List[LineageNode]],
    out_dir: Path,
    tracking_id: str = "",
) -> List[Path]:
    """Write both Markdown and JSON timeline files; return their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"evolution_{tracking_id or 'run'}"
    md_path = out_dir / f"{base}.md"
    json_path = out_dir / f"{base}.json"
    md_path.write_text(render_timeline_markdown(versions, diffs, lineage, tracking_id), encoding="utf-8")
    json_path.write_text(render_timeline_json(versions, diffs, lineage), encoding="utf-8")
    return [md_path, json_path]
