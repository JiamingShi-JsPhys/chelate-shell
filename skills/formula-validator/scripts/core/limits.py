"""Automatic limit-case enumeration.

Two things are checked here, and they are deliberately kept apart:

1. *Comparative* limits (the error-finding part). For an identity ``lhs = rhs``
   the two sides must behave identically as any variable runs to 0 or infinity.
   If one side stays finite while the other diverges, the formula is wrong -
   no interpretation required.

2. *Singularities* (the advisory part). Where does a denominator vanish?
   A divergence that appears on *both* sides is not an error, it is a property
   of the formula, so it is reported as information rather than a failure.

Conflating the two is the classic mistake: it makes every asymptotically
divergent-but-correct formula look broken.
"""

from __future__ import annotations

import numpy as np
import sympy as sp

from .numeric import _compile

__all__ = ["enumerate_limits", "find_singularities"]

_MAX_CHECKS = 60          # guard against combinatorial blow-up
_MAX_OPS = 400            # above this, symbolic limit() is too risky to attempt
_LIMIT_SIMPLIFY_MAX = 200 # simplify only small expressions before limit()
_TOL = 1e-9


def _classify(val) -> dict:
    """Turn a SymPy limit result into a small, comparable dict."""
    if val is None:
        return {"kind": "indeterminate"}
    if isinstance(val, sp.AccumBounds):
        return {"kind": "oscillating", "detail": sp.sstr(val)}
    if val is sp.nan or getattr(val, "is_nan", False):
        return {"kind": "undefined"}
    if getattr(val, "is_infinite", False):
        return {"kind": "divergent", "detail": sp.sstr(val)}
    if getattr(val, "is_number", False) and getattr(val, "is_finite", False):
        try:
            return {"kind": "finite", "value": float(val), "expr": val}
        except Exception:
            return {"kind": "finite", "detail": sp.sstr(val), "expr": val}
    # The limit resolved but still depends on other symbols. Keep the expression
    # so the two sides can be compared algebraically instead of shrugging.
    return {"kind": "conditional", "detail": sp.sstr(val), "expr": val}


def _numeric_probe(expr, sym, point, positive: bool) -> dict:
    """Fallback limit probe. Cheap, approximate, but always returns something."""
    try:
        f = _compile(expr, [sym])
    except Exception:
        return {"kind": "indeterminate"}
    if point is sp.oo or point == sp.oo:
        xs = np.array([1e2, 1e4, 1e6, 1e8, 1e10, 1e12], dtype=float)
    elif point == -sp.oo:
        xs = -np.array([1e2, 1e4, 1e6, 1e8, 1e10, 1e12], dtype=float)
    else:
        base = np.array([1e-2, 1e-4, 1e-6, 1e-8, 1e-10, 1e-12], dtype=float)
        xs = base if positive else np.concatenate([-base[::-1], base])
    try:
        with np.errstate(all="ignore"):
            raw = f(xs)
    except Exception:
        return {"kind": "indeterminate"}
    vals = np.asarray(raw, dtype=np.complex128).reshape(-1)
    tail = vals[-3:]
    if not np.all(np.isfinite(tail)):
        return {"kind": "divergent", "detail": "numeric probe overflowed"}
    mag = np.abs(tail)
    if mag.max() > 1e8:
        return {"kind": "divergent", "detail": f"|f| ~ {mag.max():.3g}"}
    if mag.max() < 1e-300:
        return {"kind": "finite", "value": 0.0}
    if float(np.std(mag) / max(float(mag.mean()), 1e-300)) < 1e-3:
        v = complex(tail[-1])
        return ({"kind": "finite", "value": float(v.real)}
                if abs(v.imag) < 1e-12 * max(abs(v.real), 1.0)
                else {"kind": "finite", "detail": str(v)})
    return {"kind": "oscillating", "detail": "numeric probe did not settle"}


def _limit(expr, sym, point, positive: bool) -> dict:
    if sp.count_ops(expr) > _MAX_OPS:
        return _numeric_probe(expr, sym, point, positive)
    # Algebraic simplification is sound here: the limit is invariant under it,
    # and it sidesteps a SymPy defect where some trigonometric / periodic
    # expressions make limit() loop inside igcd / series expansion
    # (e.g. limit(sin(x)**2 + cos(x)**2 - 1, x, 0) never returns). Simplifying
    # first turns such identities into a constant whose limit is trivial.
    if sp.count_ops(expr) <= _LIMIT_SIMPLIFY_MAX:
        try:
            expr = sp.simplify(expr)
        except Exception:
            pass
    try:
        val = sp.limit(expr, sym, point)
        got = _classify(val)
        if got["kind"] == "indeterminate":
            return _numeric_probe(expr, sym, point, positive)
        return got
    except Exception:
        return _numeric_probe(expr, sym, point, positive)


def _point_label(point) -> str:
    return "0" if point == 0 else sp.sstr(point)


def _compare(ll: dict, lr: dict, lhs, rhs, sym, point) -> dict:
    """Compare the two sides' behaviour at one limit point."""
    kl, kr = ll["kind"], lr["kind"]
    out = {"lhs": ll, "rhs": lr, "verdict": "pass", "severity": "info",
           "message": None, "ratio_limit": None}

    if kl == "finite" and kr == "finite":
        v1, v2 = ll.get("value"), lr.get("value")
        if v1 is None or v2 is None:
            out["verdict"] = "inconclusive"
            out["severity"] = "info"
            out["message"] = ("both sides remain finite but the values are "
                              "symbolic; compared numerically instead")
            return out
        scale = max(abs(v1), abs(v2), 1e-30)
        if abs(v1 - v2) <= _TOL * scale:
            return out
        out.update(verdict="mismatch", severity="error",
                   message=(f"as {sym.name} -> {_point_label(point)}, the two "
                            f"sides approach different finite limits "
                            f"({v1:.6g} vs {v2:.6g})"))
        return out

    if {kl, kr} == {"finite", "divergent"}:
        bad, good = ("lhs", "rhs") if kl == "divergent" else ("rhs", "lhs")
        out.update(verdict="mismatch", severity="error",
                   message=(f"as {sym.name} -> {_point_label(point)}, the {bad} "
                            f"diverges while the {good} stays finite"))
        return out

    if kl == "divergent" and kr == "divergent":
        try:
            ratio = sp.limit(sp.together(lhs / rhs), sym, point)
            r = _classify(ratio)
            out["ratio_limit"] = r
            if r["kind"] == "finite":
                v = r.get("value")
                if v is not None and abs(v - 1.0) <= 1e-6 * max(abs(v), 1.0):
                    return out
                out.update(verdict="mismatch", severity="error",
                           message=(f"both sides diverge as {sym.name} -> "
                                    f"{_point_label(point)}, but their ratio "
                                    f"tends to {v} instead of 1"))
            else:
                out["verdict"] = "inconclusive"
                out["severity"] = "info"
                out["message"] = ("both sides diverge and the ratio limit could "
                                  "not be resolved")
        except Exception:
            out["verdict"] = "inconclusive"
            out["severity"] = "info"
            out["message"] = "both sides diverge; ratio limit not computable"
        return out

    if kl == "conditional" and kr == "conditional":
        a, b = ll.get("expr"), lr.get("expr")
        if a is not None and b is not None:
            try:
                d = sp.simplify(a - b)
                if getattr(d, "is_zero", False) is True:
                    return out
                out.update(verdict="mismatch", severity="error",
                           message=(f"as {sym.name} -> {_point_label(point)}, "
                                    f"the two sides tend to different "
                                    f"expressions (difference `{sp.sstr(d)}`)"))
                return out
            except Exception:
                pass
        out.update(verdict="inconclusive", severity="info",
                   message=(f"as {sym.name} -> {_point_label(point)}, both sides "
                            f"tend to symbolic expressions that could not be "
                            f"compared"))
        return out

    if {kl, kr} == {"conditional", "finite"}:
        # Compare the conditional side against the finite one numerically is not
        # meaningful; report as inconclusive rather than inventing a verdict.
        out.update(verdict="inconclusive", severity="info",
                   message=(f"as {sym.name} -> {_point_label(point)}, one side "
                            f"tends to a symbolic expression and the other to a "
                            f"number; compare them with the numeric check"))
        return out

    if "undefined" in (kl, kr):
        out.update(verdict="inconclusive", severity="warning",
                   message=(f"the limit as {sym.name} -> {_point_label(point)} "
                            f"is undefined on at least one side"))
        return out

    out.update(verdict="inconclusive", severity="warning",
               message=(f"the limit as {sym.name} -> {_point_label(point)} does "
                        f"not settle ({kl} / {kr})"))
    return out


def find_singularities(expr, symbols, max_ops: int = 200) -> dict:
    """Where does a denominator vanish? Reported as information, not as error."""
    out: dict[str, list[str]] = {}
    if sp.count_ops(expr) > max_ops:
        return out
    try:
        den = sp.fraction(sp.cancel(sp.together(expr)))[1]
    except Exception:
        return out
    if den == 1:
        return out
    for s in symbols:
        if s not in den.free_symbols:
            continue
        try:
            roots = sp.solve(sp.Eq(den, 0), s)
        except Exception:
            continue
        if roots:
            out[s.name] = [sp.sstr(r) for r in roots[:6]]
    return out


def enumerate_limits(lhs, rhs=None, symbols=None, critical: list[str] | None = None,
                     positive: set[str] | None = None) -> dict:
    """Enumerate limit cases for an identity, or for a single expression."""
    positive = positive or set()
    symbols = list(symbols) if symbols is not None else sorted(
        set(lhs.free_symbols) | (set(rhs.free_symbols) if rhs is not None else set()),
        key=lambda s: s.name)

    extra: dict[str, list] = {}
    for item in (critical or []):
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        try:
            extra.setdefault(name.strip(), []).append(sp.sympify(value.strip()))
        except Exception:
            continue

    # Automatic singularity enumeration. Testing only 0 and +-oo walks straight
    # past the pole at x = 1 in something like 1/(1-x**2), which is exactly
    # where a wrong partial fraction falls apart, so poles found on either side
    # are added to the list of points to probe.
    sources = [lhs] if rhs is None else [lhs, rhs]
    for expr in sources:
        for name, points in find_singularities(expr, symbols).items():
            for point in points[:3]:
                try:
                    value = sp.sympify(point)
                except Exception:
                    continue
                bucket = extra.setdefault(name, [])
                if not any(sp.simplify(value - existing) == 0
                           for existing in bucket):
                    bucket.append(value)

    checks: list[dict] = []
    skipped: list[str] = []
    is_identity = rhs is not None

    for s in symbols:
        pts: list = [sp.Integer(0), sp.oo]
        if s.name not in positive:
            pts.append(-sp.oo)
        pts.extend(extra.get(s.name, []))
        for pt in pts:
            if len(checks) >= _MAX_CHECKS:
                skipped.append(f"{s.name} -> {_point_label(pt)}")
                continue
            ll = _limit(lhs, s, pt, s.name in positive)
            entry = {"symbol": s.name, "point": _point_label(pt)}
            if is_identity:
                lr = _limit(rhs, s, pt, s.name in positive)
                entry.update(_compare(ll, lr, lhs, rhs, s, pt))
                entry.pop("lhs", None)
                entry.pop("rhs", None)
                entry["lhs_limit"] = ll
                entry["rhs_limit"] = lr
            else:
                entry["limit"] = ll
                entry["verdict"] = "pass"
                entry["severity"] = ("info" if ll["kind"] == "divergent"
                                     else "info")
                entry["message"] = None
            checks.append(entry)

    errors = [c for c in checks if c.get("severity") == "error"]
    warnings = [c for c in checks if c.get("severity") == "warning"]
    if errors:
        status = "fail"
    elif warnings:
        status = "warning"
    else:
        status = "pass"

    return {
        "status": status,
        "mode": "identity" if is_identity else "expression",
        "checks": checks,
        "n_checks": len(checks),
        "n_errors": len(errors),
        "skipped": skipped,
        "singularities": (find_singularities(lhs, symbols)
                          if not is_identity else {}),
    }
