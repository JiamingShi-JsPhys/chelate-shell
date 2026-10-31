---
name: ai-trace-remover
version: 1.2.0
description: >
  Removes template sentences from a manuscript and scores its 0–100
  "AI-likeness" with English and Chinese lexicons. It rewrites only matched
  patterns and always reports what it changed.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# ai-trace-remover

Strips formulaic phrasing and grades the residue. It never rewrites your
argument and never deletes a sentence silently.

- **Stage:** `processors` · **Sandbox:** no · **Dependencies:** stdlib only

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action scan -- <file>
```

- Everything after `--` is forwarded to the legacy CLI, which takes the
  manuscript path positionally.
- The gate lands in `<WS>/process/gates/ai-trace-remover_<ts>.json`.

## When to use

- A draft is about to be delivered and formulaic phrasing must go.
- A text's template density must be measured.

## When NOT to use

- The content itself must be improved — that is writing, not cleaning.
- The user wants a sentence deleted outright without a report.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `scan` | Scan and clean, then score | `<file> [-o <out>]` |
| `report` | Re-emit the score report | `<file>` |

## Hard constraints

- **Only matched patterns are touched.**
- **Every change is reported** — the diff is part of the output.

## Outputs

- The cleaned text (when an output path is given) under `process/`.
- `<WS>/process/gates/ai-trace-remover_<ts>.json` — the gate result and score.

## Failure handling

- A missing file exits non-zero with a clear message.
- No match yields a score of 0 — a valid result, not an error.

## Limitations

- Lexicon-based; it cannot judge whether prose is genuinely original.
- The score is a heuristic, not a detector verdict.
