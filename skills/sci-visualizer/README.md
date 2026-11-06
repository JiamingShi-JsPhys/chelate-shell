# sci-visualizer

Generation-stage meta-skill for Chelate Shell. Owns the figure-generation
engine in-process (matplotlib/seaborn/pandas, under `scripts/engine.py`)
and **frame-scans** gif/animation inputs with optional Pillow, emitting a
gate into the workspace.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Usage

```bash
# static chart (in-process engine, matplotlib/seaborn)
python run.py --root <workspace> --action process --type static \
    --input data.csv --chart scatter --x col1 --y col2 [--hue group]

# gif frame scan (optional Pillow)
python run.py --root <workspace> --action process --type gif --input anim.gif
```

## Output

- `static` → in-process engine render; artifacts under
  `<workspace>/process/figures/` (vector PDF + raster PNG).
- `gif` / `animation` → `<workspace>/process/figures/<stem>_frames.txt`
  with frame count and size.
- `UNVERIFIED` when no `--input` is given, when a required rendering
  library (`matplotlib`, `seaborn`, `pandas`) is missing, or (for
  gif/animation) when Pillow is missing — never a hard crash.

## License

The skill code is MIT (see [LICENSE](LICENSE)). Rendering dependencies
`matplotlib` / `seaborn` / `pandas` (BSD-3-Clause / PSF) and optional
`Pillow` (MIT) are permissive and compatible with the MIT distribution.
