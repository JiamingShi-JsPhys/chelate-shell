---
name: sci-visualizer
version: 1.4.0
description: >
  Renders static scientific charts from tabular data and scans gif or
  animation frames.
metadata:
  version: 1.4.0
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
  `bar|line|scatter|box`; `--x`, `--y`, `--hue`, `--title` shape the figure.
- **Never fabricate data points, and never drop rows silently** — the reason
  says what was plotted.
- Output lands in `<WS>/process/figures/`; the gate in `<WS>/process/gates/`.

## When to use

- A dataset needs a publication-quality chart.
- A gif or frame sequence must be inspected frame by frame.

## When NOT to use

- An interactive or 3D visualisation — out of scope (`3d-modeler` makes
  meshes, not plots).
- The figure must be hand-composed.

## More

- [actions, outputs, failure handling and limits](references/sci-visualizer-reference.md)
