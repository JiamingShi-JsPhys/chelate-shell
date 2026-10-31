"""Orchestration: run the checks in order and aggregate a verdict.

Check order is chosen so the cheapest and most decisive check runs first:

    D1 parse  ->  D2 dimension  ->  D3 limit  ->  D4 numeric  ->  D5 symbolic

Dimension is cheap and catches whole classes of error, so it gates the rest.
Symbolic proving is last because it is the slowest and because a numeric
disagreement already settles the question.

Verdict states:

* ``pass``     - every check that ran agreed.
* ``fail``     - at least one check found a disagreement.
* ``conflict`` - the dimensions disagree but the numbers agree. In practice
  this almost always means the *unit declaration* is wrong, not the formula,
  so it is surfaced as its own state instead of being folded into ``fail``.
* ``unknown``  - we abstained. Reported with the reason, never as a pass.
"""

from __future__ import annotations

import time

import sympy as sp

from . import limits as lim_mod
from . import symbolic as sym_mod
from .dimensions import check_equation
from .errors import ParseError
from .numeric import monte_carlo, sort_symbols
from .parsing import parse_equation, parse_expr

__all__ = ["validate_equation", "inspect_expression", "summarize"]


def _timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    try:
        return fn(*args, **kwargs), (time.perf_counter() - t0) * 1000.0, None
    except Exception as exc:  # a check that crashes must not kill the run
        return None, (time.perf_counter() - t0) * 1000.0, exc


def validate_equation(text: str, units: dict | None = None, n: int = 10000,
                      tol: float = 1e-9, seed: int = 0, critical: list[str] | None = None,
                      auto_infer: bool = False, positive: set[str] | None = None,
                      ranges: dict | None = None, run_symbolic: bool = True,
                      max_ops: int = 800, symbol_names=None) -> dict:
    """Validate an equation ``lhs = rhs``. Returns the full result dict."""
    result = {
        "mode": "equation",
        "input": {"text": text, "declared_units": units or {}},
        "verdict": "unknown",
        "checks": {},
        "errors": [],
        "caveats": [],
        "timing_ms": {},
    }

    # --- D1 parse -------------------------------------------------------
    parsed, t, exc = _timed(parse_equation, text, symbol_names)
    result["timing_ms"]["parse"] = round(t, 2)
    if exc is not None:
        if isinstance(exc, ParseError):
            raise exc
        raise ParseError(f"parsing failed: {exc}")
    lhs, rhs, strategy = parsed
    result["checks"]["parse"] = {
        "status": "pass", "strategy": strategy,
        "lhs": sp.sstr(lhs), "rhs": sp.sstr(rhs),
        "symbols": sorted({s.name for s in lhs.free_symbols} |
                          {s.name for s in rhs.free_symbols}),
    }
    symbols = sort_symbols(set(lhs.free_symbols) | set(rhs.free_symbols))

    # --- D2 dimension ---------------------------------------------------
    dimres, t, dexc = _timed(check_equation, lhs, rhs, units, auto_infer)
    result["timing_ms"]["dimension"] = round(t, 2)
    if dexc is not None:
        dimres = {"status": "unknown", "lhs_text": None, "rhs_text": None,
                  "mismatch": None, "unknown_symbols": [],
                  "unsupported_nodes": [], "inferred": {}}
        result["caveats"].append(
            f"the dimensional check could not run: {type(dexc).__name__}: {dexc}")
    result["checks"]["dimension"] = dimres
    if dimres["status"] == "inconsistent":
        result["errors"].append({
            "check": "dimension", "severity": "error",
            "message": dimres["mismatch"]["message"] if dimres["mismatch"]
                       else "the two sides have different dimensions",
            "evidence": dimres["mismatch"],
        })
    elif dimres["status"] == "unknown":
        result["caveats"].append(
            f"dimension not checked: no unit declared for "
            f"{', '.join(dimres['unknown_symbols'])}")
    if dimres["inferred"]:
        result["caveats"].append(
            "dimensions were guessed for: " +
            ", ".join(f"{k} -> {v['unit']}" for k, v in dimres["inferred"].items()))

    # --- bare-side detection -------------------------------------------
    # ``E = m*c**2`` is a definition, not an identity: sampling E at random and
    # comparing it with m*c**2 would report a mismatch for a perfectly correct
    # formula. Only the dimensional check is meaningful here, so the numeric
    # and symbolic checks are skipped with an explicit reason rather than
    # silently producing a false failure.
    bare_side = isinstance(lhs, sp.Symbol) or isinstance(rhs, sp.Symbol)
    result["input"]["reads_as_definition"] = bare_side
    mcres: dict = {"status": "skipped"}

    if bare_side:
        result["checks"]["limit"] = {"status": "skipped"}
        result["checks"]["numeric"] = {"status": "skipped"}
        result["checks"]["symbolic"] = {"status": "skipped"}
        result["caveats"].insert(
            0, "one side is a bare symbol, so this reads as a definition: only "
               "dimensional consistency was checked. To get the numeric and "
               "limit checks, state it as an identity between two full "
               "expressions (for example, compare two independent derivations "
               "of the same quantity).")
        complex_side = rhs if isinstance(lhs, sp.Symbol) else lhs
        sing = lim_mod.find_singularities(complex_side, symbols)
        if sing:
            result["caveats"].append(
                "denominator vanishes at: "
                + "; ".join(f"{k} = {', '.join(v)}" for k, v in sing.items()))
    else:
        # --- D3 limit ---------------------------------------------------
        # Skipped when the dimensional check already failed: the formula is
        # known broken, and piling inconclusive limit warnings on top of a
        # decisive finding only buries it.
        if dimres["status"] == "inconsistent":
            result["checks"]["limit"] = {
                "status": "skipped",
                "note": "skipped because the dimensional check already failed"}
            result["timing_ms"]["limit"] = 0.0
        else:
            limres, t, _ = _timed(lim_mod.enumerate_limits, lhs, rhs, symbols,
                                  critical, positive)
            result["timing_ms"]["limit"] = round(t, 2)
            result["checks"]["limit"] = limres
            for c in limres["checks"]:
                if c.get("severity") == "error":
                    result["errors"].append({
                        "check": "limit", "severity": "error",
                        "message": c["message"],
                        "evidence": {"symbol": c["symbol"], "point": c["point"]},
                    })
                elif c.get("severity") == "warning":
                    result["caveats"].append(
                        f"limit {c['symbol']} -> {c['point']}: {c['message']}")

        # --- D4 numeric -------------------------------------------------
        mcres, t, exc = _timed(monte_carlo, lhs, rhs, symbols, n, seed, tol,
                               1e-2, 1e2, positive, ranges)
        result["timing_ms"]["numeric"] = round(t, 2)
        if exc is not None:
            mcres = {"status": "unknown", "note": f"{exc}"}
        result["checks"]["numeric"] = mcres
        if mcres["status"] == "fail":
            result["errors"].append({
                "check": "numeric", "severity": "error",
                "message": (f"the two sides disagree at {mcres['n_compared']} "
                            f"random points; worst relative error "
                            f"{mcres['max_rel_error']} (tolerance {tol})"),
                "evidence": {
                    "worst_point": mcres["worst_point"],
                    "lhs_value": mcres["lhs_at_worst"],
                    "rhs_value": mcres["rhs_at_worst"],
                    "ratio": mcres["ratio"],
                },
            })
        elif mcres["status"] == "unknown":
            result["caveats"].append("numeric comparison could not be run: "
                                     + str(mcres.get("note")))

        # --- D5 symbolic ------------------------------------------------
        if run_symbolic and mcres["status"] != "fail":
            symres, t, _ = _timed(sym_mod.prove_identity, lhs, rhs,
                                  mcres.get("worst_point"), max_ops)
            result["timing_ms"]["symbolic"] = round(t, 2)
            result["checks"]["symbolic"] = symres
            if symres["status"] == "disproven":
                result["errors"].append({
                    "check": "symbolic", "severity": "error",
                    "message": f"symbolic difference is not zero: "
                               f"{symres['difference']}",
                    "evidence": {"difference": symres["difference"]},
                })
            elif symres["status"] == "unresolved":
                result["caveats"].append("symbolic: " + str(symres.get("note")))

    # --- aggregate ------------------------------------------------------
    failed = {e["check"] for e in result["errors"] if e["severity"] == "error"}
    if failed:
        numeric_ok = mcres["status"] == "pass"
        result["verdict"] = ("conflict"
                             if (failed == {"dimension"} and numeric_ok)
                             else "fail")
        if result["verdict"] == "conflict":
            result["caveats"].insert(
                0, "the declared units make the dimensions disagree while the "
                   "numbers agree; re-check the unit declaration before "
                   "changing the formula")
    elif mcres["status"] == "pass":
        result["verdict"] = "pass"
    else:
        result["verdict"] = "unknown"
        result["reason"] = "definition" if bare_side else "checks_inconclusive"
    result["timing_ms"]["total"] = round(sum(result["timing_ms"].values()), 2)
    return result


def inspect_expression(text: str, units: dict | None = None,
                       auto_infer: bool = False,
                       positive: set[str] | None = None,
                       symbol_names=None, expect_zero: bool = False) -> dict:
    """Analyse a single expression: its dimension, singularities, limits.

    When ``expect_zero`` is set the caller asserts the expression is an
    identity equal to zero (a residual such as ``m*q''(t) + k*q(t)`` written
    without the ``= 0``). The symbolic prover then runs: ``proven`` upgrades an
    otherwise-``unknown`` verdict to ``pass`` (a symbolic identity does not need
    units), ``disproven`` is a real failure, and ``unresolved`` abstains rather
    than guesses. An expression that is zero only *conditional* on a solution or
    a parametrisation is reported honestly as not-identically-zero.
    """
    expr, strategy = parse_expr(text, symbol_names)
    from .dimensions import analyse
    from .numeric import sort_symbols as _ss
    symbols = _ss(expr.free_symbols)
    result = {
        "mode": "expression",
        "input": {"text": text, "declared_units": units or {}},
        "checks": {
            "parse": {"status": "pass", "strategy": strategy,
                      "expr": sp.sstr(expr)},
            "dimension": analyse(expr, units, auto_infer),
            "limit": lim_mod.enumerate_limits(expr, None, symbols, None, positive),
        },
        "errors": [], "caveats": [], "verdict": "pass",
    }
    dimres = result["checks"]["dimension"]
    if dimres["status"] == "inconsistent":
        result["errors"].append({
            "check": "dimension", "severity": "error",
            "message": dimres["mismatch"]["message"] if dimres["mismatch"]
                       else "inconsistent",
            "evidence": dimres["mismatch"]})
        result["verdict"] = "fail"
    elif dimres["status"] == "unknown":
        result["caveats"].append(
            "dimension not checked: no unit declared for "
            + ", ".join(dimres["unknown_symbols"]))
        result["verdict"] = "unknown"
    if dimres["inferred"]:
        result["caveats"].append(
            "dimensions were guessed for: "
            + ", ".join(f"{k} -> {v['unit']}" for k, v in dimres["inferred"].items()))
    sing = result["checks"]["limit"].get("singularities") or {}
    if sing:
        result["caveats"].append(
            "denominator vanishes at: "
            + "; ".join(f"{k} = {', '.join(v)}" for k, v in sing.items()))

    if expect_zero:
        # A numeric witness lets the prover also *disprove* a non-identity:
        # an expression that disagrees with zero at a random point is not
        # identically zero, and the high-precision check confirms it.
        witness = None
        if symbols:
            mc, _, _ = _timed(monte_carlo, expr, sp.Integer(0), symbols, 200,
                              0, 1e-9, 1e-2, 1e2, positive, None)
            if mc.get("status") == "fail":
                witness = mc.get("worst_point")
        symres = sym_mod.prove_identity(expr, sp.Integer(0), witness)
        result["checks"]["symbolic"] = symres
        if symres["status"] == "proven":
            if result["verdict"] not in ("fail", "conflict"):
                result["verdict"] = "pass"
            result["caveats"].append(
                "expect-zero: the expression is symbolically zero, so it is an "
                "identity regardless of any undeclared units")
        elif symres["status"] == "disproven":
            result["errors"].append({
                "check": "symbolic", "severity": "error",
                "message": (f"expect-zero: the expression is not zero; "
                             f"difference: {symres['difference']}"),
                "evidence": {"difference": symres["difference"]},
            })
            result["verdict"] = "fail"
        else:  # unresolved: the simplifier gave up, abstain
            result["caveats"].append(
                "expect-zero: the symbolic check could not prove the expression "
                "is identically zero - the difference did not simplify to zero "
                "and no high-precision cross-check confirmed a mismatch, so the "
                "verdict stays as the dimensional check left it")
    return result


def summarize(result: dict, report_path: str | None = None) -> dict:
    """Compact view for an agent to read. This is what enters the context."""
    out = {
        "verdict": result["verdict"],
        "mode": result.get("mode"),
        "failed_checks": sorted({e["check"] for e in result["errors"]
                                 if e["severity"] == "error"}),
        "first_error": result["errors"][0]["message"] if result["errors"] else None,
        "caveat_count": len(result["caveats"]),
    }
    numeric = result.get("checks", {}).get("numeric")
    if numeric:
        out["worst_point"] = numeric.get("worst_point")
        out["max_rel_error"] = numeric.get("max_rel_error")
    sym = result.get("checks", {}).get("symbolic")
    if sym and sym.get("status") == "disproven":
        out["difference"] = sym.get("difference")
    bp = result.get("breakpoint")
    if bp and bp.get("first_break"):
        fb = bp["first_break"]
        out["breakpoint"] = {
            "step": fb["step"],
            "diagnosis": (fb.get("diagnosis") or {}).get("diagnosis"),
            "summary": (fb.get("diagnosis") or {}).get("summary"),
            "worst_point": fb.get("worst_point"),
        }
    if report_path:
        out["report"] = report_path
    return out
