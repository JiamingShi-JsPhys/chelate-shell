"""video-tracker — v1.1.0 root adapter (thin; legacy tree untouched).

The legacy skill tree under scripts/ is preserved byte-for-byte from v1.0.0
(CSRT/Template trackers, FFT spectrum analysis, physics consistency probes):

    python run.py --root <workspace> --action <probe|track|fft|physics|
        report|demo> --config <config.json>

The Router passes the generic stage action ("ingest"); it maps to the
default subcommand (track). numpy/opencv are probed first: a missing
dependency degrades to UNVERIFIED instead of crashing the pipeline.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "video-tracker"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ("numpy", "cv2")

ACTIONS = {
    "probe": ("scripts.run", "main", "sub"),
    "track": ("scripts.run", "main", "sub"),
    "fft": ("scripts.run", "main", "sub"),
    "physics": ("scripts.run", "main", "sub"),
    "report": ("scripts.run", "main", "sub"),
    "demo": ("scripts.run", "main", "sub"),
}
DEFAULT_ACTION = "track"


def _gate(rc, out, sub):
    if rc == 0:
        return "PASS", "EMPIRICAL", f"subcommand {sub!r} completed"
    return "FAIL", "EMPIRICAL", (f"subcommand {sub!r} exited rc={rc}: "
                                 f"{adapter.tail(out)}")


if __name__ == "__main__":
    sys.exit(adapter.run_legacy(
        SKILL, ACTIONS, default_action=DEFAULT_ACTION, skill_dir=SKILL_ROOT,
        gate_map=_gate,
        dependencies=DEPENDENCIES, dep_purpose="video tracking unavailable",
        description="OpenCV tracking, FFT spectra, physics consistency probes."))
