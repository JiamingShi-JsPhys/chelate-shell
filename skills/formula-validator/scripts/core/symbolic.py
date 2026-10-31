"""Symbolic identity proving with honest degradation.

The important part of this module is the three-way verdict:

* ``proven``     - a simplification chain drove ``lhs - rhs`` to exactly zero.
* ``disproven``  - the difference is not zero, and high-precision arithmetic
  confirms the mismatch. This is a real error.
* ``unresolved`` - the difference did not simplify to zero, but high-precision
  arithmetic says it is numerically zero. Almost always this means SymPy's
  simplifier gave up, not that the formula is wrong.

Reporting ``unresolved`` as "wrong" would train the user to ignore the
verifier, so it is reported as its own state with the evidence attached.
"""

from __future__ import annotations

import sympy as sp

__all__ = ["prove_identity", "high_precision_check"]

_MAX_OPS = 800
_HP_DIGITS = 40

_TACTICS = (
    ("cancel", lambda e: sp.cancel(sp.together(e))),
    ("expand", lambda e: sp.expand(e, force=True)),
    ("trigsimp", sp.trigsimp),
    ("powsimp", lambda e: sp.powsimp(e, force=True)),
    ("simplify", sp.simplify),
)


def _zero_test(expr) -> bool:
    # ``Matrix.is_zero`` is False even for an all-zero matrix in SymPy, so
    # matrices need their own path before falling back to the scalar tests.
    if getattr(expr, "is_Matrix", False):
        try:
            if expr.is_zero_matrix is True:
                return True
        except Exception:
            pass
        try:
            if expr.equals(sp.zeros(*expr.shape)):
                return True
        except Exception:
            pass
        return all(_zero_test(e) for e in expr)
    for probe in (lambda e: e.is_zero,
                  lambda e: sp.simplify(e).is_zero):
        try:
            if probe(expr) is True:
                return True
        except Exception:
            continue
    return False


def high_precision_check(diff, point: dict | None, digits: int = _HP_DIGITS) -> bool | None:
    """Evaluate ``diff`` at ``point`` in high precision. None = inconclusive."""
    if not point:
        return None
    try:
        subbed = diff.subs({sp.Symbol(k): sp.nsimplify(v, rational=True)
                            for k, v in point.items() if v is not None})
        value = sp.N(subbed, digits)
        if not getattr(value, "is_number", False) or value.is_finite is False:
            return None
        z = complex(value)
        return abs(z) < 10.0 ** (-(digits // 2))
    except Exception:
        return None


def prove_identity(lhs, rhs, point: dict | None = None,
                   max_ops: int = _MAX_OPS) -> dict:
    """Try to prove ``lhs == rhs`` symbolically. Returns a result dict."""
    out = {
        "status": "unresolved",
        "tactic": None,
        "difference": None,
        "high_precision_agrees": None,
        "note": None,
    }
    try:
        diff = sp.together(lhs - rhs)
    except Exception as exc:
        out["note"] = f"could not form the difference: {exc}"
        return out

    if _zero_test(diff):
        out.update(status="proven", tactic="direct", difference="0")
        return out

    if sp.count_ops(diff) > max_ops:
        hp = high_precision_check(diff, point)
        out["high_precision_agrees"] = hp
        if hp is True:
            out["note"] = ("the difference is too large to simplify, but "
                           "high-precision arithmetic finds it zero")
        else:
            out["note"] = "the difference is too large for symbolic proving"
        try:
            out["difference"] = sp.sstr(diff)
        except Exception:
            pass
        return out

    current = diff
    for name, tactic in _TACTICS:
        try:
            simplified = tactic(current)
        except Exception:
            continue
        if simplified is None:
            continue
        current = simplified
        if _zero_test(current):
            out.update(status="proven", tactic=name, difference="0")
            return out
        if sp.count_ops(current) > max_ops * 4:
            out["note"] = f"simplification via '{name}' grew too large; stopped"
            break

    try:
        out["difference"] = sp.sstr(current)
    except Exception:
        out["difference"] = "<unprintable>"

    hp = high_precision_check(current, point)
    out["high_precision_agrees"] = hp
    if hp is True:
        out["status"] = "unresolved"
        out["note"] = ("the difference did not simplify to zero, but 40-digit "
                       "arithmetic at the worst sample point still agrees; this "
                       "is most likely a simplifier limitation")
    elif hp is False:
        out["status"] = "disproven"
        out["note"] = ("the difference is not zero and high-precision "
                       "arithmetic confirms the disagreement")
    else:
        out["status"] = "unresolved"
        out["note"] = ("the difference did not simplify to zero and no "
                       "high-precision cross-check was possible")
    return out
