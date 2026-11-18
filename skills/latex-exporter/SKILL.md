---
name: latex-exporter
version: 1.4.0
description: >
  Merges process/ Markdown and figures into one compilable .tex, standard
  library only.
metadata:
  version: 1.4.0
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
- The `.tex` lands in `<WS>/process/latex/` — **not** `results/`; promotion is
  the pipeline's job. The gate lands in `<WS>/process/gates/`.
- **Stdlib only**: never introduce a pandoc dependency, and never rewrite the
  prose — the Markdown is embedded as authored.

## When to use

- The final deliverable must be a single LaTeX file.
- Reports and figures already live under `process/`.

## When NOT to use

- The document must be compiled to PDF — that needs a LaTeX install.
- The sources are Word or HTML.

## More

- [actions, outputs, failure handling and limits](references/latex-exporter-reference.md)
