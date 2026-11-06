"""CSV structural profiling core (pandas).

Produces the gate payload for data-profiler: row/column counts, per-column
missing-value statistics, numeric outlier ratios (Tukey 1.5*IQR fences),
duplicate rows and constant columns. Missing values and outliers are
REPORTED, not failures — the gate certifies that the dataset was read and
characterized, not that it is clean.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

OUTLIER_FENCE = 1.5  # Tukey 1.5*IQR fences


def profile_csv(csv_path: Path, fence: float = OUTLIER_FENCE) -> dict:
    """Profile `csv_path`; raises on unreadable/empty input.

    `fence` is the Tukey multiplier for outlier detection (1.5 by default).
    """
    import pandas as pd

    df = pd.read_csv(csv_path)
    if df.shape[1] == 0:
        raise ValueError("CSV has no columns")

    columns = []
    total_missing = 0
    for col in df.columns:
        series = df[col]
        n_missing = int(series.isna().sum())
        total_missing += n_missing
        entry = {
            "column": str(col),
            "dtype": str(series.dtype),
            "missing": n_missing,
            "missing_pct": round(100.0 * n_missing / len(df), 3) if len(df) else 0.0,
            "n_unique": int(series.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(series) and not series.dropna().empty:
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                lo, hi = q1 - fence * iqr, q3 + fence * iqr
                n_out = int(((series < lo) | (series > hi)).sum())
                entry["outliers"] = n_out
                entry["outlier_pct"] = round(100.0 * n_out / len(df), 3)
            else:
                entry["outliers"] = 0
                entry["outlier_pct"] = 0.0
            entry.update({"min": float(series.min()), "max": float(series.max()),
                          "mean": float(series.mean())})
        columns.append(entry)

    numeric = [c for c in columns if "outlier_pct" in c]
    dup_rows = int(df.duplicated().sum())
    constant = [c["column"] for c in columns if c["n_unique"] <= 1]

    return {
        "source": str(csv_path),
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "missing_total": total_missing,
        "missing_pct": round(100.0 * total_missing / df.size, 3) if df.size else 0.0,
        "duplicate_rows": dup_rows,
        "constant_columns": constant,
        "outlier_pct_overall": (
            round(sum(c["outlier_pct"] for c in numeric) / len(numeric), 3)
            if numeric else 0.0),
        "columns": columns,
        "profiled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
