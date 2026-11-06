"""data-profiler — gates-stage CSV health check (thin adapter).

All profiling logic lives in lib/chelate_core/csv_profile.py; this file
only parses CLI arguments and maps outcomes onto the gate contract:

    python run.py --root <workspace> --action profile --input data.csv

Verdicts:
    PASS        profile computed (missing values / outliers are REPORTED,
                not failures — the gate certifies the dataset was read and
                characterized)
    FAIL        CSV unreadable, empty, or has no columns
    UNVERIFIED pandas missing

Outputs:
    process/gates/data-profiler_<ts>.json    the gate result
    process/data_profile_<stem>_<ts>.json    the full profile
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter, csv_profile, paths  # noqa: E402

SKILL = "data-profiler"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ("pandas",)


def _configure(ap) -> None:
    ap.add_argument("--input", required=True, help="path to the source CSV")


def _profile(args) -> dict:
    cfg = adapter.load_config(SKILL_ROOT)
    adapter.require_deps(DEPENDENCIES, "CSV profiling")
    csv_path = paths.resolve_input(args.root, args.input)
    if not csv_path.is_file():
        raise adapter.Failed(f"input CSV not found: {csv_path}")
    fence = float(cfg.get("outlier_fence", csv_profile.OUTLIER_FENCE))
    try:
        profile = csv_profile.profile_csv(csv_path, fence=fence)
    except Exception as exc:
        raise adapter.Failed(
            f"CSV unreadable: {type(exc).__name__}: {exc}")
    if profile["rows"] == 0:
        raise adapter.Failed(f"{csv_path.name} has a header but zero rows")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = adapter.bootstrap().write_json(
        str(Path(args.root) / "process"),
        f"data_profile_{csv_path.stem}_{stamp}.json", profile)
    return {
        "status": "PASS", "evidence_level": "EMPIRICAL",
        "reason": (f"{profile['rows']} rows x {profile['cols']} cols, "
                   f"missing {profile['missing_pct']}%, outliers "
                   f"{profile['outlier_pct_overall']}%, duplicates "
                   f"{profile['duplicate_rows']}"),
        "artifacts": [out_path],
        "data": {"rows": profile["rows"], "cols": profile["cols"],
                 "missing_pct": profile["missing_pct"],
                 "outlier_pct_overall": profile["outlier_pct_overall"],
                 "duplicate_rows": profile["duplicate_rows"],
                 "outlier_fence": fence},
    }


HANDLERS = {"profile": _profile}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Profile a CSV: counts, missing values, outliers, dupes."))
