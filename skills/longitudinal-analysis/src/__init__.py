"""longitudinal-analysis -- longitudinal statistical analysis pipeline.

Reproducible multi-step analysis for longitudinal / panel data:
descriptive stats, manipulation checks, linear mixed models, lagged
mediation, and sensitivity analyses. R (lme4 / lavaan) is invoked for the
statistical steps; pure-stdlib modules handle config, orchestration and
auditing so the package degrades gracefully when R is absent.
"""

__version__ = "1.2.0"
