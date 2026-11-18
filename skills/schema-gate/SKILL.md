---
name: schema-gate
version: 1.4.0
description: >
  Validates CSV/JSON against a column contract; an unknown keyword is
  UNVERIFIED, never pass.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# schema-gate

Checks a dataset against a schema you write, and reports every violation with
its column, row and kind. `data-profiler` describes what is in a file; this
gate decides whether the file is what the project said it would be.

- **Stage:** `gates` · **Sandbox:** no · **Dependencies:** none (standard library)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action check --input data.csv --schema schema.json
```

- Column keywords: `type` (`number` | `integer` | `string` | `boolean`),
  `required`, `allowed`, `min`, `max`, `pattern`. **Anything else is
  refused** — a validator that skipped an unknown keyword would report a PASS
  for a check it never made.
- Results land in `<WS>/process/gates/`, the full report in `<WS>/process/`.

## Verdicts

| Status | When |
| --- | --- |
| `PASS` | every declared cell satisfies the contract |
| `FAIL` | at least one violation; the report names column, row and kind |
| `UNVERIFIED` | the schema or data cannot be checked (unknown keyword, unreadable file, zero rows) |

## When to use

- A dataset feeds a conclusion and its shape is part of the claim.
- A pipeline must stop when a column disappears or a value leaves its range.

## When NOT to use

- You need statistical profiling — that is `data-profiler`.
- Your schema uses JSON Schema keywords (`$ref`, `oneOf`, `items`, …). This
  gate implements a small subset and refuses the rest on purpose.

## More

- [schema format, outputs, failure handling and limits](references/schema-gate-reference.md)
