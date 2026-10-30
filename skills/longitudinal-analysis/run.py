"""longitudinal-analysis — v1.1.0 root adapter (thin; legacy untouched).

The legacy skill tree under src/ and R/ is preserved byte-for-byte from
v1.0.0 (time-series OLS, LMM via lme4, mediation via lavaan, sensitivity
analysis; pure-Python steps when Rscript is absent):

    python run.py --root <workspace> --action <run|validate|init|export|
        list-steps> --config <config.yaml|json>

pandas is probed first: a missing dependency degrades to UNVERIFIED. R is
optional — the legacy pipeline skips R-backed steps on its own.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "longitudinal-analysis"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ("pandas",)

ACTIONS = {
    "run": ("src.cli", "main", "sub"),
    "validate": ("src.cli", "main", "sub"),
    "init": ("src.cli", "main", "sub"),
    "export": ("src.cli", "main", "sub"),
    "list-steps": ("src.cli", "main", "sub"),
}
DEFAULT_ACTION = "run"


def _gate(rc, out, sub):
    if rc == 0:
        return "PASS", "EMPIRICAL", f"subcommand {sub!r} completed"
    return "FAIL", "EMPIRICAL", (f"subcommand {sub!r} exited rc={rc}: "
                                 f"{adapter.tail(out)}")


if __name__ == "__main__":
    sys.exit(adapter.run_legacy(
        SKILL, ACTIONS, default_action=DEFAULT_ACTION, skill_dir=SKILL_ROOT,
        gate_map=_gate,
        dependencies=DEPENDENCIES, dep_purpose="longitudinal analysis unavailable",
        description="OLS / LMM / mediation / sensitivity for panel data."))
