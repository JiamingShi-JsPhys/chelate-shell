"""conflict-detector — v1.1.0 root adapter (thin; legacy tree untouched).

The legacy skill tree under src/ is preserved byte-for-byte from v1.0.0
(pluggable cross-document comparison, regex number extraction, structured
JSON/CSV conflict reports):

    python run.py --root <workspace> --action <run|validate|list-docs> \
        --config <config.yaml|json>
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "conflict-detector"
SKILL_ROOT = adapter.skill_root(__file__)

ACTIONS = {
    "run": ("src.cli", "main", "sub"),
    "validate": ("src.cli", "main", "sub"),
    "list-docs": ("src.cli", "main", "sub"),
}
DEFAULT_ACTION = "run"


def _gate(rc, out, sub):
    if rc == 0:
        return "PASS", "EXACT", f"subcommand {sub!r} completed"
    return "FAIL", "EXACT", (f"subcommand {sub!r} exited rc={rc}: "
                             f"{adapter.tail(out)}")


if __name__ == "__main__":
    sys.exit(adapter.run_legacy(
        SKILL, ACTIONS, default_action=DEFAULT_ACTION, skill_dir=SKILL_ROOT,
        gate_map=_gate,
        description="Cross-document contradiction engine with number checks."))
