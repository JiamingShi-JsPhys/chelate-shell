"""Lagged-mediator step: T-1 covariate construction + R/lavaan SEM.

The Python side builds the time-lagged covariates (``pain_t_minus_1``,
``willingness_t_minus_1``, subject means), writes them to a CSV under
``outputs/logs``, and hands that CSV to ``R/mediation.R`` (lavaan bootstrap
SEM). The resulting path estimates are written to
``outputs/tables/mediation_paths.csv``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from .. import r_runner

__all__ = ["run"]

_SKILL_ROOT = Path(__file__).resolve().parents[2]


def _build_lagged(
    df: pd.DataFrame,
    cfg,
    x: str,
    m: str,
    y: str,
    controls: list,
) -> pd.DataFrame:
    """Add T-1 lagged covariates and the subject mean to a copy of ``df``."""
    out = df.copy()
    out = out.sort_values([cfg.id_column, cfg.time_column])
    grp = out.groupby(cfg.id_column)

    out[f"{x}_t_minus_1"] = grp[x].shift(1)
    out[f"{y}_t_minus_1"] = grp[y].shift(1)
    out[f"{m}_t"] = out[m]
    out[f"{y}_t"] = out[y]
    out["subject_mean"] = grp[x].transform("mean")

    for c in controls:
        if c not in out.columns and c not in df.columns:
            raise ValueError(f"mediation step: control '{c}' not in data")
    return out


def run(df: pd.DataFrame, config: Dict, cfg) -> Path:
    """Run the lagged-mediator SEM and write the path-estimate CSV."""
    x = config.get("x")
    m = config.get("m")
    y = config.get("y")
    if not (x and m and y):
        raise ValueError("mediation step requires 'x', 'm', 'y'")
    controls = config.get("controls") or []

    lagged = _build_lagged(df, cfg, x, m, y, controls)

    tmp = Path(cfg.outputs["logs"]) / "mediation_input.csv"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    lagged.to_csv(tmp, index=False)

    payload = {"data_input": str(tmp), "seed": cfg.seed}
    result = r_runner.run_r(str(_SKILL_ROOT / "R" / "mediation.R"), payload)

    out = Path(cfg.outputs["tables"]) / "mediation_paths.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(result.get("paths", [])).to_csv(out, index=False)
    return out
