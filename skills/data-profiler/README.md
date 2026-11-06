# data-profiler

Structural health check for CSV datasets with pandas. Missing values and
outliers are *reported*, not failed — the gate certifies that the dataset
was read and characterized.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

```bash
pip install pandas
```

## Usage

```bash
python run.py --root <workspace> --action profile --input data.csv
```

The Tukey fence multiplier comes from `assets/config.yaml` (default 1.5).

## Outputs

| Path | Content |
|------|---------|
| `process/data_profile_<stem>_<ts>.json` | rows/cols, per-column dtype, missing counts and percentages, numeric min/max/mean, outlier counts and percentages, duplicate rows, constant columns |
| `process/gates/data-profiler_<ts>.json` | gate result |

## Gate semantics

- **PASS** — profile computed (EMPIRICAL evidence). Data-quality findings
  are reported, never failed.
- **FAIL** — CSV unreadable, no columns, or zero rows.
- **UNVERIFIED** — `pandas` missing.

## Design

`run.py` is a thin adapter; the profiling core lives in
[`lib/chelate_core/csv_profile.py`](../../lib/chelate_core/csv_profile.py).
The input CSV is never modified.

## License

MIT — see [LICENSE](LICENSE).
