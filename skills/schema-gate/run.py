"""schema-gate — gates-stage declared-schema check (thin adapter).

Logic lives in lib/chelate_core/schema_check.py:

    python run.py --root <workspace> --action check \
        --input data.csv --schema schema.json

PASS: every declared cell satisfies the contract. FAIL: at least one
violation. UNVERIFIED: an unsupported schema keyword, an unreadable file, or
zero data rows — never a pass for a check this validator cannot make.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, next(
    (p for p in (_HERE, os.path.dirname(_HERE),
                 os.path.dirname(os.path.dirname(_HERE)),
                 os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
     if os.path.isdir(os.path.join(p, "lib", "chelate_core"))),
    os.path.abspath(os.path.join(_HERE, "..", ".."))))

from lib.chelate_core import adapter, paths, schema_check  # noqa: E402

SKILL = "schema-gate"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ()


def _configure(ap) -> None:
    ap.add_argument("--input", required=True, help="CSV or JSON dataset")
    ap.add_argument("--schema", required=True, help="column contract (JSON)")


def _check(args) -> dict:
    data_path = paths.resolve_input(args.root, args.input)
    schema_path = paths.resolve_input(args.root, args.schema)
    for label, path in (("input", data_path), ("schema", schema_path)):
        if not path.is_file():
            raise adapter.Failed(f"{label} not found: {path}")

    try:
        schema = schema_check.load_schema(str(schema_path))
        columns, rows = schema_check.read_rows(str(data_path))
    except schema_check.SchemaError as exc:
        raise adapter.Degraded(f"not checkable: {exc}")
    if not rows:
        raise adapter.Degraded(f"{data_path.name} has a header but no data rows")

    report = schema_check.check(schema, columns, rows)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = adapter.bootstrap().write_json(
        str(Path(args.root) / "process"),
        f"schema_report_{data_path.stem}_{stamp}.json", report)

    if not report["ok"]:
        kinds = ", ".join(f"{kind}={count}" for kind, count
                          in sorted(report["violations_by_kind"].items()))
        raise adapter.Failed(
            f"{report['violation_count']} violation(s) in {data_path.name}: "
            f"{kinds}", evidence_level="EXACT", artifacts=[out_path])

    return {
        "status": "PASS", "evidence_level": "EXACT",
        "reason": (f"{report['rows']} rows x {len(report['columns'])} columns, "
                   f"{report['checked_cells']} cells checked against "
                   f"{len(schema['columns'])} declared columns"),
        "artifacts": [out_path],
        "data": {"rows": report["rows"], "columns": len(report["columns"]),
                 "declared": len(schema["columns"]),
                 "checked_cells": report["checked_cells"],
                 "violation_count": 0},
    }


HANDLERS = {"check": _check}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Validate a dataset against a declared column contract."))
