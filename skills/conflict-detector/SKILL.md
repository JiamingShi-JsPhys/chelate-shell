---
name: conflict-detector
version: 1.2.0
description: >
  Cross-checks two or more documents, datasets or extracted fact tables for
  contradictions and reports each conflict with a severity. Numbers are
  compared with hard cross-checks, not fuzzy inference.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# conflict-detector

Finds claims that disagree across sources and grades them by level: entity
(numeric/boolean), clause (categorical), argument (free text). It reports
conflicts; it does not decide which source is right.

- **Stage:** `gates` · **Sandbox:** no · **Dependencies:** stdlib only (`PyYAML` only for `.yaml` configs)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action run -- --config config/examples/two_docs.yaml
```

- `validate` first: it is fast and writes no report.
- `--format json,csv,md` selects the output formats (default: json).
- The gate lands in `<WS>/process/gates/conflict-detector_<ts>.json`.

## When to use

- Two or more sources must be checked against each other.
- A single claim appears in several places and their agreement matters.
- An extracted fact table must be audited for internal contradictions.

## When NOT to use

- Only one document is involved — there is nothing to cross-check.
- You need a correctness judgement rather than a consistency report.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `validate` | Check the config, no report written | `--config <cfg>` |
| `list-docs` | List the sources a config resolves to | `--config <cfg>` |
| `run` | Detect conflicts | `--config <cfg> [--format json,csv,md]` |

## Hard constraints

- **Never invent a conflict.** An empty report is a valid result.
- **Report severity as computed**, never re-graded by hand.

## Outputs

- `<WS>/process/gates/conflict-detector_<ts>.json` — the gate result.
- The conflict report in the requested formats under `process/`.

## Failure handling

- An invalid config exits non-zero and names the field.
- An unreachable source aborts the run naming that source.
- No conflicts found is a success with an empty report.

## Limitations

- Extraction is key-value oriented; free-text paragraphs only participate at the argument level.
- Unit normalisation is table-driven (`unit_map`); custom units must be declared.
