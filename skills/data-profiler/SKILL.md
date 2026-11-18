---
name: data-profiler
version: 1.4.0
description: >
  Profiles a CSV: counts, missing values, IQR outliers, duplicates. Not a
  cleanliness check.
metadata:
  version: 1.4.0
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

- Missing values, outliers and duplicates are **reported**, not failed.
  **FAIL means unreadable, empty or header-only.**
- The gate lands in `<WS>/process/gates/data-profiler_<ts>.json`; the full
  profile in `<WS>/process/data_profile_<stem>_<ts>.json`.

## When to use

- Before any analysis of a new CSV.
- Sanity-checking exported lab data.
- Comparing datasets across experiment rounds.

## When NOT to use

- Statistical modelling — that is `longitudinal-analysis`.
- Cleaning or imputing data — the profiler never writes.
- Datasets too large for memory.

## More

- [actions, outputs, failure handling and limits](references/data-profiler-reference.md)
