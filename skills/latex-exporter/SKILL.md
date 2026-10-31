---
name: latex-exporter
description: LaTeX export processor (no heavy dependency). Merges the Markdown reports under process/ and the graphics under process/figures/ into a single compilable .tex file under process/latex/. Pure standard-library Markdown subset converter.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.2.0
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
version: 1.2.0
---

# latex-exporter

## Quick Execution

**Do NOT read the source code. Run this exact command format directly:**

```bash
python scripts/run.py --root <WS> --action process [--name report.tex]
python scripts/run.py --root <WS> --action export
```

- `--root <WS>` = the user's workspace (absolute path). The engine reads every
  Markdown report under `<WS>/process/` and every graphic
  (`.pdf/.png/.jpg/.jpeg/.eps`) under `<WS>/process/figures/`, then writes one
  compilable `.tex` to `<WS>/process/latex/<name>` — never into the skill's
  install dir.
- Valid `--action`: `process` / `export` (the generic stage action `process`
  maps to the same handler).
- `--name` sets the output filename (default `merged_report.tex`).
- **No sandbox needed (sandbox_required: false) and no pandoc.** The
  Markdown→LaTeX conversion is a pure standard-library subset renderer.

## What it produces
A complete `article` document: preamble (`graphicx`, `amsmath`, `hyperref`,
`geometry`; `ctex` auto-added when CJK text is detected), `\maketitle`, one
section structure per Markdown report (reports separated by `\clearpage`), and
a final `Figures` section with one `figure` float per graphic (caption derived
from the filename). Markdown subset handled: ATX headings, fenced code
(`verbatim`), pipe tables (`tabular`), bullet/numbered lists, block quotes,
horizontal rules, and inline **bold** / *italic* / `code` / links / images /
`$...$` math. LaTeX special characters are escaped; math and code are protected.

## When to use
- Stitch the reports a pipeline produced under `process/` into one manuscript.

## When NOT to use
- You need pandoc-grade fidelity for exotic Markdown (footnotes, definition
  lists, raw HTML). Complex TikZ authoring stays out of scope.

## Dependencies
- None beyond the Python standard library.
