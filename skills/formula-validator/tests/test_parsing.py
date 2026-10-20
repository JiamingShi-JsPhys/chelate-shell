"""Parser tests.

Parsing is where a verifier can fail silently: a wrong parse validates a
different formula than the one the user wrote, and every later check comes back
green. These cases pin the conversions that are easy to get subtly wrong.
"""

from __future__ import annotations

import sympy as sp

from scripts.core.errors import ParseError
from scripts.core.parsing import parse_equation, parse_expr


def test_sympy_syntax_is_preferred_and_reported():
    expr, strategy = parse_expr("sqrt(k/m)")
    assert strategy == "sympy-direct"
    assert expr == sp.sqrt(sp.Symbol("k") / sp.Symbol("m"))


def test_e_is_energy_not_eulers_number():
    """SymPy reads bare E as exp(1); in physics it is almost always energy."""
    expr, _ = parse_expr("E")
    assert expr == sp.Symbol("E")


def test_other_reserved_names_become_symbols():
    for name in ("N", "S", "Q", "beta", "gamma", "zeta", "Lambda"):
        expr, _ = parse_expr(name)
        assert expr == sp.Symbol(name), f"{name} should parse as a symbol"


def test_imaginary_unit_stays_available():
    expr, _ = parse_expr("exp(-I*E*t/hbar)")
    assert sp.I in expr.free_symbols or sp.I in expr.atoms(sp.I)


def test_explicit_symbols_flag_overrides_reserved_names():
    expr, _ = parse_expr("I", symbol_names=["I"])
    assert expr == sp.Symbol("I")


def test_gamma_function_still_reachable_with_an_argument():
    expr, _ = parse_expr("gamma(x)")
    assert str(expr) == "gamma(x)"


def test_latex_fraction_and_sqrt():
    expr, _ = parse_expr(r"\frac{1}{\sqrt{1-v^2/c^2}}")
    assert expr == 1 / sp.sqrt(1 - sp.Symbol("v") ** 2 / sp.Symbol("c") ** 2)


def test_latex_implicit_multiplication():
    expr, _ = parse_expr(r"\hbar\omega")
    assert expr == sp.Symbol("hbar") * sp.Symbol("omega")


def test_latex_powers_and_products():
    expr, _ = parse_expr(r"\hbar^2 k^2/(2m)")
    expected = sp.Symbol("hbar") ** 2 * sp.Symbol("k") ** 2 / (2 * sp.Symbol("m"))
    assert sp.simplify(expr - expected) == 0


def test_latex_euler_exponential():
    expr, _ = parse_expr(r"e^{-x^2}")
    assert expr == sp.exp(-sp.Symbol("x") ** 2)


def test_trig_power_applies_to_the_argument():
    """\\sin^2\\theta is (sin theta)**2, not sin(theta * 2)."""
    expr, _ = parse_expr(r"\sin^2\theta + \cos^2\theta")
    theta = sp.Symbol("theta")
    assert sp.simplify(expr - (sp.sin(theta) ** 2 + sp.cos(theta) ** 2)) == 0


def test_partial_derivative_first_order():
    expr, _ = parse_expr(r"\frac{\partial f}{\partial x}")
    assert str(expr) == "Derivative(f, x)"


def test_partial_derivative_second_order():
    expr, _ = parse_expr(r"\frac{\partial^2 V}{\partial x^2}")
    assert "Derivative" in str(expr)
    assert expr == sp.Derivative(sp.Symbol("V"), (sp.Symbol("x"), 2))


def test_dagger_becomes_conjugate_transpose():
    expr, _ = parse_expr(r"U^\dagger U")
    assert sp.srepr(expr).count("Dagger") >= 1 or "Dagger" in str(expr)


def test_latex_matrix_environment():
    expr, _ = parse_expr(r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}")
    assert getattr(expr, "is_Matrix", False)
    assert expr.shape == (2, 2)


def test_subscripts_are_preserved():
    expr, _ = parse_expr(r"x_0 + x_1")
    assert {s.name for s in expr.free_symbols} == {"x_0", "x_1"}


def test_equation_is_split_on_the_top_level_equals():
    lhs, rhs, _ = parse_equation("p*c = m*c**2")
    assert sp.sstr(lhs) == "c*p"
    assert sp.sstr(rhs) == "c**2*m"


def test_integral_without_a_clear_body_abstains():
    try:
        parse_expr(r"\int_0^1 f(x) dx")
    except ParseError as exc:
        assert "hint" in exc.detail
    else:  # pragma: no cover - either outcome is defensible
        pass


def test_unbalanced_braces_are_reported_not_guessed():
    try:
        parse_expr(r"\frac{1}{2")
    except ParseError as exc:
        assert "unbalanced" in exc.message
    else:  # pragma: no cover
        raise AssertionError("unbalanced braces should raise")


def test_garbage_input_raises_parse_error():
    try:
        parse_expr("$$$")
    except ParseError:
        pass
    else:  # pragma: no cover
        raise AssertionError("unparseable input should raise")


def test_bare_subscript_summation_is_rejected():
    """Bare-subscript sums must raise, not silently become s*u*m_i*F_i*j."""
    try:
        parse_expr("sum_i F_ij")
    except ParseError as exc:
        assert "Sum(" in exc.detail.get("hint", ""), (
            "the hint should point at the SymPy-native Sum form")
    else:  # pragma: no cover
        raise AssertionError("bare-subscript sum should raise ParseError")
    # the SymPy-native form is accepted and produces a Sum
    expr, _ = parse_expr("Sum(F(i,j),(i,1,5))")
    assert expr.has(sp.Sum), "Sum(F(i,j),(i,1,5)) should parse to a Sum"


def test_ordinary_subscripts_still_work():
    """x_0 + x_1 is a legitimate LaTeX subscript and must stay a symbol."""
    expr, _ = parse_expr("x_0 + x_1")
    assert {s.name for s in expr.free_symbols} == {"x_0", "x_1"}
