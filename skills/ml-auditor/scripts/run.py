"""ml-auditor adapter -- thin CLI over scripts/engine.py.

Usage:
    python scripts/run.py --root <WS> --action gate --input data.csv \
        [--label target]
    python scripts/run.py --root <WS> --action gate --data data.csv --label y

The adapter only parses arguments and delegates to engine.audit(); all
business logic (leakage scan + cross-validated label-error scan) lives in
scripts/engine.py.

Input contract:
    --input / --data   path to a labelled CSV (relative paths resolve against
                       --root, then the cwd).
    --label            name of the label/target column. When omitted it is
                       auto-detected (a column named label/target/y/class/
                       outcome, else the last column).
    scikit-learn + pandas are hard dependencies; cleanlab is an optional
    second opinion. A missing hard dependency degrades the gate to UNVERIFIED.
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..")))
sys.path.insert(0, _HERE)

from lib.chelate_core import adapter  # noqa: E402

SKILL = "ml-auditor"


def _resolve(path, root):
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    if root:
        candidate = os.path.join(root, path)
        if os.path.isfile(candidate):
            return candidate
    return path


def _handler(args):
    src = args.input or args.data
    if not src:
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": "no dataset supplied (pass --input/--data <csv>)",
                "artifacts": []}
    csv_path = _resolve(src, args.root)
    if not os.path.isfile(csv_path):
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": f"dataset not found: {src!r}", "artifacts": []}
    from engine import audit
    return audit(csv_path, label_col=args.label, root=args.root)


def _configure(ap):
    ap.add_argument("--input", help="path to a labelled CSV dataset")
    ap.add_argument("--data", help="alias for --input")
    ap.add_argument("--label",
                    help="label/target column name (auto-detected if omitted)")


if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, {"gate": _handler},
        description="ML data-audit gate: data-leakage + label-error "
                    "detection (scikit-learn; cleanlab optional)."))
