"""LMM step: linear mixed model via Rscript (lme4 + emmeans).

The Python side only orchestrates: it hands a JSON payload to
``R/lmm.R``, parses the JSON result, and writes the fixed-effects table to
``outputs/tables/lmm_fixed_effects.csv``.

When Rscript is unavailable the runner raises :class:`RNotAvailableError`,
which the pipeline catches and logs as a skip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from .. import r_runner

__all__ = ["run"]

# R scripts live in <skill_root>/R, i.e. three levels up from this file:
#   src/steps/lmm.py  ->  skill_root/R
_SKILL_ROOT = Path(__file__).resolve().parents[2]


def run(df: pd.DataFrame, config: Dict, cfg) -> Path:
    """Run the configured LMM formula via R and write the fixed-effects CSV."""
    formula = config.get("formula")
    if not formula:
        raise ValueError("lmm step requires 'formula'")

    payload = {
        "data_input": str(cfg.data_input),
        "formula": formula,
        "reml": bool(config.get("reml", True)),
        "seed": cfg.seed,
    }

    result = r_runner.run_r(str(_SKILL_ROOT / "R" / "lmm.R"), payload)

    out = Path(cfg.outputs["tables"]) / "lmm_fixed_effects.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(result.get("fixed_effects", [])).to_csv(out, index=False)
    return out
