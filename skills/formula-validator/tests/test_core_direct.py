"""Direct in-process unit tests for the core engine.

The subprocess-driven suite covers behaviour end-to-end; these tests lock the
individual engine functions (parsing, dimensions, limits, symbolic proving,
matrix properties, breakpoint location, report rendering) so their branches are
actually measured and regressions are localised.
"""

from __future__ import annotations

import sympy as sp

import pytest

from scripts.core import breakpoint as bp_mod
from scripts.core import dimensions as dim_mod
from scripts.core import limits as lim_mod
from scripts.core import matrixprops
from scripts.core import parsing
from scripts.core import pipeline
from scripts.core import report
from scripts.core import symbolic as sym_mod
from scripts.core.parsing import ParseError

x, y, z, a = sp.symbols("x y z a")
m = sp.Symbol("m")


# --- parsing ----------------------------------------------------------------

def test_parse_expr_sympy_direct():
    expr, strat = parsing.parse_expr("x**2 + sin(x)")
    assert strat == "sympy-direct"
    assert expr == x**2 + sp.sin(x)


def test_parse_equation_splits():
    lhs, rhs, strat = parsing.parse_equation("a = b")
    assert lhs == sp.Symbol("a")
    assert rhs == sp.Symbol("b")


def test_parse_latex_frac():
    expr, strat = parsing.parse_expr(r"\frac{1}{2} x")
    assert strat == "latex-fallback"
    assert expr == sp.Rational(1, 2) * x


def test_parse_latex_sqrt():
    expr, _ = parsing.parse_expr(r"\sqrt{x}")
    assert expr == sp.sqrt(x)


def test_parse_latex_pmatrix():
    expr, _ = parsing.parse_expr(r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}")
    assert getattr(expr, "is_Matrix", False)
    assert expr.shape == (2, 2)


def test_parse_rejects_bare_subscript_summation():
    with pytest.raises(ParseError):
        parsing.parse_expr("sum_i F_ij")


def test_parse_rejects_empty():
    with pytest.raises(ParseError):
        parsing.parse_expr("")


def test_parse_rejects_unbalanced_braces():
    with pytest.raises(ParseError):
        parsing.parse_expr("x + { unbalanced")


# --- dimensions -------------------------------------------------------------

def test_dimensions_consistent():
    out = dim_mod.check_equation(x, x, {"x": "m"}, False)
    assert out["status"] == "consistent"


def test_dimensions_inconsistent_between_sides():
    out = dim_mod.check_equation(x, y, {"x": "m", "y": "s"}, False)
    assert out["status"] == "inconsistent"


def test_dimensions_unknown_without_units():
    out = dim_mod.check_equation(x, x, {}, False)
    assert out["status"] == "unknown"
    assert "x" in out["unknown_symbols"]


def test_dimensions_sum_mixes_dims():
    out = dim_mod.check_equation(x + y, x + z,
                                 {"x": "m", "y": "s", "z": "s"}, False)
    assert out["status"] == "inconsistent"


def test_analyse_resolved():
    out = dim_mod.analyse(x, {"x": "m"}, False)
    assert out["status"] == "resolved"
    assert "length" in (out["dimension_text"] or "")


def test_analyse_unknown_without_units():
    out = dim_mod.analyse(x, {}, False)
    assert out["status"] == "unknown"


def test_analyse_transcendental_arg_must_be_dimensionless():
    # exp of a dimensioned quantity is incoherent.
    out = dim_mod.analyse(sp.exp(y), {"y": "m"}, False)
    assert out["status"] == "inconsistent"


# --- limits -----------------------------------------------------------------

def test_enumerate_limits_single_expression_passes():
    out = lim_mod.enumerate_limits(x, None, [x])
    assert out["status"] == "pass"
    assert out["singularities"] == {}


def test_enumerate_limits_finds_singularity():
    out = lim_mod.enumerate_limits(1 / (1 - x), None, [x])
    assert "x" in out["singularities"]


def test_enumerate_limits_mismatch_is_error():
    # lhs = x, rhs = x + 1 disagree at every finite point.
    out = lim_mod.enumerate_limits(x, x + 1, [x])
    assert out["status"] == "fail"
    assert any(c.get("severity") == "error" for c in out["checks"])


def test_find_singularities():
    out = lim_mod.find_singularities(1 / (x - 2), [x])
    assert out.get("x") == ["2"]


# --- symbolic ---------------------------------------------------------------

def test_prove_identity_passes():
    out = sym_mod.prove_identity(x + y, y + x)
    assert out["status"] == "proven"


def test_prove_trig_identity_passes():
    out = sym_mod.prove_identity(sp.sin(x) ** 2 + sp.cos(x) ** 2, 1)
    assert out["status"] == "proven"


def test_prove_identity_disproven_with_witness():
    # x == x + 1 is false; a witness point makes high precision confirm it.
    out = sym_mod.prove_identity(x, x + 1, point={"x": 3.0})
    assert out["status"] == "disproven"


# --- matrix properties ------------------------------------------------------

def test_matrix_hermitian_unitary_pass():
    M = sp.Matrix([[0, 1], [1, 0]])
    out = matrixprops.check_matrix(M)
    assert out["status"] == "pass"


def test_matrix_anti_hermitian():
    M = sp.Matrix([[0, 1], [-1, 0]])
    out = matrixprops.check_matrix(M, properties=["anti_hermitian"])
    assert out["status"] == "pass"


def test_matrix_symmetric():
    M = sp.Matrix([[1, 2], [2, 1]])
    out = matrixprops.check_matrix(M, properties=["symmetric"])
    assert out["status"] == "pass"


def test_matrix_traceless():
    M = sp.Matrix([[1, 0], [0, -1]])
    out = matrixprops.check_matrix(M, properties=["traceless"])
    assert out["status"] == "pass"


def test_matrix_det_unit_modulus():
    M = sp.Matrix([[1, 0], [0, 1]])
    out = matrixprops.check_matrix(M, properties=["det_unit_modulus"])
    assert out["status"] == "pass"


def test_matrix_idempotent():
    M = sp.Matrix([[1, 0], [0, 0]])
    out = matrixprops.check_matrix(M, properties=["idempotent"])
    assert out["status"] == "pass"


def test_matrix_eigenvalues_real():
    M = sp.Matrix([[2, 0], [0, 3]])
    out = matrixprops.check_matrix(M, properties=["eigenvalues_real"])
    assert out["status"] == "pass"


def test_matrix_symbolic_symmetric():
    M = sp.Matrix([[a, 0], [0, a]])
    out = matrixprops.check_matrix(M, properties=["symmetric"])
    assert out["status"] == "pass"


def test_matrix_nonunitary_fails():
    M = sp.Matrix([[1, 0], [0, 2]])
    out = matrixprops.check_matrix(M)
    assert out["status"] == "fail"
    assert "unitary" in out["failed"]


def test_matrix_unknown_property_reported():
    M = sp.Matrix([[1, 0], [0, 1]])
    out = matrixprops.check_matrix(M, properties=["bogus"])
    assert "bogus" in out["unknown_properties"]


def test_parse_matrix_wraps_bare_brackets():
    M = matrixprops.parse_matrix("[[0,1],[1,0]]")
    assert getattr(M, "is_Matrix", False)


def test_parse_matrix_rejects_scalar():
    with pytest.raises(ParseError):
        matrixprops.parse_matrix("3")


def test_parse_matrix_rejects_garbage():
    with pytest.raises(ParseError):
        matrixprops.parse_matrix("not a matrix")


# --- derivation breakpoint ---------------------------------------------------

def test_breakpoint_pass():
    out = bp_mod.locate_breakpoint([x**2 - 1, (x - 1) * (x + 1)])
    assert out["status"] == "pass"


def test_breakpoint_locates_first_break():
    out = bp_mod.locate_breakpoint([x**2, x**3])
    assert out["status"] == "fail"
    assert out["first_break"] is not None


def test_breakpoint_needs_two_steps():
    out = bp_mod.locate_breakpoint([x])
    assert out["status"] == "unknown"
    assert "note" in out


# --- report rendering --------------------------------------------------------

def test_render_pass_report():
    res = pipeline.validate_equation("1/(x*(1+x)) = 1/x - 1/(1+x)", n=100)
    text = report.render(res)
    assert "#" in text


def test_render_fail_report():
    res = pipeline.validate_equation("E = m", units={"E": "J", "m": "kg"}, n=100)
    text = report.render(res)
    assert "#" in text
    assert res["verdict"] == "fail"


def test_render_definition_report():
    res = pipeline.validate_equation(
        "E = m*c**2", units={"E": "J", "m": "kg", "c": "m/s"}, n=50)
    text = report.render(res)
    assert "#" in text
    assert res["verdict"] == "unknown"


def test_render_expect_zero_fail_report():
    res = pipeline.inspect_expression("x", expect_zero=True)
    text = report.render(res)
    assert "#" in text
    assert res["verdict"] == "fail"
