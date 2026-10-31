---
name: latex-exporter
version: 1.2.0
description: >
  Merges the Markdown reports in `process/` plus the graphics in
  `process/figures/` into one compilable `.tex` file. Pure standard library —
  no pandoc, no LaTeX toolchain required to produce the file.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
---

# latex-exporter

Assembles the deliverable `.tex`. It does not compile it and does not typeset
content you did not write.

- **Stage:** `processors` · **Sandbox:** no · **Dependencies:** stdlib only (no pandoc)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python scripts/run.py --root <WS> --action export
```

- `--action process` is an alias; `--name report.tex` sets the filename
  (default `merged_report.tex`).
- The `.tex` lands in `<WS>/results/`; the gate in `<WS>/process/gates/`.

## When to use

- The final deliverable must be a single LaTeX file.
- Reports and figures already live under `process/`.

## When NOT to use

- The document must be compiled to PDF — that needs a LaTeX install.
- The sources are Word or HTML.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `export` | Merge reports + figures into one `.tex` | `[--name report.tex]` |
| `process` | Alias of `export` | `[--name report.tex]` |

## Hard constraints

- **Stdlib only.** Never introduce a pandoc dependency.
- **Never rewrite the prose** — the Markdown is embedded as authored.

## Outputs

- `<WS>/results/merged_report.tex` (or `--name`) — the merged document.
- `<WS>/process/gates/latex-exporter_<ts>.json` — the gate result.

## Failure handling

- No Markdown to merge fails the gate with a clear message.
- A missing figure file is reported, and the include is written commented out.

## Limitations

- No compilation step.
- Only Markdown and the common image formats are handled.
