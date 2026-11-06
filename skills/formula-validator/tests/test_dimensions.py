"""Dimensional analysis tests.

The three-state verdict (consistent / inconsistent / unknown) is the point: a
guessed dimension that produces a false error is worse than admitting that
nothing is known.
"""

from __future__ import annotations

import sympy as sp

from scripts.core.dimensions import analyse, check_equation
from scripts.core.errors import ParseError
from scripts.core.registry import UnitParseError, describe_dimension
from scripts.core.parsing import parse_equation

U = {"m": "kg", "c": "m/s", "v": "m/s", "p": "kg*m/s", "E": "J"}


def _eq(text):
    return parse_equation(text)


def test_consistent_when_both_sides_carry_energy():
    lhs, rhs, _ = _eq("E = m*c**2")
    res = check_equation(lhs, rhs, U)
    assert res["status"] == "consistent"
    assert res["lhs_text"] == res["rhs_text"]


def test_inconsistent_when_a_sum_mixes_dimensions():
    lhs, rhs, _ = _eq("p*c = m*c**2 + m*v")
    res = check_equation(lhs, rhs, U)
    assert res["status"] == "inconsistent"
    assert res["mismatch"]["message"] == "a sum mixes incompatible dimensions"


def test_inconsistent_when_the_sides_simply_differ():
    lhs, rhs, _ = _eq("m*c = m*c**2")
    res = check_equation(lhs, rhs, U)
    assert res["status"] == "inconsistent"
    assert res["mismatch"]["side"] == "both"


def test_unknown_when_no_unit_is_declared():
    lhs, rhs, _ = _eq("a*b = c")
    res = check_equation(lhs, rhs, {})
    assert res["status"] == "unknown"
    assert set(res["unknown_symbols"]) == {"a", "b", "c"}


def test_inference_is_off_by_default():
    """A guessed dimension creates false errors, so it must be opt-in."""
    lhs, rhs, _ = _eq("1/(x*(1+x)) = 1/x - 1/(1+x)")
    assert check_equation(lhs, rhs, {}, auto_infer=False)["status"] == "unknown"


def test_inference_reports_every_guess():
    lhs, rhs, _ = _eq("p = m*v")
    res = check_equation(lhs, rhs, {}, auto_infer=True)
    assert res["status"] == "consistent"
    assert "p" in res["inferred"] and "m" in res["inferred"]
    assert res["inferred"]["m"]["unit"] == "kg"


def test_transcendental_argument_must_be_dimensionless():
    lhs = sp.exp(sp.Symbol("x"))
    res = check_equation(lhs, sp.Symbol("x"), {"x": "m"})
    assert res["status"] == "inconsistent"
    assert "dimensionless" in res["mismatch"]["message"]


def test_radian_is_a_unit_not_a_sympy_function():
    """``rad`` collides with a name in SymPy's namespace; the registry must win."""
    res = analyse(sp.Symbol("theta"), {"theta": "rad"})
    assert res["status"] == "resolved"
    assert res["dimension_text"] == "dimensionless"


def test_square_root_halves_the_exponent():
    expr = sp.sqrt(sp.Symbol("A"))
    assert describe_dimension(analyse(expr, {"A": "m**2"})["dimension"]) == "length"


def test_derivative_subtracts_the_variable_dimension():
    x = sp.Symbol("x")
    expr = sp.Derivative(sp.Function("V")(x), (x, 2))
    res = analyse(expr, {"V": "J", "x": "m"})
    # J / m**2 = kg * s**-2
    assert res["dimension_text"] == "mass * time^-2"


def test_integral_adds_the_variable_dimension():
    x = sp.Symbol("x")
    expr = sp.Integral(sp.Function("rho")(x), (x, 0, 1))
    res = analyse(expr, {"rho": "kg/m", "x": "m"})
    assert res["dimension_text"] == "mass"


def test_dimensionless_symbols_are_recognised():
    lhs, rhs, _ = _eq("1 = sin(theta)**2 + cos(theta)**2")
    res = check_equation(lhs, rhs, {"theta": "rad"})
    assert res["status"] == "consistent"


def test_unit_string_parsing_accepts_products_and_powers():
    res = analyse(sp.Symbol("x"), {"x": "kg*m/s**2"})
    assert res["dimension_text"] == "mass * length * time^-2"


def test_unknown_unit_name_is_an_error_not_a_guess():
    try:
        analyse(sp.Symbol("x"), {"x": "furlong"})
    except UnitParseError as exc:
        assert "furlong" in exc.message
    else:  # pragma: no cover
        raise AssertionError("unknown unit should raise")


def test_ev_is_treated_as_energy():
    assert analyse(sp.Symbol("E"), {"E": "eV"})["dimension_text"] == \
        analyse(sp.Symbol("E"), {"E": "J"})["dimension_text"]
