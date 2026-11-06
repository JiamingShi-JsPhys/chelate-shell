"""Version discovery: enumerate and order a family of document versions.

Two naming schemes are supported:

- ``sequential``  -- ``v1.md, v2.md, ...`` or ``doc_001.md, ...``; ordered by
  the embedded integer.
- ``timestamp``   -- files named with an ISO-ish stamp; ordered by the stamp
  (falling back to mtime when the name carries no parseable timestamp).

The result is a deterministic, ordered list of :class:`Version` records so
the diff timeline is reproducible regardless of filesystem listing order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

__all__ = [
    "Version",
    "discover_versions",
]

_TS_RE = re.compile(r"(\d{8}T\d{6}Z?|\d{4}-\d{2}-\d{2}|\d{4}_\d{2}_\d{2})")
_SEQ_RE = re.compile(r"v?(\d+)", re.IGNORECASE)


@dataclass
class Version:
    """One document version in the family."""

    version_id: str
    path: Path
    label: str = ""
    sort_key: tuple = ()


def discover_versions(versions_dir: Path, naming: str = "sequential") -> List[Version]:
    """Return the versioned files in a directory, ordered.

    Parameters
    ----------
    versions_dir:
        Directory that contains the versioned files (or a single file).
    naming:
        ``"sequential"`` or ``"timestamp"``.
    """
    base = Path(versions_dir)
    if base.is_file():
        return [Version(version_id=base.name, path=base, label=base.name)]

    if not base.is_dir():
        raise FileNotFoundError(f"versions_dir not found: {base}")

    files = [p for p in base.iterdir() if p.is_file() and p.suffix.lower() in (".md", ".txt", ".tex", ".rst")]
    if not files:
        return []

    if naming == "timestamp":
        def key(p: Path):
            m = _TS_RE.search(p.name)
            if m:
                return (0, m.group(1))
            return (1, p.stat().st_mtime)

        ordered = sorted(files, key=key)
        return [Version(version_id=p.name, path=p, label=p.name, sort_key=()) for p in ordered]

    # sequential
    def skey(p: Path):
        m = _SEQ_RE.search(p.name)
        if m:
            return (0, int(m.group(1)), p.name)
        return (1, 0, p.name)

    ordered = sorted(files, key=skey)
    return [Version(version_id=p.name, path=p, label=p.name) for p in ordered]
