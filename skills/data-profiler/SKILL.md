---
name: data-profiler
description: Profiles a CSV with pandas — row and column counts, per-column missing-value statistics, 1.5*IQR outlier ratios, duplicate rows and constant columns — and reports the profile as a gate result.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.1.1
  entry_point: python run.py
  python_requires: '>=3.10'
---

# data-profiler

This skill is the **first look at any dataset**: it reads a CSV and certifies that the file was parsed and characterized — shape, missing values, outliers, duplicates, constant columns. It answers "what is in this file", not "is this file good".

**Core Loop:** the skill measures; the agent decides what to clean. *A PASS here means 'characterized', never 'clean'.*

## When to use
- Before any analysis of a new CSV (pipeline gate or standalone).
- Sanity-checking exported lab data (e.g. a down-sampled `.cap` conversion).
- Comparing datasets across experiment rounds.

## When NOT to use (Out of Scope)
- Statistical modeling (use longitudinal-analysis).
- Cleaning or imputing data — the profiler never modifies the input.
- Datasets too large for memory (pandas reads the whole file).

## Core Workflow
1. **Profile:** `python run.py --root <workspace> --action profile --input data.csv`
2. **Inspect:** read `process/data_profile_<stem>_<ts>.json` — per-column missing/outlier percentages, duplicate rows, constant columns.
3. **Decide:** choose cleaning steps based on the profile; document them for the user.
4. **Re-profile:** after cleaning, run again and compare the two reports.

## Hard Constraints (Red Lines)
- **Missing values and outliers are REPORTED, not FAIL.** The gate certifies characterization only.
- **FAIL means unreadable, empty, or header-only** — a structural problem, not a data-quality opinion.
- **The input CSV is never modified.** All output goes to `process/`.
- **Numeric-only outliers.** Non-numeric columns get missing/unique counts, never fence statistics.

## Resources
- `run.py`: thin adapter (argparse + gate emission only).
- `lib/chelate_core/csv_profile.py`: the profiling core shared by the repo.
- `assets/config.yaml`: Tukey fence multiplier (default 1.5).
