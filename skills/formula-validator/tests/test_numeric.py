"""Monte-Carlo comparison tests.

The pass/fail bit is the easy part. What matters here is that the numeric check
does not cry wolf: floating-point cancellation near a root must not be reported
as an algebraic error, and a genuine coefficient error must be.
"""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest
import sympy as sp

from conftest import ROOT
from scripts.core import numeric, parsing
from scripts.core.numeric import monte_carlo, sample_values, sort_symbols
from scripts.core.parsing import parse_equation

a, b, x, y = sp.symbols("a b x y")


def _mc(lhs_text, rhs_text, **kw):
    lhs, rhs, _ = parse_equation(f"{lhs_text} = {rhs_text}")
    return monte_carlo(lhs, rhs, **kw)


def test_identical_expressions_pass():
    res = _mc("x**2 + 2*x*y + y**2", "(x + y)**2")
    assert res["status"] == "pass"
    assert res["n_compared"] > 9000


def test_partial_fractions_pass():
    res = _mc("1/(x*(1+x))", "1/x - 1/(1+x)")
    assert res["status"] == "pass"


def test_coefficient_error_is_caught():
    res = _mc("(x + y)**2", "2*(x + y)**2")
    assert res["status"] == "fail"
    assert res["ratio"]["looks_like_constant_factor"] is True
    assert abs(res["ratio"]["mean"] - 2.0) < 1e-6


def test_sign_error_is_caught_with_a_reported_point():
    res = _mc("sin(x)**2 + cos(x)**2", "-1")
    assert res["status"] == "fail"
    assert res["worst_point"] and "x" in res["worst_point"]


def test_cancellation_near_a_root_is_not_an_error():
    """x**2+2x+1 and (x+1)**2 are identical but differ by ulps near x = -1."""
    res = _mc("x**2 + 2*x + 1", "(x + 1)**2")
    assert res["status"] == "pass", (
        "float noise near a double root must not be reported as an error")
    assert res.get("float_artifact") is True


def test_sampling_spans_several_decades():
    cols = sample_values([a, b], 2000, seed=1)
    magnitudes = abs(cols["a"])
    assert magnitudes.min() < 0.05 and magnitudes.max() > 20.0


def test_positive_symbols_are_never_negative():
    cols = sample_values([a], 500, seed=2, positive={"a"})
    assert (cols["a"] > 0).all()


def test_seed_makes_the_run_reproducible():
    one = _mc("(x + y)**2", "x**2 + 2*x*y + y**2", seed=7)
    two = _mc("(x + y)**2", "x**2 + 2*x*y + y**2", seed=7)
    assert one["max_rel_error"] == two["max_rel_error"]


def test_complex_results_are_compared():
    res = _mc("exp(I*x)", "cos(x) + I*sin(x)")
    assert res["status"] == "pass"


def test_undefined_region_is_reported_not_hidden():
    res = _mc("log(x)", "log(-x)", positive={"x"})
    assert res["n_nonfinite"] > 0


def test_symbols_are_sorted_for_determinism():
    assert [s.name for s in sort_symbols([sp.Symbol("b"), sp.Symbol("a")])] == ["a", "b"]


class TestCompileStrategy:
    """The SciPy import is the single largest cost inside a verification.

    It used to be paid on every run because ``["numpy", "scipy"]`` was the
    first module set tried. Now NumPy is tried first and SciPy is reached
    only for the functions NumPy genuinely lacks. These tests pin both halves
    of that: SciPy must stay out of a plain run, and ``erf`` must still work.
    """

    def test_a_plain_formula_does_not_import_scipy(self):
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "from scripts.core import numeric, parsing\n"
            "expr, _ = parsing.parse_expr('1/(1-x**2)')\n"
            "numeric._compile(expr, [__import__('sympy').Symbol('x')])\n"
            "print('scipy' in sys.modules)" % str(ROOT)
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, cwd=str(ROOT))
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip().endswith("False"), (
            "compiling a plain rational expression pulled SciPy in")

    def test_erf_still_evaluates_through_the_fallback(self):
        x = sp.Symbol("x")
        f = numeric._compile(sp.erf(x), [x])
        assert float(f(np.array([0.0]))[0]) == 0.0
        assert abs(float(f(np.array([2.0]))[0]) - 0.9953222650) < 1e-6

    def test_the_same_expression_is_compiled_once(self):
        x = sp.Symbol("x")
        expr, _ = parsing.parse_expr("sin(x)**2 + cos(x)**2")
        assert numeric._compile(expr, [x]) is numeric._compile(expr, [x]), (
            "the compile cache did not kick in")

    def test_the_cache_key_tracks_symbol_order(self):
        """``lambdify`` binds positionally, so order is part of the key.

        A cache keyed only on the expression and the *set* of symbol names
        would hand back ``lambda x, y`` when the caller asked for
        ``lambda y, x`` and the arguments would silently swap. This is the
        bug this test exists to prevent.
        """
        x, y = sp.Symbol("x"), sp.Symbol("y")
        expr, _ = parsing.parse_expr("x*y")
        f_xy = numeric._compile(expr, [x, y])
        f_yx = numeric._compile(expr, [y, x])
        assert f_xy is not f_yx
        # Both evaluate correctly, each against its own argument order.
        assert float(f_xy(np.array([3.0]), np.array([5.0]))[0]) == 15.0
        assert float(f_yx(np.array([3.0]), np.array([5.0]))[0]) == 15.0

    def test_an_unevaluable_expression_raises_a_typed_error(self):
        x = sp.Symbol("x")
        with pytest.raises(numeric.LambdifyError):
            numeric._compile(sp.hyper([1], [2], x), [x])
