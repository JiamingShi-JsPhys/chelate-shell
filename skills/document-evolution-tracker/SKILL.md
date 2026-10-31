---
name: document-evolution-tracker
version: 1.2.0
description: >
  Tracks how a family of document versions evolved: discovers the version
  files, aligns them block by block, and reports paragraph-level changes plus
  the lineage of named concepts across versions. Fires when a set of drafts
  must be compared over time rather than one pair of files.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# document-evolution-tracker

Diffs a whole family of document versions and traces named concepts through
them. It reports **structural** change — block alignment via `difflib` — not
semantic meaning.

- **Stage:** `workspace` · **Sandbox:** no · **Dependencies:** stdlib only (`PyYAML` only for `.yaml` configs)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action versions -- --config config/examples/family.json
```

- `validate` first: it reports config errors and the discovered version files.
- `--concepts "a,b"` names the concepts to trace; unnamed ones are not followed.
- The gate lands in `<WS>/process/gates/document-evolution-tracker_<ts>.json`.

## When to use

- A family of versions (timestamped or sequentially named) must be compared as a whole.
- A named concept — a term, a heading, a definition — must be traced across versions.
- The evolution of a draft must be reported as a timeline, not a single diff.

## When NOT to use

- Only two files need a diff — any diff tool is cheaper.
- You need semantic equivalence, not a structural comparison.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `validate` | Check the config and report the discovered versions | `--config <cfg>` |
| `versions` | List the discovered version files | `--config <cfg>` |
| `run` | Compare the family and produce the timeline | `--config <cfg> [--concepts "a,b"]` |

## Hard constraints

- **Structural only.** A concept counts as present on a literal match, never on a paraphrase.
- **Never reformat the sources.** Inputs are read, never written.

## Outputs

- `<WS>/process/gates/document-evolution-tracker_<ts>.json` — the gate result.
- A Markdown timeline plus a JSON change record under `process/`.

## Failure handling

- An invalid config exits non-zero and names the offending field.
- Fewer than two discovered versions aborts the run.
- A concept that never appears is reported as absent across all versions.

## Limitations

- Diffing is structural (block alignment), not semantic.
- Only `sequential` and `timestamp` naming schemes are recognised.
