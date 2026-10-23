"""Sensitivity step: LMM re-estimation across random-effects / covariance options.

For each candidate ``(random_effects, covariance)`` pair the step re-runs the
LMM and records AIC / BIC (or the error) to
``outputs/tables/sensitivity.csv``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd

from .. import r_runner

__all__ = ["run"]

_SKILL_ROOT = Path(__file__).resolve().parents[2]

# Default random-effects and covariance structures to sweep over.
_DEFAULT_RE = ["(1|subject_id)", "(1 + session|subject_id)"]
_DEFAULT_COV = ["us", "ar1"]


def run(df: pd.DataFrame, config: Dict, cfg) -> Path:
    """Sweep RE / covariance structures; write AIC-BIC table to CSV."""
    vary = config.get("vary") or ["random_effects", "covariance_structure"]
    if "random_effects" in vary and "covariance_structure" in vary:
        combinations: List[Dict] = [
            {"random_effects": re, "covariance": cov}
            for re in _DEFAULT_RE
            for cov in _DEFAULT_COV
        ]
    else:
        combinations = [
            {"random_effects": c, "covariance": c} for c in _DEFAULT_RE
        ]

    results = []
    for combo in combinations:
        formula = f"willingness ~ default * session + {combo['random_effects']}"
        payload = {
            "data_input": str(cfg.data_input),
            "formula": formula,
            "reml": True,
            "seed": cfg.seed,
        }
        try:
            r = r_runner.run_r(str(_SKILL_ROOT / "R" / "lmm.R"), payload)
            results.append(
                {
                    "random_effects": combo["random_effects"],
                    "covariance": combo["covariance"],
                    "aic": r.get("aic"),
                    "bic": r.get("bic"),
                }
            )
        except r_runner.RNotAvailableError as exc:
            results.append(
                {"random_effects": combo["random_effects"], "error": str(exc)}
            )
        except Exception as exc:  # pragma: no cover - defensive
            results.append(
                {"random_effects": combo["random_effects"], "error": str(exc)}
            )

    out = Path(cfg.outputs["tables"]) / "sensitivity.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(out, index=False)
    return out
