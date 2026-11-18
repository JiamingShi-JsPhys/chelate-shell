# schema-gate — reference

## Schema format

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

Supported column keywords: `type` (`number` | `integer` | `string` |
`boolean`), `required` (default `true`), `allowed`, `min`, `max`, `pattern`.
JSON input must be an array of objects, or `{"rows": [...]}`.

A schema keyword this validator does not implement degrades the gate to
`UNVERIFIED` instead of certifying a check it never made.

## Outputs

- `<WS>/process/gates/schema-gate_<ts>.json` — the gate result.
- `<WS>/process/schema_report_<ts>.json` — every violation with column, row
  and kind.

## Failure handling

- An unreadable schema or data file fails the gate with the path.
- A schema containing an unknown keyword is `UNVERIFIED`.
- A file with zero rows is `UNVERIFIED` — there is nothing to validate.

## Limitations

- A deliberately small subset of JSON Schema; `$ref`, `oneOf`, `items` and
  friends are refused rather than half-implemented.
- Extra columns pass unless `allow_extra_columns` is false.

## Delivering results

This skill writes intermediates to `process/`. `results/` is filled only by
`python cli.py pipeline` after a human approved that exact plan.

- Do not copy a skill's output into `results/` yourself, and do not do it
  because the user asked for a shortcut: say that only `cli.py pipeline`
  writes there, offer to run the pipeline instead, and if they still insist,
  tell them `cli.py audit` will report the file as unapproved.
- Never set `CHELATE_UNSAFE_AUTO_APPROVE=1` (formerly `CHELATE_HUMAN`) and
  never run `cli.py approve` on the user's behalf. If an approval is needed,
  ask the human to issue it in their own terminal.
- Before telling the user a deliverable is ready — and after any write you
  make under `results/` — run `python cli.py audit --root <ws>`. Exit 1 means
  files there have no approval behind them: report that and name them, do not
  describe the state as delivered.
