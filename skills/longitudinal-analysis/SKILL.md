---
name: longitudinal-analysis
version: 1.2.0
description: >
  Runs a repeated-measures / panel analysis: descriptive statistics, a
  manipulation check, linear mixed models, mediation and sensitivity analysis.
  Python steps run anywhere; the mixed-model, mediation and sensitivity steps
  go through R and are skipped, not replaced, when Rscript is absent.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# longitudinal-analysis

Orchestrates a fixed pipeline of statistical steps over panel data and reports
each step's status. It never substitutes hand-written Python for a missing R
step.

- **Stage:** `gates` · **Sandbox:** no · **Dependencies:** `pandas` (`numpy`, R with lme4/lavaan, `python-docx` optional)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action list-steps -- --config config/examples/behavior_2x2x2.yaml
```

- `validate` then `list-steps` shows which steps the config enables and which
  need R.
- Run everything, or one named step with `--step lmm`.
- The gate lands in `<WS>/process/gates/longitudinal-analysis_<ts>.json`.

## When to use

- The data has repeated measures (one or more sessions per subject).
- The request names LMM, mixed model, mediation or sensitivity analysis.
- Descriptive statistics or a manipulation check are needed over panel data.

## When NOT to use

- The data is a single cross-section — a plain test is enough.
- You intend to imitate a skipped R step in Python — never do that.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `validate` | Check the config | `--config <cfg>` |
| `list-steps` | Show the enabled steps and their R needs | `--config <cfg>` |
| `run` | Run the whole pipeline, or one step | `--config <cfg> [--step lmm]` |
| `export` | Export the generated tables | `--config <cfg> --format csv\|docx` |

## Hard constraints

- **Never hand-write Python to replace a skipped R step.** Report the skip.
- **Never install R.** List the missing packages and stop.
- **Report each step's own status**; do not merge them into one verdict.

## Outputs

- `<WS>/process/gates/longitudinal-analysis_<ts>.json` — the gate result.
- Per-step tables (CSV, or DOCX with `--format docx`) under `process/`.

## Failure handling

- A step reporting `skipped` means R or an R package is missing — list it and stop.
- An invalid config exits non-zero naming the field.
- A mid-pipeline error keeps earlier outputs and reports the failing step.

## Limitations

- R packages (`lme4`, `lavaan`, `emmeans`, `jsonlite`) must already be installed.
- The mediation bootstrap count is the user's choice (default 5000) and dominates wall-clock time.
