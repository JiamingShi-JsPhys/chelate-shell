"""quantitative-validator adapter -- thin CLI over scripts/engine.py.

Usage:
    python scripts/run.py --root <WS> --action gate \
        --formula "H2 + O2 -> H2O"
    python scripts/run.py --root <WS> --action gate --input equation.txt

The adapter only parses arguments and delegates to engine.validate(); all
business logic (formula grammar, equation splitting, atom-conservation
balance, rdkit periodic-table cross-check) lives in scripts/engine.py.

Input contract:
    --formula   a molecular formula ("H2O", "Ca(OH)2") or a full chemical
                equation ("CH4 + 2 O2 -> CO2 + 2 H2O"). Use "->", "=>",
                "==", "=" or the unicode arrow to separate the two sides.
    --input     optional file whose contents are the formula/equation
                (relative paths resolve against --root, then the cwd).
    rdkit is a hard dependency: when it is missing the gate degrades to
    UNVERIFIED (never a fabricated PASS/FAIL).
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "..")))
sys.path.insert(0, _HERE)

from lib.chelate_core import adapter  # noqa: E402

SKILL = "quantitative-validator"


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


def _read_input_text(args):
    """Return the formula/equation string from --formula or --input file."""
    if args.formula:
        return args.formula
    if args.input:
        path = _resolve(args.input, args.root)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    return ""


def _handler(args):
    text = _read_input_text(args)
    if text is None:
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": f"input file not found: {args.input!r}",
                "artifacts": []}
    if not text or not text.strip():
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": "no formula or equation supplied "
                          "(pass --formula or --input)", "artifacts": []}
    from engine import validate
    return validate(text, root=args.root)


def _configure(ap):
    ap.add_argument("--formula",
                    help="molecular formula or chemical equation, e.g. "
                         "'H2 + O2 -> H2O'")
    ap.add_argument("--input",
                    help="file containing a formula or equation "
                         "(relative paths resolve against --root)")


if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, {"gate": _handler},
        description="Atom-conservation gate (rdkit); degrades to UNVERIFIED "
                    "when rdkit is absent."))
