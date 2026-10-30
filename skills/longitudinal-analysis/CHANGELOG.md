# Changelog

All notable changes to this skill are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-15

First public release of longitudinal-analysis: a reproducible
longitudinal / panel-data analysis pipeline.

### Added

- Pipeline orchestration over a YAML config with per-step enable/disable.
- Five step types: descriptive, anova (manipulation check), lmm,
  mediation (lagged), and sensitivity (random-effects / covariance sweep).
- R-backed statistical steps via `Rscript` (lme4 + emmeans for LMM,
  lavaan bootstrap SEM for lagged mediation).
- Pure-Python descriptive / manipulation steps (pandas + statsmodels)
  that run with no R installation.
- Deterministic audit log: per-step input / output SHA-256 hashes,
  wall-clock timestamps, and fixed seed; two identical runs yield
  identical digests.
- Graceful degradation: R-backed steps are **skipped** (not crashed)
  when `Rscript` is absent, with the reason written to the audit log.
- CLI (`src/cli.py`): `run [--step]`, `validate`, `init`, `export`,
  `list-steps`.

### Not claimed

- The mediation bootstrap is user-configurable (default 5000); wall-clock
  cost scales with sample size.
- This skill does not install R or its packages; the user provides them.
