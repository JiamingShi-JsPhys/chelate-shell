"""Concept lineage: track named concepts across versions.

A *concept* is a key phrase the user declares (or auto-detected as a heading /
term). The lineage graph records, for each version, whether the concept is
**introduced**, **retained**, **modified**, or **dropped** relative to the
previous version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

__all__ = [
    "ConceptState",
    "LineageNode",
    "build_lineage",
]

# States
INTRODUCED = "introduced"
RETAINED = "retained"
MODIFIED = "modified"
DROPPED = "dropped"


@dataclass
class LineageNode:
    version_id: str
    state: str
    note: str = ""

    def to_dict(self) -> Dict:
        return {"version": self.version_id, "state": self.state, "note": self.note}


def _contains(text: str, concept: str) -> bool:
    """Case-insensitive substring check with word-boundary tolerance."""
    return concept.lower() in text.lower()


def build_lineage(
    versions: List,  # List[versioning.Version]
    texts: Dict[str, str],  # version_id -> full text
    concepts: Optional[List[str]] = None,
    auto_detect_headings: bool = False,
) -> Dict[str, List[LineageNode]]:
    """Build a concept -> [LineageNode per version] mapping.

    Parameters
    ----------
    versions:
        Ordered version records (each with ``.version_id``).
    texts:
        Mapping of version_id to the full text of that version.
    concepts:
        Explicit concept phrases to track. If None and
        ``auto_detect_headings`` is True, top-level headings are used.
    auto_detect_headings:
        When concepts is None, harvest Markdown ``#`` / ``##`` headings as
        concepts.
    """
    if not concepts:
        if auto_detect_headings:
            concepts = _detect_headings(texts)
        else:
            return {}

    result: Dict[str, List[LineageNode]] = {c: [] for c in concepts}
    prev_text: Optional[str] = None

    for v in versions:
        vid = v.version_id
        cur = texts.get(vid, "")
        for c in concepts:
            in_cur = _contains(cur, c)
            if prev_text is None:
                state = INTRODUCED if in_cur else DROPPED
                note = "first version"
            else:
                in_prev = _contains(prev_text, c)
                if in_cur and not in_prev:
                    state = INTRODUCED
                    note = "newly present"
                elif in_cur and in_prev:
                    state = RETAINED
                    note = ""
                elif (not in_cur) and in_prev:
                    state = DROPPED
                    note = "removed in this version"
                else:
                    state = RETAINED
                    note = "absent in both"
            result[c].append(LineageNode(vid, state, note))
        prev_text = cur

    return result


def _detect_headings(texts: Dict[str, str]) -> List[str]:
    """Collect top-level Markdown headings across all versions, de-duplicated, order-preserving."""
    seen = []
    for text in texts.values():
        for line in text.splitlines():
            m = re.match(r"^\s*#+\s+(.+)", line)
            if m:
                h = m.group(1).strip()
                if h and h not in seen:
                    seen.append(h)
    return seen
