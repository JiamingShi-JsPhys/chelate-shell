# schema-gate

Validate a CSV or JSON dataset against a declared column contract — types,
required columns, allowed values, ranges, patterns — and fail on any
violation.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

Nothing. Standard library only.

## Usage

```bash
python run.py --root <workspace> --action check --input data.csv --schema schema.json
python run.py --root <workspace> --action check --input runs.json --schema schema.json
```

JSON input is either an array of objects or `{"rows": [ ... ]}`.

## Schema

```json
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
```

A keyword the validator does not implement (`$ref`, `oneOf`, `items`, …) is
refused rather than ignored: the gate degrades to `UNVERIFIED` instead of
certifying a check it never made.

## Outputs

| Path | Content |
|------|---------|
| `process/gates/schema-gate_<ts>.json` | gate result (PASS / FAIL / UNVERIFIED) |
| `process/schema_report_<stem>_<ts>.json` | violation counts by kind, and up to 20 sample violations with column, row and kind |
