"""pint physical-unit consistency layer for formula-validator (v1.1.0 additive).

Blueprint requirement: "formula-validator — merge pint physical-unit
validation; keep the full SymPy D3/D4/D5 dimensional and identity checks".

This module is NEW in v1.1.0 and purely additive: the legacy SymPy pipeline
(D1-D5) stays byte-for-byte intact, and this layer adds an independent
unit-algebra cross-check built on pint. Both layers must agree before an
equation passes the gate.

Design (clean-room, written against the pint/sympy public APIs):
    - An equation "lhs = rhs" is split at its top-level '=' only.
    - Each side is parsed by sympy, then its dimensionality is computed
      recursively over Symbol / Number / Mul / Add / Pow nodes.
    - Symbols resolve to pint units via the declaration map
      (e.g. {"F": "N", "m": "kg", "a": "m/s**2"}), the same NAME=UNIT pairs
      the legacy CLI accepts through --units.
    - Undeclared symbols make the check "unknown" (never a false failure —
      a wrong guess would produce a false dimensional error).
    - pass: both sides defined and dimensionally equal.
      fail: both sides defined and dimensionally different (or an addition
            of mismatched dimensions inside one side).
      unknown: anything else (functions, undeclared symbols, parse failure).
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

__all__ = ["check_equation_units", "expression_dimensionality",
           "format_dimensionality"]

_UNIT_CACHE: Dict[str, object] = {}


def _registry():
    import pint
    return pint.UnitRegistry()


def _split_sides(text: str) -> Optional[Tuple[str, str]]:
    """Split 'lhs = rhs' at the top-level relational '=' only."""
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "=" and depth == 0:
            nxt = text[i + 1] if i + 1 < n else ""
            prv = text[i - 1] if i > 0 else ""
            if nxt == "=" or prv in "=!<>":
                i += 2 if nxt == "=" else 1
                continue
            lhs, rhs = text[:i].strip(), text[i + 1:].strip()
            if lhs and rhs:
                return lhs, rhs
            return None
        i += 1
    return None


def _parse(text: str):
    import sympy
    try:
        return sympy.sympify(text, rational=True)
    except Exception:
        return None


def _dims(expr, units: Dict[str, str], ureg):
    """Recursively compute the dimensionality dict of a sympy expression.

    Returns a dict, the literal "MISMATCH" (addition of unlike dimensions),
    or None (unknown).
    """
    import sympy
    if isinstance(expr, sympy.Symbol):
        unit = units.get(expr.name)
        if not unit:
            return None
        try:
            return dict(ureg.Unit(unit).dimensionality)
        except Exception:
            return None
    if isinstance(expr, sympy.Number):
        return {}
    if isinstance(expr, sympy.Pow):
        base = _dims(expr.base, units, ureg)
        if base is None:
            return None
        if base == "MISMATCH":
            return "MISMATCH"
        try:
            factor = float(expr.exp)
        except Exception:
            return None
        return {k: v * factor for k, v in base.items()}
    if isinstance(expr, sympy.Mul):
        total: Dict[str, float] = {}
        for arg in expr.args:
            d = _dims(arg, units, ureg)
            if d is None:
                return None
            if d == "MISMATCH":
                return "MISMATCH"
            for k, v in d.items():
                total[k] = total.get(k, 0.0) + v
        return {k: v for k, v in total.items() if abs(v) > 1e-12}
    if isinstance(expr, sympy.Add):
        dims = [_dims(a, units, ureg) for a in expr.args]
        if any(d is None for d in dims):
            return None
        if any(d == "MISMATCH" for d in dims):
            return "MISMATCH"
        first = dims[0]
        for d in dims[1:]:
            if not _same(d, first):
                return "MISMATCH"
        return first
    return None


def _same(a, b) -> bool:
    if (a in (None, "MISMATCH")) or (b in (None, "MISMATCH")):
        return False
    keys = set(a) | set(b)
    return all(abs(a.get(k, 0.0) - b.get(k, 0.0)) < 1e-9 for k in keys)


def format_dimensionality(dims) -> str:
    if dims is None:
        return "unknown"
    if dims == "MISMATCH":
        return "MISMATCH"
    if not dims:
        return "dimensionless"
    num, den = [], []
    for k, v in sorted(dims.items()):
        if v > 0:
            num.append(k if abs(v - 1) < 1e-9 else f"{k}^{v:g}")
        else:
            den.append(k if abs(v + 1) < 1e-9 else f"{k}^{-v:g}")
    out = "*".join(num) if num else "1"
    if den:
        out += "/" + "*".join(den)
    return out


def expression_dimensionality(text: str,
                              units: Optional[Dict[str, str]] = None) -> dict:
    """Dimensionality of a single expression (the legacy `check` counterpart)."""
    units = units or {}
    expr = _parse(text)
    if expr is None:
        return {"status": "unknown", "reason": f"cannot parse: {text!r}"}
    dims = _dims(expr, units, _registry())
    if dims is None:
        return {"status": "unknown",
                "reason": "undeclared symbols or unsupported construct"}
    if dims == "MISMATCH":
        return {"status": "fail",
                "reason": "addition/subtraction of unlike dimensions"}
    return {"status": "pass", "dimensionality": format_dimensionality(dims),
            "dims": dims}


def check_equation_units(text: str,
                         units: Optional[Dict[str, str]] = None) -> dict:
    """Check that both sides of 'lhs = rhs' carry identical dimensions."""
    units = units or {}
    sides = _split_sides(text)
    if sides is None:
        return {"status": "unknown",
                "reason": "no top-level '=' relation found"}
    lhs_text, rhs_text = sides
    lhs_expr, rhs_expr = _parse(lhs_text), _parse(rhs_text)
    if lhs_expr is None or rhs_expr is None:
        return {"status": "unknown", "reason": "cannot parse both sides"}
    ureg = _registry()
    lhs_dims = _dims(lhs_expr, units, ureg)
    rhs_dims = _dims(rhs_expr, units, ureg)
    if lhs_dims is None or rhs_dims is None:
        return {"status": "unknown",
                "reason": "undeclared symbols or unsupported construct",
                "lhs": lhs_text, "rhs": rhs_text}
    if lhs_dims == "MISMATCH" or rhs_dims == "MISMATCH":
        return {"status": "fail",
                "reason": "addition/subtraction of unlike dimensions inside a side",
                "lhs": format_dimensionality(lhs_dims),
                "rhs": format_dimensionality(rhs_dims)}
    if _same(lhs_dims, rhs_dims):
        return {"status": "pass",
                "lhs": format_dimensionality(lhs_dims),
                "rhs": format_dimensionality(rhs_dims),
                "reason": "dimensions agree on both sides"}
    return {"status": "fail",
            "lhs": format_dimensionality(lhs_dims),
            "rhs": format_dimensionality(rhs_dims),
            "reason": ("dimensional mismatch: LHS [%s], RHS [%s]"
                       % (format_dimensionality(lhs_dims),
                          format_dimensionality(rhs_dims)))}
