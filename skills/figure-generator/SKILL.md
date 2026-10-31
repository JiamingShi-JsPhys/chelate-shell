---
name: figure-generator
version: 1.2.0
description: >
  Renders publication-quality charts from a CSV table (bar, line, scatter) and
  SEM path diagrams from a JSON spec. Runs inside the process sandbox; output
  goes to `process/figures/`.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
---

# figure-generator

Produces figures from data, including AMOS-style structural-equation path
diagrams. It renders what the data says — it never invents points.

- **Stage:** `processors` · **Sandbox:** yes · **Dependencies:** `matplotlib`, `seaborn`, `pandas`

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python scripts/run.py --root <WS> --action process --input data.csv --chart bar
```

- `--x`, `--y`, `--hue` name the columns; `--title` overrides the derived one.
- A JSON spec with `"type": "sem_path"` draws a path diagram instead.
- Figures land in `<WS>/process/figures/`; the gate in `<WS>/process/gates/`.

## When to use

- A dataset needs a chart for a report or a paper.
- An SEM model must be drawn as a path diagram.

## When NOT to use

- The figure must be hand-composed — this is data-driven rendering.
- Animated output — out of scope.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `process` | Render the figure | `--input <csv\|json> [--chart bar\|line\|scatter] [--x --y --hue --title --output-dir]` |

## Hard constraints

- **Never fabricate data points.**
- **Never drop rows silently** — report what was plotted.

## Outputs

- `<WS>/process/figures/<name>.png` — the rendered figure.
- `<WS>/process/gates/figure-generator_<ts>.json` — the gate result.

## Failure handling

- A missing column fails the gate naming that column.
- `matplotlib`/`seaborn`/`pandas` missing → `UNVERIFIED`.

## Limitations

- Static output only.
- Chart types are limited to bar, line and scatter (plus the SEM renderer).
