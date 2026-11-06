# Changelog

## [1.3.0] - 2026-10-28

- Merged the standalone figure-generator skill into sci-visualizer: the
  figure engine (`scripts/engine.py`, formerly `skills/figure-generator/scripts/`)
  now ships under `scripts/` and is imported in-process by `run.py`.
- `manifest.json` gains `matplotlib` / `seaborn` / `pandas` as declared
  dependencies; missing libraries degrade the gate to `UNVERIFIED`,
  never a crash.
- `run.py` adds `--chart`, `--x`, `--y`, `--hue`, `--title` pass-through
  flags for tabular static input (the engine's full signature).
- `figure-generator` skill removed from the routing table; `sem-copilot`
  removed as well (extracted as an independent standalone plugin).

## [1.2.0] - 2026-10-24

- Initial scaffold as a thin generation-stage meta-skill; static charts
  delegated to figure-generator via subprocess; gif/animation frame-scan
  via optional Pillow.
