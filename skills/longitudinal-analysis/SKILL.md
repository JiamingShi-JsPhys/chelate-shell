---
name: longitudinal-analysis
description: Reproducible statistical pipeline for longitudinal and panel data. Runs LMM and mediation analysis via R, degrading gracefully if Rscript is missing.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.1.3
  entry_point: python run.py
  python_requires: '>=3.10'
---



# longitudinal-analysis







A self-contained skill that runs a **reproducible multi-step analysis on



longitudinal / panel data**. Each step is independently enabled and



audited; R (lme4 / lavaan) is invoked for the statistical heavy lifting



and the Python side orchestrates + degrades gracefully when R is absent.







## MANDATORY WORKFLOW


## Dependency bootstrap (run on first use)

Before the first run, probe the runtime deps for this skill:

- **Required (Python)**: `pandas`, `PyYAML`.
- **Optional (Python)**: `statsmodels`, `scipy` (manipulation-check step).
- **Required (external)**: `R >= 4.0` with `lme4`, `lavaan`, `emmeans`,
  `jsonlite` on PATH — needed for the `lmm`, `mediation`, and
  `sensitivity` steps.

Behavior:

- Missing **Python** deps -> tell the user which are absent and ask
  whether to `python -m pip install pandas pyyaml` (add `statsmodels
  scipy` for the manipulation check). Install only after they confirm;
  prefer a project-local venv.
- Missing **R** or R packages -> do **not** attempt to install R. List the
  exact missing R packages, **skip** the R-backed steps, record the reason
  in the audit log, and deliver the Python-only steps that do run.







1. Load the YAML config (`config/examples/behavior_2x2x2.yaml` as reference).



2. Confirm `data.input` exists and the `id_column` / `time_column` are



   present.



3. `python -m src.cli run --config <path> [--step <name>]`.



4. Report the per-step status; **skipped** R steps mean R is not installed



   - list the missing packages and stop (do not attempt an install).



5. Point the user at `results/tables/*.csv` and



   `results/logs/analysis_log.jsonl`.







## When to use







- The user has panel / repeated-measures data (one or more sessions per



  subject, with between-subject conditions) and wants a reproducible



  analysis rather than a one-off calculation.



- The request names a technique: "LMM", "mixed model", "repeated



  measures", "longitudinal analysis", "mediation over time", "lagged



  mediator", or "sensitivity analysis of RE structure".



- Descriptive stats, a manipulation check, or a sensitivity analysis over



  random-effects / covariance structures must be produced with an audit



  trail.







## Usage examples







```bash



# Validate a config and list the steps it enables.



python -m src.cli validate --config config/examples/behavior_2x2x2.yaml



python -m src.cli list-steps --config config/examples/behavior_2x2x2.yaml







# Run the full pipeline, or a single named step.



python -m src.cli run --config config/examples/behavior_2x2x2.yaml



python -m src.cli run --config config/examples/behavior_2x2x2.yaml --step lmm







# Export the generated tables (csv or docx).



python -m src.cli export --config config/examples/behavior_2x2x2.yaml --format csv



```







Results land in `results/tables/*.csv`; the per-step audit trail is



`results/logs/analysis_log.jsonl`.







## Failure handling







- **A step reports `skipped`** - R or an R package is missing. List the



  missing packages and stop; do not attempt an install and do not



  substitute a hand-rolled computation.



- **Config invalid** (`validate` exits non-zero) - fix the reported field



  (usually `data.input`, `id_column`, or `time_column`) and re-validate.



- **A step errors mid-pipeline** - earlier steps' outputs are kept and



  audited; report the failing step verbatim and stop, do not re-run



  blindly.



- **Unexpected exit code** - report the message verbatim.







## Pipeline steps







| Type | Module | R dependency |



| --- | --- | --- |



| `descriptive` | `src/steps/descriptive.py` | none |



| `anova` (manipulation check) | `src/steps/manipulation.py` | none (statsmodels) |



| `lmm` | `src/steps/lmm.py` | `R/lmm.R` (lme4 + emmeans) |



| `mediation` (lagged) | `src/steps/mediation.py` | `R/mediation.R` (lavaan) |



| `sensitivity` | `src/steps/sensitivity.py` | `R/lmm.R` |







## Limitations







- R packages (`lme4`, `lavaan`, `emmeans`, `jsonlite`) must be installed



  locally; the pipeline **skips** R-backed steps when `Rscript` is not on



  PATH and logs the reason in the audit.



- The mediation bootstrap is the user's choice (default 5000); wall-clock



  cost scales with sample size.






