"""Monte-Carlo numerical comparison of two expressions.

This is the workhorse check. It is deliberately cheap and deliberately
*comparative*: we do not try to decide whether a formula "looks reasonable",
we only ask whether lhs and rhs agree at many random points.

Sampling is log-uniform across decades rather than uniform, because a
coefficient error of the form ``2*x`` vs ``x/2`` survives uniform sampling in a
narrow range but shows up immediately when the magnitudes span several decades.

The most valuable output is not the pass/fail bit, it is ``worst_point``: the
concrete parameter values where the two sides disagree most. That is the thing
a human can act on.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Iterable

import numpy as np
import sympy as sp

from .errors import FVError

__all__ = ["monte_carlo", "sample_values", "LambdifyError"]

_TINY = 1e-300

# Compiled evaluators are cached because the same expression is compiled more
# than once per run: every intermediate of a derivation chain is compared twice
# (as the rhs of step i and the lhs of step i+1), and a long-lived MCP server
# process sees the same formulas again across calls. Compilation is the
# dominant cost of the numeric stage, so this is worth the small cache.
_COMPILE_CACHE: OrderedDict = OrderedDict()
_COMPILE_CACHE_MAX = 64

# NumPy first, SciPy only on demand - see ``_compile`` for why the order
# matters as much as it does.
_MODULES = (["numpy"], ["numpy", "scipy"], ["math"])


class LambdifyError(FVError):
    """The expression cannot be compiled to a vectorised evaluator."""

    exit_code = 2


def sort_symbols(symbols: Iterable[sp.Symbol]) -> list[sp.Symbol]:
    return sorted(set(symbols), key=lambda s: (s.name,))


def sample_values(symbols, n: int, seed: int = 0,
                  lo: float = 1e-2, hi: float = 1e2,
                  positive: set[str] | None = None,
                  ranges: dict | None = None) -> dict[str, np.ndarray]:
    """Log-uniform sample for each symbol, returned as name -> array."""
    rng = np.random.default_rng(seed)
    positive = positive or set()
    ranges = ranges or {}
    out: dict[str, np.ndarray] = {}
    for s in symbols:
        r = ranges.get(s.name)
        a, b = (float(r[0]), float(r[1])) if r else (lo, hi)
        a = max(a, 1e-12)
        expo = rng.uniform(np.log10(a), np.log10(b), n)
        mag = np.power(10.0, expo)
        if s.name in positive:
            out[s.name] = mag
        else:
            out[s.name] = mag * rng.choice([-1.0, 1.0], size=n)
    return out


def _cache_key(expr, symbols) -> tuple:
    return (sp.srepr(expr), tuple(s.name for s in symbols))


def _probe_array(f, n_symbols: int) -> bool:
    """Evaluate ``f`` once on a short array.

    ``lambdify`` resolves names it cannot translate *at call time*, not at
    compile time: ``erf`` under ``["numpy"]`` returns a function built on
    scalar ``math.erf`` and only raises ``TypeError`` when handed an array.
    A compile-time ``try/except`` therefore accepts an evaluator that cannot
    run, and the failure resurfaces later as an opaque numeric error with no
    chance to fall back. One cheap evaluation decides here instead.
    """
    probe = np.full(3, 2.0)
    try:
        with np.errstate(all="ignore"):
            out = f(*([probe] * n_symbols)) if n_symbols else f()
        np.asarray(out, dtype=np.complex128)
    except Exception:
        return False
    return True


def _probe_scalar(f, n_symbols: int) -> bool:
    """Same idea as :func:`_probe_array`, for the scalar ``math`` backend."""
    try:
        with np.errstate(all="ignore"):
            out = f(*([2.0] * n_symbols)) if n_symbols else f()
        complex(out)
    except Exception:
        return False
    return True


def _compile(expr, symbols):
    """Compile ``expr`` into a vectorised evaluator.

    Two decisions here are load-bearing:

    **NumPy is tried before SciPy.** Requesting ``["numpy", "scipy"]``
    unconditionally imports SciPy on every run, measured at 200-550 ms on a
    cold interpreter - the single largest cost inside a verification. Almost
    every formula only needs NumPy, so SciPy is now reached only for the
    handful of functions NumPy genuinely lacks (``erf``, ``gamma``,
    ``besselj``, ``zeta``), and only when the probe proves NumPy cannot
    evaluate them. The behaviour for those functions is unchanged; only the
    import is deferred.

    **A candidate is probed before it is trusted.** See :func:`_probe_array`.
    """
    key = _cache_key(expr, symbols)
    hit = _COMPILE_CACHE.get(key)
    if hit is not None:
        _COMPILE_CACHE.move_to_end(key)
        return hit

    n = len(symbols)
    for modules in _MODULES:
        try:
            f = sp.lambdify(symbols, expr, modules=modules)
        except Exception:
            continue
        if modules == ["math"]:
            if not _probe_scalar(f, n):
                continue
            vf = np.vectorize(f, otypes=[np.complex128])
            f = lambda *args, _vf=vf: _vf(*args)  # noqa: E731
        elif not _probe_array(f, n):
            continue
        _COMPILE_CACHE[key] = f
        if len(_COMPILE_CACHE) > _COMPILE_CACHE_MAX:
            _COMPILE_CACHE.popitem(last=False)
        return f

    raise LambdifyError(
        "could not compile the expression for numerical evaluation",
        hint="special functions may be unsupported; try simplifying the input")


def _evaluate(f, symbols, cols: dict[str, np.ndarray], n: int) -> np.ndarray:
    try:
        with np.errstate(all="ignore"):
            raw = f(*[cols[s.name] for s in symbols]) if symbols else f()
    except Exception as exc:
        raise LambdifyError(
            f"numerical evaluation failed: {exc}",
            hint="the expression may reference an unsupported special function") from exc
    arr = np.asarray(raw)
    if arr.shape == ():
        arr = np.full(n, complex(arr))
    return np.asarray(arr, dtype=np.complex128).reshape(n)


def _round(x, digits: int = 6):
    """Round for compact output. Complex values become [re, im]."""
    try:
        v = complex(x)
    except Exception:
        return None
    if not (np.isfinite(v.real) and np.isfinite(v.imag)):
        return None
    if abs(v.imag) <= 1e-12 * max(abs(v.real), 1.0):
        return float(f"%.{digits}g" % v.real)
    return [float(f"%.{digits}g" % v.real), float(f"%.{digits}g" % v.imag)]


def monte_carlo(lhs, rhs, symbols=None, n: int = 10000, seed: int = 0,
                tol: float = 1e-9, lo: float = 1e-2, hi: float = 1e2,
                positive: set[str] | None = None,
                ranges: dict | None = None) -> dict:
    """Compare lhs and rhs at ``n`` random points. Returns a result dict."""
    symbols = sort_symbols(
        symbols if symbols is not None
        else (set(lhs.free_symbols) | set(rhs.free_symbols)))
    result = {
        "status": "unknown", "n_samples": int(n), "n_compared": 0,
        "n_nonfinite": 0, "max_rel_error": None, "max_abs_error": None,
        "tolerance": tol, "worst_point": None, "lhs_at_worst": None,
        "rhs_at_worst": None, "ratio": None, "note": None,
    }

    cols = sample_values(symbols, n, seed=seed, lo=lo, hi=hi,
                         positive=positive, ranges=ranges)
    f_l, f_r = _compile(lhs, symbols), _compile(rhs, symbols)
    lv = _evaluate(f_l, symbols, cols, n)
    rv = _evaluate(f_r, symbols, cols, n)

    finite = np.isfinite(lv) & np.isfinite(rv)
    n_finite = int(finite.sum())
    result["n_compared"] = n_finite
    result["n_nonfinite"] = int(n) - n_finite

    if n_finite == 0:
        result["note"] = ("no sample produced a finite value on both sides; "
                          "the formula may be undefined over the sampled domain")
        return result

    fl, fr = lv[finite], rv[finite]
    abs_err = np.abs(fl - fr)
    denom = np.maximum(np.maximum(np.abs(fl), np.abs(fr)), _TINY)
    rel = abs_err / denom

    k = int(np.argmax(rel))
    result["max_rel_error"] = _round(rel[k])
    result["max_abs_error"] = _round(abs_err[k])

    point = {s.name: _round(cols[s.name][finite][k]) for s in symbols}
    result["worst_point"] = point
    result["lhs_at_worst"] = _round(fl[k])
    result["rhs_at_worst"] = _round(fr[k])

    # Ratio diagnostics: distinguishes "wrong constant factor" from
    # "wrong functional form", which is the single most useful hint we can give.
    big = np.abs(fl) > 1e-12
    if big.sum() >= 8:
        ratio = fr[big] / fl[big]
        mean = complex(np.mean(ratio))
        std = float(np.std(ratio))
        if abs(mean) > 0:
            result["ratio"] = {
                "mean": _round(abs(mean), 10),
                "spread": _round(std / abs(mean)),
                "looks_like_constant_factor": bool(
                    std / abs(mean) < 1e-6 and abs(abs(mean) - 1.0) > tol),
            }

    if n_finite < max(20, int(0.05 * n)):
        result["note"] = (f"only {n_finite} of {n} samples were finite on both "
                          "sides; narrow the sampling range to get better coverage")

    result["status"] = "pass" if float(rel[k]) <= tol else "fail"

    if result["status"] == "fail":
        # A disagreement in float64 is only a *suspicion*. Near a root the two
        # sides of a correct identity can differ by many ulps purely from
        # cancellation, so 40-digit arithmetic gets the last word.
        verdict = _hp_agree(lhs, rhs, point)
        if verdict is True:
            result["status"] = "pass"
            result["float_artifact"] = True
            result["note"] = (
                "sampled float64 values differ by up to "
                f"{result['max_rel_error']} near a cancellation point, but "
                "40-digit arithmetic at the worst point agrees; this is "
                "floating-point noise, not an algebraic error")
        elif verdict is None:
            result["note"] = ((result.get("note") or "") +
                              " high-precision cross-check was inconclusive").strip()
    return result


def _hp_agree(lhs, rhs, point, digits: int = 40):
    """True if lhs and rhs agree at ``point`` in high precision."""
    if not point or any(v is None for v in point.values()):
        return None
    try:
        from .symbolic import high_precision_check
        return high_precision_check(sp.together(lhs - rhs), point, digits)
    except Exception:
        return None
