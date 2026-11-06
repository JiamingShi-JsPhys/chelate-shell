"""Core detection primitives: numeric / interval / boolean / categorical
contradictions.

Each detector returns a list of :class:`Conflict` records (structured, not
text) so the reporter can render them in any format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

__all__ = [
    "Conflict",
    "NumericClaim",
    "detect_numeric_mismatch",
    "detect_interval_overlap",
    "detect_boolean_conflict",
    "detect_categorical_mismatch",
]


@dataclass
class Conflict:
    """A single contradiction between two claims."""

    level: str          # entity | clause | argument
    claim_a: str        # human-readable description of claim A
    claim_b: str
    source_a: str       # document id
    source_b: str
    kind: str           # numeric_mismatch | interval_overlap | boolean | categorical
    detail: Dict = field(default_factory=dict)
    severity: str = "high"  # high | medium | low

    def to_dict(self) -> Dict:
        return {
            "level": self.level,
            "kind": self.kind,
            "severity": self.severity,
            "source_a": self.source_a,
            "source_b": self.source_b,
            "claim_a": self.claim_a,
            "claim_b": self.claim_b,
            "detail": self.detail,
        }


@dataclass
class NumericClaim:
    """A numeric claim with a unit / context key."""

    key: str
    value: float
    source: str
    tol: float = 1e-6


def detect_numeric_mismatch(a: NumericClaim, b: NumericClaim, tol: float = 1e-6) -> Optional[Conflict]:
    """Return a Conflict if two numeric claims disagree beyond tolerance."""
    if abs(a.value - b.value) > max(tol, max(abs(a.value), abs(b.value)) * 1e-9):
        return Conflict(
            level="entity",
            claim_a=f"{a.key} = {a.value}",
            claim_b=f"{b.key} = {b.value}",
            source_a=a.source,
            source_b=b.source,
            kind="numeric_mismatch",
            detail={"key": a.key, "a": a.value, "b": b.value, "delta": abs(a.value - b.value)},
        )
    return None


def detect_interval_overlap(
    a_key: str, a_lo: float, a_hi: float,
    b_key: str, b_lo: float, b_hi: float,
    source_a: str, source_b: str,
) -> Optional[Conflict]:
    """Return a Conflict if two intervals should be disjoint but overlap."""
    overlap = not (a_hi < b_lo or b_hi < a_lo)
    if overlap:
        return Conflict(
            level="entity",
            claim_a=f"{a_key} in [{a_lo}, {a_hi}]",
            claim_b=f"{b_key} in [{b_lo}, {b_hi}]",
            source_a=source_a,
            source_b=source_b,
            kind="interval_overlap",
            detail={
                "a": [a_lo, a_hi],
                "b": [b_lo, b_hi],
                "overlap": [max(a_lo, b_lo), min(a_hi, b_hi)],
            },
        )
    return None


def detect_boolean_conflict(
    a_key: str, a_val: bool,
    b_key: str, b_val: bool,
    source_a: str, source_b: str,
) -> Optional[Conflict]:
    """Return a Conflict if two boolean claims on the same key disagree."""
    if a_val != b_val:
        return Conflict(
            level="clause",
            claim_a=f"{a_key} is {a_val}",
            claim_b=f"{b_key} is {b_val}",
            source_a=source_a,
            source_b=source_b,
            kind="boolean",
            detail={"key": a_key, "a": a_val, "b": b_val},
        )
    return None


def detect_categorical_mismatch(
    a_key: str, a_val: str,
    b_key: str, b_val: str,
    source_a: str, source_b: str,
    allowed: Optional[List[str]] = None,
) -> Optional[Conflict]:
    """Return a Conflict if two categorical claims disagree (optionally within a controlled vocabulary)."""
    if a_val != b_val:
        detail: Dict = {"key": a_key, "a": a_val, "b": b_val}
        if allowed is not None:
            detail["outside_vocabulary"] = [v for v in (a_val, b_val) if v not in allowed]
        return Conflict(
            level="clause",
            claim_a=f"{a_key} = {a_val!r}",
            claim_b=f"{b_key} = {b_val!r}",
            source_a=source_a,
            source_b=source_b,
            kind="categorical",
            detail=detail,
            severity="medium" if allowed is None else "high",
        )
    return None
