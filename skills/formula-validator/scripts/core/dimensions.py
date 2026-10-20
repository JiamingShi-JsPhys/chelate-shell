"""Dimensional analysis over the seven SI base dimensions.

The checker walks the SymPy expression tree and propagates a dimension
vector. Three outcomes are possible, and all three are first-class:

* ``consistent``  - both sides resolve to the same dimension vector.
* ``inconsistent``- they differ, or a sum mixes dimensions. This is a finding.
* ``unknown``     - some symbol has no declared unit and no hint. We abstain
  rather than guess, because a guessed dimension would produce a fake pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import sympy as sp
from sympy.core.function import AppliedUndef

from .errors import DimensionError
from .registry import (SYMBOL_HINTS, UNIT_REGISTRY, ZERO, UnitParseError,
                       describe_dimension)

__all__ = ["check_equation", "analyse", "UnitParseError"]

_TRANSCENDENTAL = (sp.exp, sp.log)
_TRIG = (sp.sin, sp.cos, sp.tan, sp.cot, sp.sec, sp.csc,
         sp.asin, sp.acos, sp.atan, sp.acot, sp.asec, sp.acsc,
         sp.sinh, sp.cosh, sp.tanh, sp.coth)
_TRANSPARENT = (sp.Abs, sp.conjugate, sp.re, sp.im, sp.sign, sp.floor,
                sp.ceiling)


@dataclass
class _Ctx:
    resolve: Callable[[str], Optional[tuple]]
    unknown: set = field(default_factory=set)
    unsupported: set = field(default_factory=set)


def _rationalize(value) -> Optional[sp.Rational]:
    try:
        r = sp.nsimplify(value, rational=True)
        return r if r.is_Rational else None
    except Exception:
        return None


def _walk(expr, ctx: _Ctx) -> Optional[tuple]:
    """Return a dimension vector, or None when it cannot be determined."""
    # Only numeric *atoms* are dimensionless. A bare ``expr.is_number`` is wrong
    # here: SymPy reports Integral(rho(x), (x, 0, 1)).is_number as True because
    # the limits are numeric, which would make every definite integral collapse
    # to "dimensionless".
    if getattr(expr, "is_Atom", False) and expr.is_number:
        return ZERO

    if isinstance(expr, sp.Symbol):
        d = ctx.resolve(expr.name)
        if d is None:
            ctx.unknown.add(expr.name)
        return d

    if isinstance(expr, sp.Add):
        vecs = [_walk(a, ctx) for a in expr.args]
        if any(v is None for v in vecs):
            return None
        if len(set(vecs)) > 1:
            raise DimensionError(
                "a sum mixes incompatible dimensions",
                terms=[describe_dimension(v) for v in vecs],
                expression=sp.sstr(expr))
        return vecs[0]

    if isinstance(expr, sp.Mul):
        vecs = [_walk(a, ctx) for a in expr.args]
        if any(v is None for v in vecs):
            return None
        total = list(ZERO)
        for v in vecs:
            for i, p in enumerate(v):
                total[i] += p
        return tuple(total)

    if isinstance(expr, sp.Pow):
        base = _walk(expr.args[0], ctx)
        expo = expr.args[1]
        if expo.is_number:
            r = _rationalize(expo)
            if r is None or base is None:
                return None
            return tuple(sp.Rational(p) * r for p in base)
        ed = _walk(expo, ctx)
        if base is None or ed is None:
            return None
        if ed != ZERO:
            raise DimensionError(
                "an exponent carries a physical dimension",
                terms=[describe_dimension(ed)],
                expression=sp.sstr(expr))
        return ZERO if base == ZERO else None

    if isinstance(expr, sp.Derivative):
        d = _walk(expr.args[0], ctx)
        for spec in expr.args[1:]:
            if isinstance(spec, sp.Tuple) and len(spec) >= 1:
                var, order = spec[0], spec[1] if len(spec) > 1 else 1
            else:
                var, order = spec, 1
            if not isinstance(var, sp.Symbol):
                return None
            vd = _walk(var, ctx)
            if d is None or vd is None:
                return None
            try:
                n = int(order)
            except Exception:
                return None
            d = tuple(a - n * b for a, b in zip(d, vd))
        return d

    if isinstance(expr, sp.Integral):
        d = _walk(expr.args[0], ctx)
        for lim in expr.args[1:]:
            if not isinstance(lim, sp.Tuple) or len(lim) == 0:
                return None
            var = lim[0]
            if not isinstance(var, sp.Symbol):
                return None
            vd = _walk(var, ctx)
            if d is None or vd is None:
                return None
            d = tuple(a + b for a, b in zip(d, vd))
        return d

    if isinstance(expr, (sp.Sum, sp.Product)):
        return _walk(expr.args[0], ctx)

    if isinstance(expr, AppliedUndef):
        d = ctx.resolve(expr.func.name)
        if d is None:
            ctx.unknown.add(f"{expr.func.name}(...)")
        return d

    if getattr(expr, "is_Matrix", False):
        vecs = [_walk(e, ctx) for e in expr]
        if any(v is None for v in vecs):
            return None
        if len(set(vecs)) > 1:
            raise DimensionError(
                "matrix entries have different dimensions",
                terms=[describe_dimension(v) for v in vecs],
                expression=sp.sstr(expr))
        return vecs[0]

    if isinstance(expr, sp.Piecewise):
        vecs = [_walk(e, ctx) for e, _ in expr.args]
        if any(v is None for v in vecs):
            return None
        if len(set(vecs)) > 1:
            raise DimensionError(
                "piecewise branches have different dimensions",
                terms=[describe_dimension(v) for v in vecs],
                expression=sp.sstr(expr))
        return vecs[0]

    if isinstance(expr, _TRANSCENDENTAL + _TRIG):
        ad = _walk(expr.args[0], ctx)
        if ad is None:
            return None
        if ad != ZERO:
            kind = "transcendental" if isinstance(expr, _TRANSCENDENTAL) else "trigonometric"
            raise DimensionError(
                f"argument of a {kind} function is not dimensionless",
                terms=[describe_dimension(ad)],
                expression=sp.sstr(expr))
        return ZERO

    if isinstance(expr, _TRANSPARENT):
        return _walk(expr.args[0], ctx)

    ctx.unsupported.add(type(expr).__name__)
    return None


def _dim_of_unit_string(text: str) -> tuple:
    """Parse a unit expression such as ``kg*m/s**2`` into a dimension vector."""
    cleaned = str(text).strip().replace("^", "**")
    if not cleaned:
        raise UnitParseError("empty unit declaration", text=text)
    # Unit names are forced to plain symbols before parsing. Several of them
    # collide with SymPy's own namespace - ``rad`` resolves to a function - and
    # a collision here silently changes what the declaration means.
    forced = {name: sp.Symbol(name) for name in UNIT_REGISTRY}
    try:
        e = sp.sympify(cleaned, rational=True, locals=forced)
    except Exception as exc:
        raise UnitParseError(
            f"cannot read the unit '{text}'",
            text=text,
            hint="write products with * and powers with **, e.g. kg*m/s**2") from exc
    ctx = _Ctx(resolve=lambda name: UNIT_REGISTRY.get(name))
    try:
        vec = _walk(e, ctx)
    except DimensionError as exc:
        raise UnitParseError(f"the unit '{text}' is not coherent: {exc.message}",
                             text=text) from exc
    if vec is None:
        raise UnitParseError(
            f"the unit '{text}' contains an unknown unit name",
            text=text,
            unknown=sorted(ctx.unknown),
            hint="known unit names: " + ", ".join(sorted(UNIT_REGISTRY)))
    return vec


def _build_resolver(expr, declared: dict, auto_infer: bool,
                    inferred: dict) -> tuple[Callable[[str], Optional[tuple]], set]:
    """Return (resolver, unresolved_names)."""
    table: dict[str, tuple] = {}
    for name, unit_text in (declared or {}).items():
        table[str(name).strip()] = _dim_of_unit_string(unit_text)

    if auto_infer:
        for sym in _collect_names(expr):
            if sym in table or sym in SYMBOL_HINTS:
                continue
        for sym in _collect_names(expr):
            if sym in table:
                continue
            hint = SYMBOL_HINTS.get(sym)
            if hint:
                unit_text, note = hint
                table[sym] = _dim_of_unit_string(unit_text)
                inferred[sym] = {"unit": unit_text, "note": note}

    unresolved = {s for s in _collect_names(expr) if s not in table}
    return (lambda name: table.get(name)), unresolved


def _collect_names(expr) -> list[str]:
    names: list[str] = []
    for s in getattr(expr, "free_symbols", set()):
        names.append(s.name)
    for f in getattr(expr, "atoms", lambda *a: set())(AppliedUndef):
        names.append(f.func.name)
    return names


def analyse(expr, declared_units: dict | None = None,
            auto_infer: bool = False) -> dict:
    """Dimension one expression. Returns a result dict (see :func:`check_equation`)."""
    inferred: dict = {}
    resolve, unresolved = _build_resolver(expr, declared_units, auto_infer,
                                          inferred)
    ctx = _Ctx(resolve=resolve)
    try:
        vec = _walk(expr, ctx)
    except DimensionError as exc:
        return {
            "status": "inconsistent",
            "dimension": None,
            "dimension_text": None,
            "mismatch": {"message": exc.message,
                         "expression": exc.detail.get("expression"),
                         "term_dimensions": exc.terms},
            "unknown_symbols": sorted(ctx.unknown),
            "unsupported_nodes": sorted(ctx.unsupported),
            "inferred": inferred,
        }
    return {
        "status": "unknown" if vec is None else "resolved",
        "dimension": list(vec) if vec is not None else None,
        "dimension_text": describe_dimension(vec),
        "mismatch": None,
        "unknown_symbols": sorted(ctx.unknown | unresolved),
        "unsupported_nodes": sorted(ctx.unsupported),
        "inferred": inferred,
    }


def check_equation(lhs, rhs, declared_units: dict | None = None,
                   auto_infer: bool = False) -> dict:
    """Compare the dimensions of both sides of an equation."""
    inferred: dict = {}
    resolve, unresolved = _build_resolver(
        sp.Mul(lhs, rhs, evaluate=False), declared_units, auto_infer, inferred)
    ctx = _Ctx(resolve=resolve)
    out = {
        "status": "unknown",
        "lhs": None, "rhs": None,
        "lhs_text": None, "rhs_text": None,
        "mismatch": None,
        "unknown_symbols": [],
        "unsupported_nodes": [],
        "inferred": inferred,
    }
    for side, key in ((lhs, "lhs"), (rhs, "rhs")):
        try:
            vec = _walk(side, ctx)
        except DimensionError as exc:
            out["status"] = "inconsistent"
            out["mismatch"] = {
                "side": key,
                "message": exc.message,
                "expression": exc.detail.get("expression"),
                "term_dimensions": exc.terms,
            }
            vec = None
        out[key] = list(vec) if vec is not None else None
        out[f"{key}_text"] = describe_dimension(vec)

    if out["status"] != "inconsistent":
        if out["lhs"] is None or out["rhs"] is None:
            out["status"] = "unknown"
        elif out["lhs"] == out["rhs"]:
            out["status"] = "consistent"
        else:
            out["status"] = "inconsistent"
            out["mismatch"] = {
                "side": "both",
                "message": "left and right hand sides have different dimensions",
                "expression": None,
                "term_dimensions": [out["lhs_text"], out["rhs_text"]],
            }

    out["unknown_symbols"] = sorted(ctx.unknown | unresolved)
    out["unsupported_nodes"] = sorted(ctx.unsupported)
    return out
