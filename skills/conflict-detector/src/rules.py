"""Cross-document rule engine.

Takes a per-document fact table (from :mod:`extract`) and produces the full
conflict list by pairing claims across documents according to the configured
levels.

Levels
------
- ``entity``   -- same key, different value (numeric / bool / categorical).
- ``clause``   -- boolean / categorical mismatch with severity downgraded.
- ``argument`` -- free-text lines that share a key but have different text.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from . import detect, normalize
from .detect import Conflict
from .extract import Fact
from .normalize import Normaliser

__all__ = ["run_detection", "pair_facts"]


def pair_facts(
    facts_by_doc: Dict[str, List[Fact]],
    key_aliases: Dict[str, str],
) -> List[List[Fact]]:
    """Group facts by canonical key and return the multi-doc groups only."""
    norm = Normaliser(key_aliases, {})
    by_key: Dict[str, List[Fact]] = defaultdict(list)
    for doc_id, facts in facts_by_doc.items():
        for f in facts:
            if f.kind == "text":
                # text facts don't participate in entity / clause detection
                continue
            by_key[norm.normalize_key(f.key)].append(f)
    # Only groups spanning 2+ distinct docs are interesting.
    out = []
    for key, group in by_key.items():
        docs = {f.source for f in group}
        if len(docs) >= 2:
            out.append(group)
    return out


def run_detection(
    facts_by_doc: Dict[str, List[Fact]],
    levels: List[str],
    key_aliases: Dict[str, str],
    numeric_tolerance: float = 1e-6,
) -> List[Conflict]:
    """Run all configured detection levels; return the flat conflict list."""
    conflicts: List[Conflict] = []
    groups = pair_facts(facts_by_doc, key_aliases)

    for group in groups:
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.source == b.source:
                    continue
                conflict = _detect_pair(a, b, levels, numeric_tolerance)
                if conflict is not None:
                    conflicts.append(conflict)

    # De-duplicate identical pairs (same key / source pair / values).
    seen = set()
    deduped: List[Conflict] = []
    for c in conflicts:
        sig = (c.level, c.source_a, c.source_b, c.claim_a, c.claim_b, c.kind)
        if sig not in seen:
            seen.add(sig)
            deduped.append(c)
    return deduped


def _detect_pair(a: Fact, b: Fact, levels: List[str], tol: float) -> Conflict | None:
    """Detect a single pair of facts. Returns None when consistent."""
    if "entity" in levels and a.kind == "numeric" and b.kind == "numeric":
        na = float(a.value)
        nb = float(b.value)
        if abs(na - nb) > max(tol, max(abs(na), abs(nb)) * 1e-9):
            return Conflict(
                level="entity",
                claim_a=f"{a.key} = {na}",
                claim_b=f"{b.key} = {nb}",
                source_a=a.source,
                source_b=b.source,
                kind="numeric_mismatch",
                detail={"key": a.key, "a": na, "b": nb, "delta": abs(na - nb)},
            )
    if "entity" in levels and a.kind == "bool" and b.kind == "bool":
        if a.value != b.value:
            return Conflict(
                level="entity",
                claim_a=f"{a.key} is {a.value}",
                claim_b=f"{b.key} is {b.value}",
                source_a=a.source,
                source_b=b.source,
                kind="boolean",
                detail={"key": a.key, "a": a.value, "b": b.value},
            )
    if "clause" in levels and a.kind in ("text", "categorical") and b.kind in ("text", "categorical"):
        if str(a.value) != str(b.value):
            return Conflict(
                level="clause",
                claim_a=f"{a.key} = {a.value!r}",
                claim_b=f"{b.key} = {b.value!r}",
                source_a=a.source,
                source_b=b.source,
                kind="categorical",
                detail={"key": a.key, "a": str(a.value), "b": str(b.value)},
                severity="medium",
            )
    if "argument" in levels and a.kind == "text" and b.kind == "text":
        if str(a.value).strip() != str(b.value).strip():
            return Conflict(
                level="argument",
                claim_a=f"{a.key} = {a.value!r}",
                claim_b=f"{b.key} = {b.value!r}",
                source_a=a.source,
                source_b=b.source,
                kind="categorical",
                detail={"key": a.key, "a": str(a.value), "b": str(b.value)},
                severity="low",
            )
    return None
