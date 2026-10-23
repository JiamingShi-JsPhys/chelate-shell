"""multi-dim-manager — v1.1.0 root adapter (thin; legacy tree untouched).

The legacy skill tree under scripts/ is preserved byte-for-byte from v1.0.0
(parameter-space expansion, SHA-256 snapshots, hash audit logs, rollback):

    python run.py --root <workspace> --action <run|dryrun|rollback|summary|
        verify> --config config.example.yaml

The Router passes the generic stage action ("workspace"); it maps to the
safe default subcommand (dryrun — prints the Cartesian plan without
executing anything).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "multi-dim-manager"
SKILL_ROOT = adapter.skill_root(__file__)

ACTIONS = {
    "run": ("scripts.run", "main", "sub"),
    "dryrun": ("scripts.run", "main", "sub"),
    "rollback": ("scripts.run", "main", "sub"),
    "summary": ("scripts.run", "main", "sub"),
    "verify": ("scripts.run", "main", "sub"),
}
DEFAULT_ACTION = "dryrun"


def _gate(rc, out, sub):
    if rc == 0:
        return "PASS", "EXACT", f"subcommand {sub!r} completed"
    return "FAIL", "EXACT", (f"subcommand {sub!r} exited rc={rc}: "
                             f"{adapter.tail(out)}")


if __name__ == "__main__":
    sys.exit(adapter.run_legacy(
        SKILL, ACTIONS, default_action=DEFAULT_ACTION, skill_dir=SKILL_ROOT,
        gate_map=_gate,
        description="Parameter sweeps with snapshots, audit logs, rollback."))
