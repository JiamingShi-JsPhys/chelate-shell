"""BibTeX parse / dedupe / normalize core (bibtexparser).

Compatible with bibtexparser v1 (dict entries) and v2 (Entry objects).
Dedupe rule (conservative): an entry collides when its normalized citation
key OR its (lowercased title, year) pair was already seen; first occurrence
wins and later duplicates are itemized in the report. v2 parsers collapse
repeated keys at parse time — that collapse is reported honestly so
total = unique + duplicates always holds.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

FIELD_ORDER = ("title", "author", "year", "journal", "booktitle", "volume",
               "number", "pages", "publisher", "address", "doi", "url",
               "eprint", "archivePrefix", "primaryClass", "month", "note")


def norm_title(title: str) -> str:
    """Lowercase, strip braces/punctuation and collapse whitespace."""
    t = re.sub(r"[{}\\$]", "", title or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def content_key(fields: dict) -> Tuple[str, str]:
    title = norm_title(fields.get("title", ""))
    year = (fields.get("year") or "").strip()
    return (title, year)


def entry_type(entry) -> str:
    return (getattr(entry, "entry_type", None)
            or entry.get("ENTRYTYPE", "misc"))


def entry_key(entry) -> str:
    return (getattr(entry, "key", None) or entry.get("ID") or "").strip()


def entry_items(entry):
    """Yield (key, value) pairs for bibtexparser v1 (dict) or v2 (Entry)."""
    fields_dict = getattr(entry, "fields_dict", None)
    if fields_dict is not None:  # v2: Entry.fields_dict -> {key: Field}
        for k, f in fields_dict.items():
            yield k, f.value
    elif isinstance(entry, dict):  # v1: plain dict
        for k, v in entry.items():
            if k in ("ENTRYTYPE", "ID"):
                continue
            yield k, v


def parse_bib(bib_path: Path) -> List:
    """Parse a .bib file with bibtexparser v2 (fallback: v1 API)."""
    import bibtexparser

    if hasattr(bibtexparser, "parse_file"):  # v2
        return bibtexparser.parse_file(str(bib_path)).entries
    with open(bib_path, encoding="utf-8") as f:  # v1
        from bibtexparser.bparser import BibTexParser
        parser = BibTexParser(common_strings=True)
        parser.ignore_nonstandard_types = False
        db = bibtexparser.load(f, parser)
        return db.entries


def format_entry(entry) -> str:
    """Emit one entry with canonical field order and consistent formatting."""
    etype = entry_type(entry).lower()
    fields = dict(entry_items(entry))
    ordered = [f for f in FIELD_ORDER if f in fields]
    ordered += sorted(k for k in fields if k not in FIELD_ORDER)
    lines = [f"@{etype}{{{entry_key(entry)},"]
    for f in ordered:
        value = " ".join(str(fields[f]).split())
        lines.append(f"  {f} = {{{value}}},")
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")
    return "\n".join(lines)


def normalize(bib_path: Path, outdir: Path) -> dict:
    """Parse, dedupe and re-emit `bib_path`; return the report dict."""
    raw_text = Path(bib_path).read_text(encoding="utf-8", errors="replace")
    raw_count = len(re.findall(r"@[A-Za-z]+\s*\{", raw_text))
    entries = list(parse_bib(Path(bib_path)))

    seen_keys, seen_content = {}, {}
    unique, duplicates = [], []
    for entry in entries:
        key = entry_key(entry)
        content = content_key(dict(entry_items(entry)))
        if key and key in seen_keys:
            duplicates.append({"dropped_key": key, "reason":
                               f"duplicate citation key of {seen_keys[key]}"})
            continue
        if content[0] and content in seen_content:
            duplicates.append({"dropped_key": key, "reason":
                               f"duplicate title+year of {seen_content[content]}"})
            continue
        if key:
            seen_keys[key] = key
        if content[0]:
            seen_content[content] = key or "<no-key>"
        unique.append(entry)

    # bibtexparser v2 collapses repeated citation keys at parse time; report
    # that honestly so total = unique + duplicates always holds.
    collapsed = raw_count - len(entries)
    if collapsed > 0:
        duplicates.append({"dropped_key": None, "reason":
                           f"{collapsed} duplicate citation key(s) collapsed "
                           f"by the parser"})

    unique.sort(key=lambda e: (entry_key(e).lower(),
                               content_key(dict(entry_items(e)))))
    header = (f"% Normalized by chelate bibtex-normalizer v1.1.0\n"
              f"% Source: {Path(bib_path).name}\n"
              f"% Entries: {len(unique)} unique "
              f"({len(duplicates)} duplicates removed)\n")
    text = header + "\n\n".join(format_entry(e) for e in unique) + "\n"
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out_bib = outdir / f"{Path(bib_path).stem}.normalized.bib"
    out_bib.write_text(text, encoding="utf-8")

    fields_seen = sorted({k for e in unique for k, _ in entry_items(e)})
    report = {
        "source": str(bib_path),
        "total": raw_count,
        "unique": len(unique),
        "duplicates": duplicates,
        "fields_seen": fields_seen,
        "normalized_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "output": str(out_bib),
    }
    out_json = outdir / f"{Path(bib_path).stem}.report.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    report["bib_path"] = str(out_bib)
    report["json_path"] = str(out_json)
    return report


def default_outdir(root: str) -> Path:
    return Path(root) / "process" / "bibtex"


def resolve_outdir(root: str, outdir: Optional[str]) -> Path:
    return Path(outdir) if outdir else default_outdir(root)
