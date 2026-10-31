---
name: bibtex-normalizer
version: 1.2.0
description: >
  Parses a `.bib` file, removes duplicate entries and writes a normalised
  bibliography in a fixed field order. Fires before any citation-dependent
  stage so downstream tools see one consistent shape.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# bibtex-normalizer

Normalises and de-duplicates a bibliography. It does not look up missing
metadata and does not verify that an entry exists.

- **Stage:** `ingest` · **Sandbox:** no · **Dependencies:** `bibtexparser`

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action normalize --input refs.bib
```

- Output defaults to `<WS>/process/bibtex/`; override with `--outdir`.
- The gate lands in `<WS>/process/gates/bibtex-normalizer_<ts>.json`.

## When to use

- Several `.bib` exports must be merged into one consistent file.
- Duplicate entries must be removed before a build or a citation check.

## When NOT to use

- The entries themselves must be verified — that is `reference-auditor`.
- Missing fields must be filled from the web — not supported.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `normalize` | Parse, dedupe, normalise field order | `--input <file.bib> [--outdir <dir>]` |

## Hard constraints

- **Never invent metadata.** Absent fields stay absent.
- **Dedupe by content key**, and report what was dropped.

## Outputs

- `<WS>/process/bibtex/` — the normalised `.bib` plus a JSON summary.
- `<WS>/process/gates/bibtex-normalizer_<ts>.json` — the gate result.

## Failure handling

- A malformed `.bib` fails the gate with the parser's message.
- `bibtexparser` missing → `UNVERIFIED`.

## Limitations

- No network lookup; no metadata completion.
- Non-standard entry types are preserved but not validated.
