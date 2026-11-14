---
name: sci-visualizer
version: 1.3.4
description: >
  Generation meta-skill: renders static scientific charts from tabular data and
  scans gif/animation frame sequences. Successor to `figure-generator`, adding
  the gif path and four chart types.
metadata:
  version: 1.3.4
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# sci-visualizer

Produces figures and inspects frame sequences. It renders what the data says
and never invents points.

- **Stage:** `generation` · **Sandbox:** no · **Dependencies:** `matplotlib`, `seaborn`, `pandas` (`Pillow` optional for gif frames)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action process --input data.csv --chart bar
```

- `--type {static,gif,animation}` selects the mode; `--chart` takes
  `bar|line|scatter|box`.
- `--x`, `--y`, `--hue`, `--title` shape the figure.
- Output lands in `<WS>/process/figures/`; the gate in `<WS>/process/gates/`.

## When to use

- A dataset needs a publication-quality chart.
- A gif or frame sequence must be inspected frame by frame.

## When NOT to use

- An interactive or 3D visualisation — out of scope (`3d-modeler` makes meshes, not plots).
- The figure must be hand-composed.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `process` | Render the figure or scan frames | `--input <csv\|json\|gif> [--type ...] [--chart ...] [--x --y --hue --title]` |

## Hard constraints

- **Never fabricate data points.**
- **Never drop rows silently** — report what was plotted.

## Outputs

- `<WS>/process/figures/<name>.png` — the rendered figure.
- `<WS>/process/gates/sci-visualizer_<ts>.json` — the gate result.

## Failure handling

- A missing column fails the gate naming that column.
- `matplotlib`/`seaborn`/`pandas` missing → `UNVERIFIED`.

## Limitations

- Static output; gif support is a frame scan, not video rendering.
- Four chart types plus the SEM renderer.

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
