"""document-evolution-tracker — v1.1.0 root adapter (thin; legacy untouched).

The legacy skill tree under src/ is preserved byte-for-byte from v1.0.0
(paragraph-level diff, concept lineage, evolution timelines):

    python run.py --root <workspace> --action <run|versions|validate> \
        --config config/examples/family.json
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "document-evolution-tracker"
SKILL_ROOT = adapter.skill_root(__file__)

ACTIONS = {
    "run": ("src.cli", "main", "sub"),
    "versions": ("src.cli", "main", "sub"),
    "validate": ("src.cli", "main", "sub"),
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
        description="Document version diffs and concept-lineage tracking."))
