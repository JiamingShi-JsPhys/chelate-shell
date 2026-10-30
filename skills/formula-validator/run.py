"""formula-validator — v1.1.1 root adapter (thin; legacy tree untouched).

The legacy skill tree under scripts/ is preserved byte-for-byte from v1.0.0
(SymPy D1-D5: dimensional analysis, limit enumeration, numeric sampling,
symbolic proof, derivation breakpoints, matrix checks). This adapter wires
the Router to the legacy CLI and merges the NEW v1.1.0 pint physical-unit
layer (scripts/core/pint_units.py) on top. The merge policy itself lives in
lib/chelate_core/formula_merge.py:

    python run.py --root <workspace> --action <validate|check|derive|matrix|
        units> --expr "F = m*a" --units F=N --units m=kg --units a=m/s**2

    validate/check : legacy D1-D5 pipeline + pint unit cross-check
    derive/matrix  : legacy pipeline only (no single-equation unit form)
    units          : pint layer only

Output contract (v1.1.1): the legacy Markdown report is anchored to
``<workspace>/process/reports/`` — never the skill's own ``_reports/``
directory, which under a plugin install would point into the host's
plugin cache.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter, debug, formula_merge  # noqa: E402

SKILL = "formula-validator"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ("sympy", "numpy", "pint")

# actions handled by the legacy D1-D5 CLI
LEGACY_ACTIONS = {
    "validate": ("scripts.cli", "main", "sub"),
    "check": ("scripts.cli", "main", "sub"),
    "derive": ("scripts.cli", "main", "sub"),
    "matrix": ("scripts.cli", "main", "sub"),
}
PINT_ACTION = "units"
DEFAULT_ACTION = "validate"


def _gate(rc, out, sub):
    if rc == 0:
        return "PASS", "SYMBOLIC", f"subcommand {sub!r} completed"
    return "FAIL", "SYMBOLIC", (f"subcommand {sub!r} exited rc={rc}: "
                                f"{adapter.tail(out)}")


def _verdict(rc, out, sub, legacy_argv):
    """Merge the legacy D1-D5 verdict with the pint unit layer."""
    summary = adapter.last_json(out) or {}
    expr = formula_merge.extract_option(legacy_argv, "--expr")
    units = formula_merge.extract_units(legacy_argv)
    return formula_merge.merge_verdict(summary, rc, sub, expr, units, out)


def _units_action(root, legacy_argv):
    """pint-only action: no legacy CLI invocation."""
    bs = adapter.bootstrap()
    expr = formula_merge.extract_option(legacy_argv, "--expr")
    units = formula_merge.extract_units(legacy_argv)
    if not expr:
        bs.emit_gate(root, SKILL, "FAIL", "UNVERIFIED",
                     "action 'units' requires --expr")
        return 0
    res = formula_merge.pint_check(expr, units)
    status = {"pass": ("PASS", "SYMBOLIC"), "fail": ("FAIL", "SYMBOLIC")}
    if res["status"] in status:
        st, ev = status[res["status"]]
        bs.emit_gate(root, SKILL, st, ev,
                     f"pint: {res.get('reason', 'dimensions agree')}")
    else:
        bs.emit_gate(root, SKILL, "UNVERIFIED", "UNVERIFIED",
                     f"pint: {res.get('reason', 'unknown')}")
    return 0


def _anchor_report_dir(root: str) -> None:
    """Pin the legacy REPORT_DIR to the workspace before it is imported.

    The legacy CLI derives ``_reports/`` from its own SKILL_ROOT, which in a
    Claude Code plugin install points into the plugin cache — a write the
    host then flags as out-of-scope. Re-binding the module attribute to
    ``<workspace>/process/reports/`` (after import, before any call) keeps
    every report inside the workspace four-zone contract.
    """
    import pathlib
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    try:
        import scripts.cli as legacy_cli
    except ImportError:
        return
    target = pathlib.Path(root) / "process" / "reports"
    legacy_cli.REPORT_DIR = target
    debug.log(f"{SKILL}: legacy REPORT_DIR anchored to {target}")


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    # Hand-rolled flag split (adapter.split_legacy_argv): argparse
    # REMAINDER reorders unrecognised options and would tear "--expr"
    # away from its value before the legacy CLI ever sees them.
    own, legacy_argv, debug_on, help_on = adapter.split_legacy_argv(list(argv))
    debug.flag(debug_on)
    if help_on:
        adapter.print_adapter_usage(SKILL)
        return 0
    root = own["--root"]
    if not root:
        adapter.print_adapter_usage(SKILL, out=sys.stderr)
        print("formula-validator-adapter: error: --root <workspace> is "
              "required (reports must land inside the workspace)",
              file=sys.stderr)
        return 2
    action = own["--action"]
    sub = action if (action in LEGACY_ACTIONS
                     or action == PINT_ACTION) else DEFAULT_ACTION
    missing = adapter.probe_deps(DEPENDENCIES)
    if missing:
        adapter.bootstrap().emit_gate(
            root, SKILL, "UNVERIFIED", "UNVERIFIED",
            f"degraded: missing dependencies {missing}")
        return 0

    if sub == PINT_ACTION:
        return _units_action(root, legacy_argv)
    _anchor_report_dir(root)
    return adapter.run_legacy(SKILL, LEGACY_ACTIONS, argv=list(argv),
                              skill_dir=SKILL_ROOT,
                              default_action=sub,
                              verdict_hook=_verdict)


if __name__ == "__main__":
    sys.exit(main())
