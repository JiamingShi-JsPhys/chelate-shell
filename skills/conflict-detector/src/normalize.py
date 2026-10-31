"""Claim normalisation: units, time bases, and key canonicalisation.

The detector compares claims across documents, so the same quantity written
in different units or key spellings must normalise to the same form. This
module is intentionally small and deterministic; custom rules can be plugged
in via :class:`Normaliser`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

__all__ = [
    "Normaliser",
    "normalize_key",
    "normalize_value",
]

_KEY_CANON = re.compile(r"[\s._\-]+")


@dataclass
class Normaliser:
    """Stateful claim normaliser.

    ``key_map`` maps a known alias to its canonical key. ``unit_map`` maps a
    unit string to a base unit so numeric values can be rescaled.
    """

    key_map: Dict[str, str]
    unit_map: Dict[str, float]

    def normalize_key(self, key: str) -> str:
        """Canonicalise a key (case / punctuation-insensitive, alias-aware)."""
        raw = _KEY_CANON.sub("_", key.strip().lower())
        return self.key_map.get(raw, raw)

    def normalize_value(self, value: Any, unit: Optional[str] = None) -> Any:
        """Rescale a numeric value to the base unit if a unit mapping exists."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if unit and unit.lower() in self.unit_map:
                return float(value) * self.unit_map[unit.lower()]
            return float(value)
        if isinstance(value, str):
            return value.strip().lower()
        return value


def normalize_key(key: str, aliases: Optional[Dict[str, str]] = None) -> str:
    """Convenience wrapper without a stateful normaliser."""
    n = Normaliser(aliases or {}, {})
    return n.normalize_key(key)


def normalize_value(value: Any, unit: Optional[str] = None, units: Optional[Dict[str, float]] = None) -> Any:
    """Convenience wrapper for value normalisation."""
    n = Normaliser({}, units or {})
    return n.normalize_value(value, unit)
