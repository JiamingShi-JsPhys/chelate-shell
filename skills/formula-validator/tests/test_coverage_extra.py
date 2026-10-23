"""Extra coverage tests for the formula-validator core.

These exercise the internal branches that the CLI/subprocess tests do not reach
(the numeric-probe fallback in limits, the symbolic verdict branches, the LaTeX
fallback converter, and report rendering of real error outputs) so the whole
package stays above the 80% coverage bar set by the skill standard.
"""

import sympy as sp

from scripts.core import pipeline
from scripts.core import symbolic
from scripts.core import report
from scripts.core.limits import (
    _classify,
    _numeric_probe,
    _compare,
    find_singularities,
    enumerate_limits,
)
from scripts.core.parsing import parse_expr, parse_equation, ParseError
from scripts.core.errors import ParseError as _ErrorsParseError

x = sp.Symbol("x")
y = sp.Symbol("y")


# --------------------------------------------------------------------------
# limits._classify branches
# --------------------------------------------------------------------------

def test_classify_none():
    assert _classify(None)["kind"] == "indeterminate"


def test_classify_accumbounds():
    assert _classify(sp.AccumBounds(0, 1))["kind"] == "oscillating"


def test_classify_nan():
    assert _classify(sp.nan)["kind"] == "undefined"


def test_classify_infinite():
    out = _classify(sp.oo)
    assert out["kind"] == "divergent"
    assert "oo" in out["detail"]


def test_classify_conditional():
    out = _classify(y)
    assert out["kind"] == "conditional"
    assert out["expr"] == y


def test_classify_finite_value():
    out = _classify(sp.Integer(5))
    assert out["kind"] == "finite"
    assert out["value"] == 5.0


# --------------------------------------------------------------------------
# limits._numeric_probe fallback (the subprocess tests never hit this)
# --------------------------------------------------------------------------

def test_numeric_probe_divergent():
    out = _numeric_probe(sp.exp(x), x, sp.oo, False)
    assert out["kind"] == "divergent"


def test_numeric_probe_oscillating():
    out = _numeric_probe(sp.sin(x), x, sp.oo, False)
    assert out["kind"] == "oscillating"


def test_numeric_probe_finite_zero():
    out = _numeric_probe(sp.exp(x), x, -sp.oo, False)
    assert out["kind"] == "finite"
    assert out["value"] == 0.0


def test_numeric_probe_compile_failure():
    # symbol to probe is not in the expression -> compiler fails -> indeterminate
    out = _numeric_probe(x, y, sp.oo, False)
    assert out["kind"] == "indeterminate"


# --------------------------------------------------------------------------
# limits._compare branches
# --------------------------------------------------------------------------

def test_compare_finite_mismatch():
    out = _compare({"kind": "finite", "value": 1.0},
                   {"kind": "finite", "value": 2.0}, x, x, x, 0)
    assert out["verdict"] == "mismatch"
    assert out["severity"] == "error"


def test_compare_finite_unknown_values():
    out = _compare({"kind": "finite"}, {"kind": "finite"}, x, x, x, 0)
    assert out["verdict"] == "inconclusive"


def test_compare_finite_vs_divergent():
    out = _compare({"kind": "finite", "value": 1.0},
                   {"kind": "divergent"}, x, x, x, 0)
    assert out["verdict"] == "mismatch"


def test_compare_divergent_ratio_pass():
    out = _compare({"kind": "divergent"}, {"kind": "divergent"},
                   x, x, x, sp.oo)
    assert out["verdict"] == "pass"


def test_compare_divergent_ratio_mismatch():
    out = _compare({"kind": "divergent"}, {"kind": "divergent"},
                   x, 2 * x, x, sp.oo)
    assert out["verdict"] == "mismatch"


def test_compare_divergent_ratio_inconclusive():
    out = _compare({"kind": "divergent"}, {"kind": "divergent"},
                   x, sp.sqrt(x), x, sp.oo)
    assert out["verdict"] == "inconclusive"


def test_compare_conditional_equal():
    out = _compare({"kind": "conditional", "expr": x},
                   {"kind": "conditional", "expr": x}, x, x, x, 0)
    assert out["verdict"] == "pass"


def test_compare_conditional_not_equal():
    out = _compare({"kind": "conditional", "expr": x},
                   {"kind": "conditional", "expr": x + 1}, x, x, x, 0)
    assert out["verdict"] == "mismatch"


def test_compare_conditional_vs_finite():
    out = _compare({"kind": "conditional", "expr": x},
                   {"kind": "finite", "value": 1.0}, x, x, x, 0)
    assert out["verdict"] == "inconclusive"


def test_compare_undefined():
    out = _compare({"kind": "undefined"}, {"kind": "finite", "value": 1.0},
                   x, x, x, 0)
    assert out["verdict"] == "inconclusive"
    assert out["severity"] == "warning"


def test_compare_default_warning():
    out = _compare({"kind": "weird"}, {"kind": "other"}, x, x, x, 0)
    assert out["verdict"] == "inconclusive"
    assert out["severity"] == "warning"


# --------------------------------------------------------------------------
# limits.find_singularities / enumerate_limits
# --------------------------------------------------------------------------

def test_find_singularities_denominator():
    out = find_singularities(1 / (1 - x ** 2), [x])
    assert out.get("x") == ["-1", "1"]


def test_find_singularities_constant():
    assert find_singularities(sp.Integer(5), [x]) == {}


def test_find_singularities_maxops():
    assert find_singularities(1 / (1 - x ** 2), [x], max_ops=1) == {}


def test_enumerate_expression_mode():
    res = enumerate_limits(1 / (1 - x ** 2), symbols=[x])
    assert res["mode"] == "expression"
    assert res["singularities"].get("x") == ["-1", "1"]
    assert res["n_checks"] >= 1


def test_enumerate_identity_mismatch():
    res = enumerate_limits(x, x + 1, symbols=[x])
    assert res["mode"] == "identity"
    assert res["status"] == "fail"


def test_enumerate_critical_param():
    res = enumerate_limits(x, 2 * x, symbols=[x], critical=["x=1"])
    assert res["mode"] == "identity"
    assert res["n_checks"] >= 1


# --------------------------------------------------------------------------
# symbolic branches
# --------------------------------------------------------------------------

def test_prove_matrix_zero():
    M = sp.Matrix([[0, 0], [0, 0]])
    assert symbolic.prove_identity(M, M)["status"] == "proven"


def test_prove_disproven_with_point():
    out = symbolic.prove_identity(x, x + 1, point={"x": 2.0})
    assert out["status"] == "disproven"


def test_prove_unresolved_no_point():
    out = symbolic.prove_identity(sp.sin(x), x, point=None)
    assert out["status"] == "unresolved"


def test_prove_high_precision_agrees():
    # sqrt(x^2) - x does not simplify to 0 but agrees numerically for x > 0
    out = symbolic.prove_identity(sp.sqrt(x ** 2), x, point={"x": 2.0})
    assert out["high_precision_agrees"] is True
    assert out["status"] == "unresolved"


def test_high_precision_empty_point():
    assert symbolic.high_precision_check(x, {}) is None


# --------------------------------------------------------------------------
# parsing LaTeX-fallback branches
# --------------------------------------------------------------------------

def test_parse_sqrt():
    expr, strat = parse_expr(r"\sqrt{x}")
    assert strat == "latex-fallback"
    assert sp.simplify(expr - sp.sqrt(x)) == 0


def test_parse_sqrt_root():
    expr, _ = parse_expr(r"\sqrt[3]{x}")
    assert sp.simplify(expr - x ** sp.Rational(1, 3)) == 0


def test_parse_partial_derivative():
    expr, _ = parse_expr(r"\frac{\partial f}{\partial x}")
    assert isinstance(expr, sp.Derivative)


def test_parse_pmatrix():
    expr, _ = parse_expr(r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}")
    assert isinstance(expr, sp.Matrix)


def test_parse_array_env():
    expr, _ = parse_expr(r"\begin{array}{cc} a & b \\ c & d \end{array}")
    assert isinstance(expr, sp.Matrix)


def test_parse_style_wrap():
    for tex in (r"\hat{x}", r"\bar{y}", r"\overline{z}", r"\mathrm{E}"):
        expr, strat = parse_expr(tex)
        assert strat == "latex-fallback"


def test_parse_greek():
    expr, _ = parse_expr(r"\alpha x")
    assert sp.Symbol("alpha") in expr.free_symbols


def test_parse_infty():
    expr, strat = parse_expr(r"x \cdot \infty")
    assert strat == "latex-fallback"
    assert expr == sp.oo * x


def test_parse_binops():
    for tex in (r"a \times b", r"a \div b", r"a \pm b",
                r"\langle a \rangle", r"A^{T}", r"\top", r"\nabla f",
                r"\left( x \right)"):
        expr, strat = parse_expr(tex)
        assert strat == "latex-fallback"


def test_parse_ln_is_known_limitation():
    # \ln emits the `log` function; juxtaposing it with its argument yields an
    # invalid `log*x`, so bare \ln is rejected. This documents the limitation
    # and still exercises the \ln branch in the converter.
    try:
        parse_expr(r"\ln x")
        assert False, "expected ParseError for bare \\ln"
    except ParseError:
        pass


def test_parse_layout_and_spacing():
    expr, _ = parse_expr(r"\hspace{1cm} x")
    assert sp.Symbol("x") in expr.free_symbols
    expr2, _ = parse_expr(r"a \, b")
    assert sp.Symbol("a") in expr2.free_symbols


def test_parse_underscore_empty_out():
    expr, _ = parse_expr(r"_x")
    assert sp.Symbol("x") in expr.free_symbols


def test_parse_amp_and_newline():
    expr, _ = parse_expr(r"a & b")
    assert sp.Symbol("a") in expr.free_symbols


def test_parse_dangling_backslash():
    try:
        parse_expr("\\")
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_parse_unsupported_env():
    try:
        parse_expr(r"\begin{foo} x \end{foo}")
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_parse_unsupported_command():
    try:
        parse_expr(r"\xyz x")
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_parse_unsupported_int():
    try:
        parse_expr(r"\int_0^1 x \, dx")
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_parse_unclosed_env():
    try:
        parse_expr(r"\begin{matrix} a & b")
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_parse_bare_sum_rejected():
    try:
        parse_expr("sum_i F_ij")
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_parse_empty():
    try:
        parse_expr("")
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_parse_equation_none():
    try:
        parse_equation(None)
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_parse_equation_not_equation():
    try:
        parse_equation("notanequation")
        assert False, "expected ParseError"
    except ParseError:
        pass


def test_parse_equation_escaped_equals():
    lhs, rhs, _ = parse_equation(r"a \= b")
    assert lhs == sp.Symbol("a")
    assert rhs == sp.Symbol("b")


# --------------------------------------------------------------------------
# report rendering of real error outputs
# --------------------------------------------------------------------------

def test_render_dimension_error():
    res = pipeline.validate_equation("x = x + 1", units={"x": "m"})
    text = report.render(res)
    assert "# Formula verification report" in text
    assert "## Highlighted problems" in text
    assert res["verdict"] == "fail"


def test_render_numeric_error():
    res = pipeline.validate_equation("x**2 = 2*x", units={"x": "m"}, n=40)
    text = report.render(res)
    assert "## Highlighted problems" in text
    assert "Ratio spread" in text or "Diagnosis" in text


def test_render_pass_report():
    res = pipeline.validate_equation("E = m*c**2",
                                     units={"E": "J", "m": "kg", "c": "m/s"})
    text = report.render(res)
    assert "# Formula verification report" in text
    assert res["verdict"] in ("pass", "unknown")
