# figure-generator

Publication-quality chart processor. Renders a bar / line / scatter plot from
a CSV with [matplotlib](https://matplotlib.org/) + seaborn, applying top-journal
styling (Arial family, no top/right spines, 300 dpi), and writes a vector PDF
and a raster PNG into the workspace.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Usage

Router adapter (thin wrapper over `scripts/engine.py`):

```bash
python scripts/run.py --root <workspace> --action process --input data.csv \
    --chart scatter --x col1 --y col2 [--hue group]
```

## Output

- `PASS` with `artifacts` = `[figure.pdf, figure.png]` written under
  `<workspace>/process/figures/` (or the directory given by `--output-dir`).
- `UNVERIFIED` when a dependency is missing (`matplotlib not installed` /
  `seaborn/pandas not installed`) or the dataset cannot be read — never a
  hard crash.

## License

The skill code is MIT (see [LICENSE](LICENSE)). Its heavy dependencies
`matplotlib` (BSD-3-Clause / PSF), `seaborn` (BSD-3-Clause), `pandas` and
`numpy` (BSD-3-Clause) are permissive and compatible with the MIT distribution.
