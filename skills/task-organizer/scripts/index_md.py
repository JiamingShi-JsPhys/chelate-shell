"""index_md.py -- generate ``Index.md`` from the organized state.

The Markdown index is the human-readable catalog of every file under the
standard tiers. It is the **human-facing** half of the two-part digest:
this index answers "what files are here and where did each one come from?",
while ``_broadcast/INDEX.md`` answers "what does each file say".

Each row carries: filename / type / size / source / summary / added at /
remark. The ``source`` column states the provenance: ``initial`` (the user's
own material, kept verbatim), ``downloaded`` (fetched by the assistant --
with the URL when one was recorded), ``process`` / ``results`` (tool
output tiers), or ``Root`` (an unclassified loose file).

The index is *regenerated* on every run: it reflects the current on-disk
state, not an incremental diff, so it is always consistent with the folder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from scripts import utils


#: Column order of the generated table.
COLUMNS = ["filename", "type", "size", "source", "summary", "added at", "remark"]


@dataclass
class IndexRow:
    """One table row in Index.md /.xlsx."""

    filename: str
    file_type: str
    size: str
    source: str
    summary: str
    added_at: str
    remark: str = ""

    def to_row(self) -> List[str]:
        return [
            self.filename,
            self.file_type,
            self.size,
            self.source,
            self.summary,
            self.added_at,
            self.remark,
        ]


def _classify_path(rel: str) -> str:
    """Map a relative path to its source label (which tier it lives in)."""
    norm = rel.replace("\\", "/")
    if norm.startswith("material/initial"):
        return "initial"
    if norm.startswith("material/downloaded"):
        return "downloaded"
    if norm.startswith("process"):
        return "process"
    if norm.startswith("results"):
        return "results"
    return "Root"


def _type_label(p: Path) -> str:
    """Human-friendly type label for index rows."""
    if p.is_symlink():
        return "symlink"
    if utils.is_readonly(p):
        return "read-only"
    suffix = p.suffix.lower()
    if suffix in {".pdf", ".epub"}:
        return "document"
    if suffix in {".csv", ".xlsx", ".xls"}:
        return "table"
    if suffix in {".py", ".js", ".c", ".cpp", ".h", ".rs", ".go", ".java"}:
        return "code"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
        return "image"
    if suffix in {".md", ".txt", ".rst", ".tex"}:
        return "text"
    if suffix in {".ipynb"}:
        return "notebook"
    return "other"


def _remark_for(p: Path, source_label: str, url: str = "") -> str:
    """Edge-case remarks: symlink / readonly / unclassified / provenance.

    For a ``downloaded`` file the remark carries the recorded origin URL,
    which is the "where did this come from" the human-facing index exists
    to answer; other tiers get a terse status note.
    """
    if p.is_symlink():
        return "symlink, not moved"
    if utils.is_readonly(p):
        return "read-only, not moved"
    if source_label == "downloaded":
        return f"downloaded from {url}" if url else "downloaded by assistant"
    if source_label == "initial":
        return "user material"
    # unclassified = a loose file left at the root that no rule claimed.
    if source_label == "Root":
        return "unclassified"
    return "normal"


def build_rows(root: Path) -> List[IndexRow]:
    """Collect one :class:`IndexRow` for every file under the standard tiers.

    Skips hidden files. Includes symlinks (flagged in remark) and readonly
    files (flagged in remark). For downloaded files the provenance URL from
    the source manifest is surfaced in the remark column.
    """
    from scripts import sources

    root = Path(root).resolve()
    manifest = sources.SourceManifest.load(root)
    rows: List[IndexRow] = []

    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        if utils.is_hidden(p):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        # The index catalogs *material*, not the tool's own outputs. Skip the
        # generated snapshot/log/report files under process/ and the index
        # files themselves. User-placed drafts in process/ are kept.
        if utils.is_allowed_new_file(rel):
            continue
        try:
            st = p.stat()
        except OSError:
            # Broken symlink or vanished entry: record with zero size/time
            # but still include it in the index (it is a real entry).
            st = p.lstat() if p.is_symlink() else None
            if st is None:
                continue
        source_label = _classify_path(rel)
        url = _manifest_url(manifest, p.name)
        remark = _remark_for(p, source_label, url=url)

        summary = utils.generate_summary(p, hint=source_label)
        added = str(int(st.st_mtime)) if getattr(st, "st_mtime", 0) else ""

        rows.append(
            IndexRow(
                filename=p.name,
                file_type=_type_label(p),
                size=utils.format_bytes(st.st_size),
                source=source_label,
                summary=summary,
                added_at=added,
                remark=remark,
            )
        )
    return rows


def _manifest_url(manifest, name: str) -> str:
    """Return the recorded origin URL for *name* ("" if none)."""
    if manifest is None:
        return ""
    for e in manifest.downloaded:
        if e.name == name and e.url:
            return e.url
    return ""


def _markdown_table(rows: List[IndexRow]) -> str:
    """Render rows as a GFM pipe table."""
    header = "| " + " | ".join(COLUMNS) + " |"
    sep = "| " + " | ".join(["---"] * len(COLUMNS)) + " |"
    lines = [header, sep]
    for r in rows:
        # Escape pipes inside cell text.
        cells = [c.replace("|", "\\|") for c in r.to_row()]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_index_md(
    root: Path,
    rows: Optional[List[IndexRow]] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Generate ``Index.md`` under material/ and return its path.

    When *rows* is omitted they are collected fresh from disk.
    """
    root = Path(root).resolve()
    if rows is None:
        rows = build_rows(root)

    if out_path is None:
        out_path = root / utils.TIER_ORGANIZE / utils.INDEX_MD_NAME

    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("# Index")
    lines.append("")
    lines.append(f"- generated under: `{root}`")
    lines.append(f"- entries: {len(rows)}")
    lines.append("- note: This index is regenerated on every run; the summary "
                 "is a one-sentence AI-generated line when an AI API key is "
                 "configured, otherwise a 'filename + first 200 chars' placeholder.")
    lines.append("")
    lines.append(_markdown_table(rows))
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def load_rows_from_md(md_path: Path) -> List[Dict[str, str]]:
    """Parse an existing Index.md back into row dicts (round-trip aid).

    Returns an empty list when the file is absent or unparseable. This keeps
    the module usable by external tooling that wants to diff indexes.
    """
    md_path = Path(md_path)
    if not md_path.exists():
        return []
    text = md_path.read_text(encoding="utf-8")
    out: List[Dict[str, str]] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| filename"):
            in_table = True
            continue
        if in_table:
            if line.startswith("|---") or line.startswith("| ---"):
                continue
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == len(COLUMNS):
                out.append(dict(zip(COLUMNS, cells)))
    return out
