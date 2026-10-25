"""Matrix property checks (Hermiticity, unitarity, ...).

This module exists so that group-theoretic objects can be validated with the
same engine as scalar formulas: a representation matrix must be unitary, a
Hamiltonian must be Hermitian, and getting either wrong silently corrupts every
later step in a derivation.

Both a symbolic and a numerical verdict are produced when possible. They are
reported separately on purpose: a symbolic ``unknown`` together with a
numerical ``false`` is strong evidence of a real error, whereas a symbolic
``unknown`` alone only means the simplifier gave up.
"""

from __future__ import annotations

import numpy as np
import sympy as sp

from .errors import ParseError
from .numeric import sample_values, sort_symbols
from .parsing import parse_expr
from .symbolic import _zero_test

__all__ = ["check_matrix", "parse_matrix", "PROPERTIES"]

PROPERTIES = ("hermitian", "unitary", "anti_hermitian", "orthogonal",
              "symmetric", "traceless", "det_unit_modulus", "idempotent",
              "eigenvalues_real")

_TOL = 1e-10


def parse_matrix(text: str) -> sp.Matrix:
    raw = str(text).strip()
    if "Matrix(" not in raw and "\\begin" not in raw:
        if raw.startswith("[") and raw.endswith("]"):
            raw = "Matrix(" + raw + ")"
        else:
            raise ParseError(
                "a matrix must be given as Matrix([[...]]) or [[...]]",
                hint="example: Matrix([[0, -I], [I, 0]])")
    expr, _ = parse_expr(raw)
    if not getattr(expr, "is_Matrix", False):
        raise ParseError("the input did not parse as a matrix")
    return sp.Matrix(expr)


def _residual_text(expr) -> str | None:
    try:
        return sp.sstr(sp.simplify(expr)) if sp.count_ops(expr) <= 300 else "<too large>"
    except Exception:
        return "<unsimplifiable>"


def _numeric_zero(expr, symbols, tries: int = 24, tol: float = _TOL,
                  seed: int = 0) -> bool | None:
    if getattr(expr, "is_Matrix", False):
        entries = list(expr)
    else:
        entries = [expr]
    if not symbols:
        try:
            vals = [complex(sp.N(e)) for e in entries]
            return all(np.isfinite(v) and abs(v) <= tol for v in vals)
        except Exception:
            return None
    cols = sample_values(symbols, tries, seed=seed)
    worst = 0.0
    for k in range(tries):
        subs = {s: complex(cols[s.name][k]) for s in symbols}
        try:
            vals = [complex(sp.N(e.subs(subs))) for e in entries]
        except Exception:
            return None
        if not all(np.isfinite(v) for v in vals):
            return None
        worst = max(worst, max(abs(v) for v in vals))
    return worst <= tol


def _check_one(matrix: sp.Matrix, prop: str, symbols, max_ops: int) -> dict:
    out = {"status": "unknown", "residual": None, "numeric": None}
    try:
        if prop == "hermitian":
            residual = matrix - matrix.H
        elif prop == "unitary":
            residual = matrix.H * matrix - sp.eye(matrix.rows)
        elif prop == "anti_hermitian":
            residual = matrix + matrix.H
        elif prop == "orthogonal":
            residual = matrix.T * matrix - sp.eye(matrix.rows)
        elif prop == "symmetric":
            residual = matrix - matrix.T
        elif prop == "traceless":
            residual = sp.trace(matrix)
        elif prop == "det_unit_modulus":
            residual = sp.Abs(matrix.det()) - 1
        elif prop == "idempotent":
            residual = matrix * matrix - matrix
        elif prop == "eigenvalues_real":
            residual = None
        else:
            out["status"] = "unknown"
            out["residual"] = f"unknown property '{prop}'"
            return out
    except Exception as exc:
        out["residual"] = f"could not form the residual: {exc}"
        return out

    if prop == "eigenvalues_real":
        try:
            vals = list(matrix.eigenvals().keys())
            got = all(getattr(sp.im(sp.N(v)), "is_zero", False) or
                      abs(complex(sp.N(v)).imag) < 1e-9 for v in vals)
            out["status"] = "true" if got else "false"
        except Exception:
            out["status"] = "unknown"
        out["numeric"] = out["status"] == "true"
        return out

    if sp.count_ops(residual) <= max_ops:
        try:
            verdict = _zero_test(residual)
            out["status"] = "true" if verdict is True else "false"
        except Exception:
            out["status"] = "unknown"
        out["residual"] = _residual_text(residual)

    out["numeric"] = _numeric_zero(residual, symbols)
    if out["status"] == "unknown" and out["numeric"] is not None:
        out["status"] = "true" if out["numeric"] else "false"
    return out


def check_matrix(matrix: sp.Matrix, properties=None, max_ops: int = 400,
                 tol: float = _TOL) -> dict:
    """Check a list of properties. Default: hermitian + unitary + traceless-ish."""
    props = list(properties) if properties else ["hermitian", "unitary"]
    unknown_props = [p for p in props if p not in PROPERTIES]
    symbols = sort_symbols(matrix.free_symbols)

    checks = {p: _check_one(matrix, p, symbols, max_ops) for p in props
              if p in PROPERTIES}

    failures = [p for p, r in checks.items() if r["status"] == "false"]
    unknowns = [p for p, r in checks.items() if r["status"] == "unknown"]
    if failures:
        status = "fail"
    elif unknowns:
        status = "unknown"
    else:
        status = "pass"

    return {
        "status": status,
        "shape": [matrix.rows, matrix.cols],
        "properties": checks,
        "failed": failures,
        "unresolved": unknowns,
        "unknown_properties": unknown_props,
        "tolerance": tol,
    }
