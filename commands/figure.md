---
name: figure
description: Generate a publication-quality scientific chart from a CSV or JSON dataset.
metadata:
  skill: sci-visualizer
  stage: generation
  sandbox: true
---

# /figure — generate a scientific chart

Produces a journal-ready chart (bar / line / scatter / box) from a structured
dataset and writes a vector PDF + raster PNG into the workspace. The heavy
rendering (matplotlib / seaborn) runs in-process via the co-located figure
engine, so a pathological input degrades to `UNVERIFIED` rather than blocking
the pipeline.

## Usage

```bash
python skills/sci-visualizer/run.py --root <WS> \
    --action process --type static --input data.csv \
    --chart scatter --x col1 --y col2 [--hue group] [--title "Fig 1"]
```

- `--input` is branched by extension: `.json` is a spec (a SEM `sem_path`
  diagram or a generic table), `.csv` is rendered as a chart.
- `--chart` accepts `bar` (default), `line`, `scatter`, `box`.
- `--type static` (default) renders via the in-process matplotlib/seaborn
  engine; `--type gif` / `--type animation` frame-scan a `.gif` with
  optional Pillow.
- All artifacts land in `<WS>/process/figures/` — never in the skill dir.

## Direct engine access

The figure engine lives at `skills/sci-visualizer/scripts/engine.py`
and is importable in-process for scripted use:

```python
import sys
sys.path.insert(0, "skills/sci-visualizer/scripts")
from engine import generate

result = generate("data.csv", chart="scatter", x="col1", y="col2",
                  root="/path/to/workspace")
```
