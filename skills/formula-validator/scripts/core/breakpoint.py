"""Breakpoint localisation for multi-step derivations.

Given a chain ``E0 -> E1 -> ... -> En``, verify each consecutive pair and find
where the chain first breaks. The pair-wise check is what makes this useful: a
global ``E0 == En`` check tells you a derivation is wrong, the pair-wise check
tells you *which line* is wrong.

The diagnosis at the break is more valuable than the break itself, because the
three common causes need three different fixes:

* ``dimension_break``  - the dimension changed across the step. Almost always a
  dropped dimensional factor (a missing ``c``, ``hbar``, or ``1/2`` that carries
  units). Fix: recheck the substitution that introduced it.
* ``constant_factor``  - the dimension held but the ratio between the two sides
  is the same number at every sample. Fix: a coefficient is wrong.
* ``structural``       - the dimension held and the ratio varies. Fix: the
  functional form is wrong, recheck the algebra itself.
"""

from __future__ import annotations

import sympy as sp

from .dimensions import analyse
from .numeric import monte_carlo, sort_symbols

__all__ = ["locate_breakpoint"]


def _difference_text(a, b) -> str | None:
    if sp.count_ops(a) + sp.count_ops(b) > 300:
        return None
    try:
        return sp.sstr(sp.simplify(b - a))
    except Exception:
        try:
            return sp.sstr(b - a)
        except Exception:
            return None


def diagnose(prev, curr, symbols, mc: dict, dim_prev: dict,
             dim_curr: dict) -> dict:
    dp = dim_prev.get("dimension")
    dc = dim_curr.get("dimension")
    if dp is not None and dc is not None and dp != dc:
        return {
            "diagnosis": "dimension_break",
            "summary": ("the dimension changes across this step "
                        f"({dim_prev.get('dimension_text')} -> "
                        f"{dim_curr.get('dimension_text')})"),
            "fix_hint": "look for a dropped dimensional factor (c, hbar, ...)",
        }
    ratio = mc.get("ratio") or {}
    if ratio.get("looks_like_constant_factor"):
        return {
            "diagnosis": "constant_factor",
            "factor": ratio.get("mean"),
            "summary": (f"the two sides differ by a nearly constant factor of "
                        f"about {ratio.get('mean')} across all samples"),
            "fix_hint": "recheck the coefficient carried into this step",
        }
    spread, mean = ratio.get("spread"), ratio.get("mean")
    # A ratio of ~1 with a tiny spread means the sides agree; only report a
    # constant factor when the factor actually differs from 1.
    if (spread is not None and mean is not None and spread < 1e-3
            and abs(mean - 1.0) > 1e-6):
        return {
            "diagnosis": "constant_factor",
            "factor": mean,
            "summary": (f"the mismatch ratio is nearly constant "
                        f"(~{mean}, spread {spread})"),
            "fix_hint": "recheck the coefficient carried into this step",
        }
    return {
        "diagnosis": "structural",
        "summary": ("the mismatch ratio varies with the parameters, so the "
                    "functional form itself differs"),
        "fix_hint": "recheck the algebra of this step, not just a coefficient",
    }


def locate_breakpoint(steps: list, declared_units: dict | None = None,
                      n: int = 10000, tol: float = 1e-9, seed: int = 0,
                      auto_infer: bool = True,
                      positive: set[str] | None = None) -> dict:
    """Verify each consecutive pair in a derivation chain."""
    result = {
        "status": "unknown",
        "n_steps": len(steps),
        "steps": [],
        "first_break": None,
        "verified_up_to": None,
        "global_check": None,
    }
    if len(steps) < 2:
        result["note"] = "at least two steps are required for a chain check"
        return result

    symbols = sort_symbols(set().union(*[s.free_symbols for s in steps]))
    dims = [analyse(s, declared_units, auto_infer) for s in steps]

    breaks: list[dict] = []
    for i in range(len(steps) - 1):
        mc = monte_carlo(steps[i], steps[i + 1], symbols=symbols, n=n,
                         seed=seed, tol=tol, positive=positive)
        entry = {
            "step": i + 1,
            "from_index": i,
            "to_index": i + 1,
            "status": mc["status"],
            "max_rel_error": mc.get("max_rel_error"),
            "worst_point": mc.get("worst_point"),
            "lhs_at_worst": mc.get("lhs_at_worst"),
            "rhs_at_worst": mc.get("rhs_at_worst"),
            "difference": _difference_text(steps[i], steps[i + 1]),
            "dimension": dims[i + 1].get("dimension_text"),
            "diagnosis": None,
        }
        if mc["status"] == "fail":
            entry["diagnosis"] = diagnose(steps[i], steps[i + 1], symbols, mc,
                                          dims[i], dims[i + 1])
            breaks.append(entry)
        result["steps"].append(entry)

    if breaks:
        first = breaks[0]
        result["first_break"] = first
        result["verified_up_to"] = first["from_index"]
        result["status"] = "fail"
        result["n_breaks"] = len(breaks)
    else:
        result["verified_up_to"] = len(steps) - 1
        result["status"] = "pass"
        result["n_breaks"] = 0

    result["global_check"] = monte_carlo(
        steps[0], steps[-1], symbols=symbols, n=n, seed=seed, tol=tol,
        positive=positive)
    return result
