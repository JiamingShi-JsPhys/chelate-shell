"""Manipulation-check step: between-subjects ANOVA via statsmodels.

Writes an ANOVA table (Type II) to ``outputs/tables/manipulation_check.csv``.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Dict

import pandas as pd

__all__ = ["run"]


def run(df: pd.DataFrame, config: Dict, cfg) -> Path:
    """Run ``dv ~ between_1 * between_2 * ...`` and export the ANOVA table."""
    dv = config.get("dv")
    between = config.get("between") or []
    if not dv:
        raise ValueError("manipulation step requires 'dv'")
    if not between:
        raise ValueError("manipulation step requires at least one 'between' factor")

    import statsmodels.api as sm  # type: ignore[import-not-found]
    from statsmodels.formula.api import ols  # type: ignore[import-not-found]

    formula = f"{dv} ~ " + " * ".join(between)
    with warnings.catch_warnings():
        # statsmodels may emit SingularMatrixWarning for rank-deficient designs;
        # the ANOVA table is still valid for the factors that have >1 level.
        warnings.simplefilter("ignore")
        model = ols(formula, data=df).fit()
        anova = sm.stats.anova_lm(model, typ=2)

    out = Path(cfg.outputs["tables"]) / "manipulation_check.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    anova.to_csv(out)
    return out
