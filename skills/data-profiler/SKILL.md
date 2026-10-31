---
name: data-profiler
version: 1.2.0
description: >
  Profiles a CSV with pandas: row and column counts, per-column missing-value
  statistics, 1.5·IQR outlier ratios, duplicate rows and constant columns. It
  certifies that the file was read and characterised — never that it is clean.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# data-profiler

Produces the first look at a dataset and reports what is in it. **A PASS means
'characterised', never 'clean'.** The profiler never modifies the input.

- **Stage:** `gates` · **Sandbox:** no · **Dependencies:** `pandas`

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action profile --input data.csv
```

- The gate lands in `<WS>/process/gates/data-profiler_<ts>.json`; the full
  profile in `<WS>/process/data_profile_<stem>_<ts>.json`.
- Missing values, outliers and duplicates are **reported**, not failed.

## When to use

- Before any analysis of a new CSV.
- Sanity-checking exported lab data.
- Comparing datasets across experiment rounds.

## When NOT to use

- Statistical modelling — that is `longitudinal-analysis`.
- Cleaning or imputing data — the profiler never writes.
- Datasets too large for memory.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `profile` | Profile the CSV | `--input <data.csv>` |

## Hard constraints

- **Missing values and outliers are REPORTED, not FAIL.**
- **FAIL means unreadable, empty or header-only.**
- **The input CSV is never modified.**

## Outputs

- `<WS>/process/data_profile_<stem>_<ts>.json` — the full profile.
- `<WS>/process/gates/data-profiler_<ts>.json` — the gate result.

## Failure handling

- An unreadable or empty CSV fails the gate.
- A header-only file is a FAIL (no rows to characterise).
- `pandas` missing → `UNVERIFIED`.

## Limitations

- Numeric-only outliers; non-numeric columns get counts only.
- The Tukey multiplier is `assets/config.yaml` (default 1.5).
