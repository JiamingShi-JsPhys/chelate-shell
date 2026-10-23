"""capstone-labmate — v1.1.0 root adapter (thin; 3 legacy entries).

The legacy skill tree under scripts/ is preserved byte-for-byte from v1.0.0
(.cap binary parser, CSV conversion, preconfigured templates, watermarked
draft reports). This adapter maps the generic Router action onto the three
legacy entry points:

    python run.py --root <workspace> --action <ingest|process|preconfigure|draft>

    ingest|process  -> scripts/process_cap.py     (.cap -> downsampled JSON/CSV)
    preconfigure    -> scripts/preconfigure_cap.py (PDF -> preconfigured .cap)
    draft           -> scripts/draft_report.py     (summary -> watermarked report)

The legacy modules use bare imports (import _capx), so the skill's scripts/
directory itself is placed on sys.path.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "capstone-labmate"
SKILL_ROOT = adapter.skill_root(__file__)
SCRIPTS_DIR = os.path.join(SKILL_ROOT, "scripts")

# adapter action -> (legacy module, entry function, argv builder mode)
ACTIONS = {
    "ingest": ("process_cap", "main", "nosub"),
    "process": ("process_cap", "main", "nosub"),
    "preconfigure": ("preconfigure_cap", "main", "nosub"),
    "draft": ("draft_report", "main", "nosub"),
}
DEFAULT_ACTION = "ingest"


def _gate(rc, out, sub):
    module = ACTIONS[sub][0]
    if rc == 0:
        return "PASS", "EMPIRICAL", f"{module} completed"
    return "FAIL", "EMPIRICAL", (f"{module} exited rc={rc}: "
                                 f"{adapter.tail(out)}")


if __name__ == "__main__":
    sys.exit(adapter.run_legacy(
        SKILL, ACTIONS, default_action=DEFAULT_ACTION, skill_dir=SKILL_ROOT,
        extra_paths=(SCRIPTS_DIR,), gate_map=_gate,
        description="PASCO Capstone .cap parsing, CSV/JSON, watermarked drafts."))
