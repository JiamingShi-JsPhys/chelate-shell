"""ai-trace-remover — v1.1.0 root adapter (thin; legacy tree untouched).

The legacy skill tree under src/ is preserved byte-for-byte from v1.0.0
(English clean-room pattern lexicon, Chinese lexicon, 0-100 AI-likeness
score, template-sentence removal):

    python run.py --root <workspace> --action scan <manuscript path> [-o out]

The legacy CLI takes a positional path; this adapter forwards remaining
arguments unchanged (mode "nosub": no subcommand is prepended).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "ai-trace-remover"
SKILL_ROOT = adapter.skill_root(__file__)

ACTIONS = {
    "scan": ("src.cli", "main", "nosub"),
    "report": ("src.cli", "main", "nosub"),
}
DEFAULT_ACTION = "scan"


def _gate(rc, out, sub):
    if rc == 0:
        return "PASS", "EMPIRICAL", f"action {sub!r} completed"
    return "FAIL", "EMPIRICAL", (f"action {sub!r} exited rc={rc}: "
                                 f"{adapter.tail(out)}")


if __name__ == "__main__":
    sys.exit(adapter.run_legacy(
        SKILL, ACTIONS, default_action=DEFAULT_ACTION, skill_dir=SKILL_ROOT,
        gate_map=_gate,
        description="AI-likeness audit: template removal + 0-100 score."))
