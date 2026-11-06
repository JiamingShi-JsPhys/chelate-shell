"""task-organizer — v1.1.0 root adapter (thin; legacy tree untouched).

The legacy skill tree under scripts/ is preserved byte-for-byte from v1.0.0
(init / organize / broadcast / C1-C8 validation / snapshots / undo-redo).
This adapter only maps the generic Router action onto the legacy CLI:

    python run.py --root <workspace> --action <init|organize|broadcast|index|
        snapshot|dedupe|undo|redo|doctor|mark-downloaded|mark-user> [legacy args]

The Router passes the generic stage action ("workspace"); it maps to the
safe default subcommand (broadcast). All remaining arguments are forwarded
to the legacy CLI untouched.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "task-organizer"
SKILL_ROOT = adapter.skill_root(__file__)

# action -> (legacy module, entry function, argv builder mode)
ACTIONS = {
    "init": ("scripts.run", "run_from_cli", "rootsub"),
    "organize": ("scripts.run", "run_from_cli", "rootsub"),
    "broadcast": ("scripts.run", "run_from_cli", "rootsub"),
    "index": ("scripts.run", "run_from_cli", "rootsub"),
    "snapshot": ("scripts.run", "run_from_cli", "rootsub"),
    "dedupe": ("scripts.run", "run_from_cli", "rootsub"),
    "doctor": ("scripts.run", "run_from_cli", "rootsub"),
    "mark-downloaded": ("scripts.run", "run_from_cli", "rootsub"),
    "mark-user": ("scripts.run", "run_from_cli", "rootsub"),
    # undo/redo take --root plus a history file, not a positional root
    "undo": ("scripts.run", "run_from_cli", "subrootflag"),
    "redo": ("scripts.run", "run_from_cli", "subrootflag"),
}
DEFAULT_ACTION = "broadcast"


def _gate(rc, out, sub):
    if rc == 0:
        return "PASS", "EXACT", f"subcommand {sub!r} completed"
    return "FAIL", "EXACT", (f"subcommand {sub!r} exited rc={rc}: "
                             f"{adapter.tail(out)}")


if __name__ == "__main__":
    sys.exit(adapter.run_legacy(
        SKILL, ACTIONS, default_action=DEFAULT_ACTION, skill_dir=SKILL_ROOT,
        gate_map=_gate,
        description="Workspace infrastructure: init, organize, broadcast."))
