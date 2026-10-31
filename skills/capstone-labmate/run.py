"""capstone-labmate — v1.1.1 root adapter (thin; 3 legacy entries).

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

Output contract (v1.1.1): every stage writes inside the workspace
(``process/stage_a``, ``process/stage_c``, ``process/stage_d``) — the
defaults (``work/...``) are cwd-relative and would otherwise land in the
plugin cache under a host like Claude Code.
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

# legacy flag -> workspace-relative output directory (v1.1.1 output contract).
# process_cap/preconfigure_cap take --outdir; draft_report takes --out (a
# file, not a directory, so the parent dir is given).
OUTPUT_DIRS = {
    "ingest": {"--outdir": "process/stage_c"},
    "process": {"--outdir": "process/stage_c"},
    "preconfigure": {"--outdir": "process/stage_a"},
    "draft": {"--out": "process/stage_d/draft.md"},
}


def _gate(rc, out, sub):
    module = ACTIONS[sub][0]
    if rc == 0:
        return "PASS", "EMPIRICAL", f"{module} completed"
    return "FAIL", "EMPIRICAL", (f"{module} exited rc={rc}: "
                                 f"{adapter.tail(out)}")


if __name__ == "__main__":
    sys.exit(adapter.run_legacy(
        SKILL, ACTIONS, default_action=DEFAULT_ACTION, skill_dir=SKILL_ROOT,
        extra_paths=(SCRIPTS_DIR,), gate_map=_gate, output_dirs=OUTPUT_DIRS,
        description="PASCO Capstone .cap parsing, CSV/JSON, watermarked drafts."))
