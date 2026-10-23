"""Descriptive statistics step: grouped means / std / counts.

Pure pandas. Writes a tidy long-format CSV to ``outputs/tables/descriptives.csv``:
one row per (group..., variable, statistic) so the column layout is stable
regardless of how many group-by keys or DVs are supplied.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd

__all__ = ["run"]


def _tidy_group_agg(df: pd.DataFrame, group_by: List[str], dv: List[str]) -> pd.DataFrame:
    """Return a tidy frame: group columns + (variable, statistic, value)."""
    rows: List[Dict] = []
    for keys, sub in df.groupby(group_by, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        group_vals: Dict = {}
        for gkey, gval in zip(group_by, keys):
            group_vals[gkey] = gval
        for v in dv:
            for stat, val in (
                ("mean", sub[v].mean()),
                ("std", sub[v].std()),
                ("count", int(sub[v].count())),
            ):
                rows.append({**group_vals, "variable": v, "statistic": stat, "value": val})
    return pd.DataFrame(rows)


def run(df: pd.DataFrame, config: Dict, cfg) -> Path:
    """Aggregate ``dv`` by ``group_by`` (mean / std / count) and write CSV."""
    group_by = config.get("group_by") or []
    dv = config.get("dv") or []
    if not group_by or not dv:
        raise ValueError("descriptive step requires 'group_by' and 'dv'")

    missing = [c for c in list(group_by) + list(dv) if c not in df.columns]
    if missing:
        raise ValueError(f"descriptive step: columns not in data: {missing}")

    tidy = _tidy_group_agg(df, group_by, dv)

    out = Path(cfg.outputs["tables"]) / "descriptives.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    tidy.to_csv(out, index=False)
    return out
