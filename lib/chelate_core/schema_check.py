"""Declared-schema validation for the schema-gate skill.

Caller: skills/schema-gate/run.py.
Data schemas:
    Reads:  a data file (CSV, or a JSON array of objects) and a schema file.
    Writes: nothing; returns a verdict dict.
Design: a documented subset, not JSON Schema.

    The schema is deliberately small::

        {
          "allow_extra_columns": true,
          "columns": {
            "time":  {"type": "number", "required": true, "min": 0},
            "mass":  {"type": "number", "min": 0.0001},
            "label": {"type": "string", "allowed": ["a", "b"]},
            "run":   {"type": "integer", "max": 12},
            "note":  {"type": "string", "pattern": "^[A-Z]"}
          }
        }

    Supported column keywords: ``type`` (number | integer | string |
    boolean), ``required`` (default true), ``allowed``, ``min``, ``max``,
    ``pattern``. Anything else raises :class:`SchemaError`.

    That last sentence is the point of this module. A validator that ignores
    a keyword it does not know reports PASS for a check it never made —
    exactly the false assurance the gate layer exists to prevent. An unknown
    keyword, an unknown type name, or a schema that is not an object is a
    refusal to verify (UNVERIFIED), never a pass.

    Missing values are empty strings (CSV) or JSON null. A missing value in a
    ``required`` column is a violation; in an optional column it is skipped.
"""
from __future__ import annotations

import csv
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

TOP_KEYS = {"columns", "allow_extra_columns", "description"}
COLUMN_KEYS = {"type", "required", "allowed", "min", "max", "pattern"}
TYPES = {"number", "integer", "string", "boolean"}
_BOOLEANS = {"true", "false"}


class SchemaError(ValueError):
    """The schema declares something this validator cannot check."""


def load_schema(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, ValueError) as exc:
        raise SchemaError(f"schema unreadable: {exc}") from exc
    validate_schema(schema)
    return schema


def validate_schema(schema: Any) -> None:
    if not isinstance(schema, dict):
        raise SchemaError("schema must be a JSON object")
    unknown = set(schema) - TOP_KEYS
    if unknown:
        raise SchemaError(f"unknown top-level key(s): {sorted(unknown)}")
    columns = schema.get("columns")
    if not isinstance(columns, dict) or not columns:
        raise SchemaError("schema needs a non-empty 'columns' object")
    for name, spec in columns.items():
        if not isinstance(spec, dict):
            raise SchemaError(f"column {name!r}: spec must be an object")
        extra = set(spec) - COLUMN_KEYS
        if extra:
            raise SchemaError(
                f"column {name!r}: unsupported keyword(s) {sorted(extra)} — "
                f"refusing to report a check this validator cannot make")
        kind = spec.get("type")
        if kind is not None and kind not in TYPES:
            raise SchemaError(f"column {name!r}: unknown type {kind!r}")
        if "required" in spec and not isinstance(spec["required"], bool):
            raise SchemaError(f"column {name!r}: required must be true or false")
        if "allowed" in spec and not isinstance(spec["allowed"], list):
            raise SchemaError(f"column {name!r}: allowed must be a list")
        for bound in ("min", "max"):
            if bound in spec and not isinstance(spec[bound], (int, float)):
                raise SchemaError(f"column {name!r}: {bound} must be a number")
        if "pattern" in spec:
            try:
                re.compile(str(spec["pattern"]))
            except re.error as exc:
                raise SchemaError(
                    f"column {name!r}: pattern does not compile ({exc})") from exc


def read_rows(path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Return (column order, rows). CSV or a JSON array of objects."""
    lower = path.lower()
    if lower.endswith(".json"):
        try:
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError) as exc:
            raise SchemaError(f"data unreadable: {exc}") from exc
        if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            payload = payload["rows"]
        if not isinstance(payload, list):
            raise SchemaError("JSON data must be an array of objects")
        order: List[str] = []
        rows: List[Dict[str, str]] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise SchemaError(f"JSON row {index} is not an object")
            for key in item:
                if key not in order:
                    order.append(key)
            rows.append({key: "" if value is None else str(value)
                         for key, value in item.items()})
        return order, rows

    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = [{key: (value or "") for key, value in row.items()
                     if key is not None} for row in reader]
            return list(reader.fieldnames or []), rows
    except OSError as exc:
        raise SchemaError(f"data unreadable: {exc}") from exc


def _violation(column: str, row: int, kind: str, detail: str) -> Dict[str, Any]:
    return {"column": column, "row": row, "kind": kind, "detail": detail}


def _cell_ok(spec: Dict[str, Any], value: str) -> Optional[str]:
    """Return a violation kind for *value*, or None when it satisfies *spec*."""
    kind = spec.get("type")
    if not value.strip():
        return "missing" if spec.get("required", True) else None
    if kind == "number":
        try:
            number = float(value)
        except ValueError:
            return "type"
        if "min" in spec and number < spec["min"]:
            return "min"
        if "max" in spec and number > spec["max"]:
            return "max"
    elif kind == "integer":
        try:
            int(value)
        except ValueError:
            return "type"
        if "min" in spec and int(value) < spec["min"]:
            return "min"
        if "max" in spec and int(value) > spec["max"]:
            return "max"
    elif kind == "boolean":
        if value.strip().lower() not in _BOOLEANS:
            return "type"
    if "allowed" in spec and value not in [str(item) for item in spec["allowed"]]:
        return "allowed"
    if "pattern" in spec and not re.search(str(spec["pattern"]), value):
        return "pattern"
    return None


def check(schema: Dict[str, Any], columns: Iterable[str],
          rows: List[Dict[str, str]], sample: int = 20) -> Dict[str, Any]:
    """Validate *rows* against *schema*; return counts and a bounded sample."""
    columns = list(columns)
    declared = schema["columns"]
    violations: List[Dict[str, Any]] = []

    duplicates = sorted({name for name in columns if columns.count(name) > 1})
    for name in duplicates:
        violations.append(_violation(name, 0, "duplicate-column",
                                     "the same column name appears twice"))

    for name, spec in declared.items():
        if name not in columns and spec.get("required", True):
            violations.append(_violation(name, 0, "missing-column",
                                         "declared required column is absent"))

    if not schema.get("allow_extra_columns", True):
        for name in columns:
            if name not in declared:
                violations.append(_violation(name, 0, "extra-column",
                                             "column is not declared"))

    checked = 0
    for index, row in enumerate(rows, start=2):  # header is line 1
        for name, spec in declared.items():
            if name not in row:
                continue
            kind = _cell_ok(spec, row[name])
            checked += 1
            if kind:
                violations.append(_violation(
                    name, index, kind,
                    f"value {row[name]!r} fails {kind}"))

    by_kind: Dict[str, int] = {}
    for item in violations:
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
    return {
        "ok": not violations,
        "checked_cells": checked,
        "rows": len(rows),
        "columns": columns,
        "violation_count": len(violations),
        "violations_by_kind": by_kind,
        "violations": violations[:sample],
    }
