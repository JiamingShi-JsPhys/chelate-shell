"""Document fact extraction.

Extracts claims from a document. Supports three input shapes:
- JSON (a list of facts, or a mapping of key -> value)
- Plain text (line-oriented ``key: value`` pairs, plus free text)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

__all__ = [
    "Fact",
    "extract_facts",
]


@dataclass
class Fact:
    """A single extracted claim."""

    key: str
    value: Any
    source: str
    raw: str = ""
    kind: str = "unknown"  # numeric | bool | categorical | text

    @staticmethod
    def _infer_kind(value: Any) -> str:
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, (int, float)):
            return "numeric"
        return "text"


def _facts_from_json(doc_id: str, data: Any) -> List[Fact]:
    out: List[Fact] = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                key = item.get("key", f"item{i}")
                val = item.get("value", item)
                out.append(
                    Fact(
                        key=str(key),
                        value=val,
                        source=doc_id,
                        raw=json.dumps(item, ensure_ascii=False),
                        kind=Fact._infer_kind(val),
                    )
                )
            else:
                out.append(
                    Fact(key=str(i), value=item, source=doc_id, raw=str(item), kind=Fact._infer_kind(item))
                )
    elif isinstance(data, dict):
        for k, v in data.items():
            out.append(
                Fact(key=str(k), value=v, source=doc_id, raw=json.dumps(v, ensure_ascii=False), kind=Fact._infer_kind(v))
            )
    return out


def _facts_from_text(doc_id: str, text: str) -> List[Fact]:
    out: List[Fact] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # Try to parse as JSON (numbers, bools, nested).
            try:
                parsed = json.loads(val)
                out.append(Fact(key=key, value=parsed, source=doc_id, raw=line, kind=Fact._infer_kind(parsed)))
                continue
            except (json.JSONDecodeError, TypeError):
                pass
            # Heuristic numeric / boolean.
            low = val.lower()
            if low in ("true", "false"):
                out.append(Fact(key=key, value=(low == "true"), source=doc_id, raw=line, kind="bool"))
            else:
                try:
                    out.append(Fact(key=key, value=float(val), source=doc_id, raw=line, kind="numeric"))
                except ValueError:
                    out.append(Fact(key=key, value=val, source=doc_id, raw=line, kind="text"))
        else:
            # Free text: store the whole line as a single "text" fact.
            out.append(Fact(key="line", value=line, source=doc_id, raw=line, kind="text"))
    return out


def extract_facts(doc_id: str, content: str) -> List[Fact]:
    """Extract facts from a document body (JSON or plain text)."""
    stripped = content.lstrip()
    # Quick JSON sniff.
    if stripped.startswith(("{", "[")):
        try:
            data = json.loads(stripped)
            return _facts_from_json(doc_id, data)
        except json.JSONDecodeError:
            pass
    return _facts_from_text(doc_id, content)
