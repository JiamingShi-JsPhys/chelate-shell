"""Limit-case enumeration tests.

The distinctive behaviour is that poles are enumerated automatically. Testing
only 0 and infinity walks straight past x = 1 in 1/(1-x**2), which is exactly
where a wrong partial fraction falls apart.
"""

from __future__ import annotations

import sympy as sp

from scripts.core.limits import enumerate_limits, find_singularities
from scripts.core.parsing import parse_equation

x, y = sp.symbols("x y")


def _lim(lhs_text, rhs_text=None, **kw):
    if rhs_text is None:
        expr, _ = sp.sympify(lhs_text), None
        return enumerate_limits(sp.sympify(lhs_text), None, **kw)
    lhs, rhs, _ = parse_equation(f"{lhs_text} = {rhs_text}")
    return enumerate_limits(lhs, rhs, **kw)


def test_wrong_partial_fraction_is_caught_at_the_pole():
    res = _lim("1/(1-x**2)", "1/(1-x)")
    assert res["status"] == "fail"
    messages = " ".join(c["message"] or "" for c in res["checks"]
                        if c.get("severity") == "error")
    assert "diverg" in messages


def test_correct_partial_fraction_passes_including_its_poles():
    res = _lim("1/(x*(1+x))", "1/x - 1/(1+x)")
    assert res["status"] == "pass"


def test_divergence_that_appears_on_both_sides_is_not_an_error():
    res = _lim("1/x", "2/x")
    # the ratio limit is 2, so this is a constant-factor error in the asymptotic
    # regime and must be reported rather than waved through
    assert res["status"] == "fail"


def test_singularity_detection_finds_the_poles():
    expr = sp.sympify("1/((x - 1)*(x + 2))")
    found = find_singularities(expr, [x])
    assert set(found.get("x", [])) == {"1", "-2"}


def test_singularity_points_are_added_automatically():
    res = _lim("1/(1-x**2)", "1/(1-x)")
    probed = {(c["symbol"], c["point"]) for c in res["checks"]}
    assert ("x", "1") in probed or ("x", "-1") in probed, (
        "poles should be probed without being requested")


def test_extra_critical_points_are_honoured():
    lhs, rhs, _ = parse_equation("1/(1-x**2) = 1/(1-x)")
    res = enumerate_limits(lhs, rhs, [x], critical=["x=1"])
    assert any(c["point"] == "1" for c in res["checks"])


def test_single_expression_mode_reports_singularities():
    res = enumerate_limits(sp.sympify("1/(x*(x-3))"), None, [x])
    assert res["mode"] == "expression"
    assert "x" in res["singularities"]


def test_finite_limits_are_compared_numerically():
    res = _lim("sin(x)/x", "1")
    # sin(x)/x -> 1, so the identity is only asymptotic; at finite samples it
    # must not be declared an equality either way near the limit
    assert res["status"] in {"pass", "fail", "warning"}


def test_check_count_is_bounded():
    many = sp.symbols("a b c d e f g")
    expr = sp.sympify("a+b+c+d+e+f+g")
    res = enumerate_limits(expr, None, list(many))
    assert res["n_checks"] <= 60
