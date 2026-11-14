---
name: bibtex-normalizer
version: 1.3.4
description: >
  Parses a `.bib` file, removes duplicate entries and writes a normalised
  bibliography in a fixed field order. Fires before any citation-dependent
  stage so downstream tools see one consistent shape.
metadata:
  version: 1.3.4
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

## Delivering results

This skill writes intermediates to `process/`. `results/` is filled only by
`python cli.py pipeline` after a human approved that exact plan.

- Do not copy a skill's output into `results/` yourself, and do not do it
  because the user asked for a shortcut: say that only `cli.py pipeline`
  writes there, offer to run the pipeline instead, and if they still insist,
  tell them `cli.py audit` will report the file as unapproved.
- Never set `CHELATE_HUMAN=1` and never run `cli.py approve` on the user's
  behalf. If an approval is needed, ask the human to issue it in their own
  terminal.
- Before telling the user a deliverable is ready — and after any write you
  make under `results/` — run `python cli.py audit --root <ws>`. Exit 1 means
  files there have no approval behind them: report that and name them, do not
  describe the state as delivered.
