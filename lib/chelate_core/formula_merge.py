"""Verdict merge policy for formula-validator (legacy D1-D5 + pint layer).

The legacy pipeline (scripts/core, byte-identical from v1.0.0) produces a
verdict token in its stdout JSON; the v1.1.0 pint layer
(scripts/core/pint_units.py) cross-checks physical units for
single-equation actions. This module holds the combination policy so the
skill's run.py stays a thin adapter.

Combination table (validate/check actions):
    legacy pass + pint pass    -> PASS     (SYMBOLIC)
    legacy pass + pint fail    -> FAIL     (dimensional mismatch)
    legacy pass + pint unknown -> PASS     (pint skipped: no declarations)
    legacy fail/conflict       -> FAIL     (legacy reason)
    legacy unknown             -> UNVERIFIED
    parse_error/error          -> FAIL     (bad input or internal error)
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

EXIT_TO_STATUS = {
    "pass": ("PASS", "SYMBOLIC"),
    "fail": ("FAIL", "SYMBOLIC"),
    "conflict": ("FAIL", "SYMBOLIC"),
    "unknown": ("UNVERIFIED", "SYMBOLIC"),
    "parse_error": ("FAIL", "UNVERIFIED"),
    "error": ("FAIL", "UNVERIFIED"),
}

# actions whose single-equation form can carry a pint unit cross-check
UNIT_ACTIONS = ("validate", "check")


def extract_option(legacy_argv: List[str], flag: str) -> Optional[str]:
    """Return the value following `flag` in legacy_argv (or None)."""
    for i, a in enumerate(legacy_argv):
        if a == flag and i + 1 < len(legacy_argv):
            return legacy_argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return None


def extract_units(legacy_argv: List[str]) -> Dict[str, str]:
    """Collect --units NAME=UNIT pairs into a dict."""
    units = {}
    i = 0
    while i < len(legacy_argv):
        if legacy_argv[i] == "--units" and i + 1 < len(legacy_argv):
            pair = legacy_argv[i + 1]
            i += 2
        elif legacy_argv[i].startswith("--units="):
            pair = legacy_argv[i].split("=", 1)[1]
            i += 1
        else:
            i += 1
            continue
        if "=" in pair:
            name, _, unit = pair.partition("=")
            units[name.strip()] = unit.strip()
    return units


def pint_check(expr_text: str, units: Dict[str, str]) -> Dict:
    """Run the pint unit layer; never raises (unknown on any failure)."""
    try:
        from scripts.core import pint_units
    except Exception as exc:
        return {"status": "unknown",
                "reason": f"pint layer unavailable: {type(exc).__name__}: {exc}"}
    try:
        if "=" in expr_text:
            return pint_units.check_equation_units(expr_text, units)
        return pint_units.expression_dimensionality(expr_text, units)
    except Exception as exc:
        return {"status": "unknown",
                "reason": f"pint layer error: {type(exc).__name__}: {exc}"}


def merge_verdict(summary: Dict, rc: int, sub: str, expr_text: Optional[str],
                  units: Dict[str, str], out_text: str) -> Tuple[str, str, str, List[str]]:
    """Combine the legacy verdict with the pint layer.

    Returns (status, evidence_level, reason, artifacts).
    """
    verdict = summary.get("verdict", "")
    legacy_msg = summary.get("message") or _tail(out_text) or f"rc={rc}"

    if verdict in EXIT_TO_STATUS:
        status, evidence = EXIT_TO_STATUS[verdict]
    elif int(rc or 0) == 0:
        status, evidence, verdict = "PASS", "SYMBOLIC", "pass"
    else:
        status, evidence = "FAIL", "UNVERIFIED"

    if sub in UNIT_ACTIONS and expr_text:
        res = pint_check(expr_text, units)
        if res["status"] == "fail":
            status, evidence = "FAIL", "SYMBOLIC"
            legacy_msg = (f"pint unit mismatch: {res.get('reason', '')} "
                          f"(legacy verdict: {verdict or 'n/a'})")
        elif res["status"] == "pass" and status == "PASS":
            legacy_msg = (f"{legacy_msg} | pint: {res.get('reason', '')} "
                          f"[{res.get('lhs', '?')} = {res.get('rhs', '?')}]")
        else:
            legacy_msg = f"{legacy_msg} | pint skipped: {res.get('reason', '')}"

    artifacts = []
    if isinstance(summary.get("report"), str):
        artifacts.append(summary["report"])
    return status, evidence, legacy_msg, artifacts


def _tail(text: str, n: int = 2, limit: int = 240) -> str:
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return " | ".join(lines[-n:])[:limit]
