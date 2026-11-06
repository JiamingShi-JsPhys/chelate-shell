"""D5 symbolic identity tests.

D5 is the strongest check in the pipeline and the only one that can return a
proof rather than evidence, so it is tested directly here rather than only
through the end-to-end path.

The three-way verdict is the contract: ``proven`` means a tactic drove the
difference to exactly zero, ``disproven`` means the difference is real and
high-precision arithmetic confirms it, and ``unresolved`` means the
simplifier gave up. Collapsing ``unresolved`` into either of the other two
would be a correctness bug, and every test below guards one of those edges.
"""

from __future__ import annotations

import sympy as sp

from scripts.core.symbolic import high_precision_check, prove_identity

x, y, a, b, t = sp.symbols("x y a b t")


def _pi(lhs, rhs, point=None, max_ops=800):
    return prove_identity(lhs, rhs, point, max_ops)


class TestProven:
    """Identities that a tactic must close."""

    def test_partial_fractions(self):
        r = _pi(1 / (x * (1 + x)), 1 / x - 1 / (1 + x))
        assert r["status"] == "proven"
        assert r["difference"] == "0"

    def test_trig_identity(self):
        r = _pi(sp.sin(x) ** 2 + sp.cos(x) ** 2, 1)
        assert r["status"] == "proven"

    def test_power_rule(self):
        r = _pi((x ** 2) ** 3, x ** 6)
        assert r["status"] == "proven"

    def test_expansion(self):
        r = _pi((x + y) ** 2, x ** 2 + 2 * x * y + y ** 2)
        assert r["status"] == "proven"

    def test_a_tactic_is_named(self):
        r = _pi(1 / (x * (1 + x)), 1 / x - 1 / (1 + x))
        assert r["tactic"], "a proven result must name the tactic that closed it"

    def test_eulers_identity(self):
        r = _pi(sp.exp(sp.I * x), sp.cos(x) + sp.I * sp.sin(x))
        assert r["status"] == "proven"


class TestDisproven:
    """Wrong formulas, where the difference is real."""

    def test_wrong_coefficient(self):
        # A point is required for the confirming arithmetic: without one the
        # stage must abstain rather than guess that the difference is real.
        r = _pi(x ** 2 + 2 * x + 1, (x + 1) ** 3, point={"x": 1.0})
        assert r["status"] == "disproven"
        assert r["high_precision_agrees"] is False

    def test_wrong_partial_fractions(self):
        # At x = 2 the two sides differ by 2/3 - far outside float64 noise.
        r = _pi(1 / (1 - x ** 2), 1 / (1 - x), point={"x": 2.0})
        assert r["status"] == "disproven"

    def test_dimensionally_wrong_but_symbolically_checkable(self):
        # Same symbols, so D5 can act; the numbers are simply different.
        r = _pi(a * b, a * b + a, point={"a": 1.0, "b": 1.0})
        assert r["status"] == "disproven"

    def test_without_a_point_the_stage_abstains(self):
        # This is the honest-degradation rule: a difference that will not
        # simplify is only a *suspicion* until arithmetic confirms it.
        r = _pi(x ** 2 + 2 * x + 1, (x + 1) ** 3, point=None)
        assert r["status"] == "unresolved"
        assert r["high_precision_agrees"] is None


class TestUnresolved:
    """The simplifier giving up must never read as a wrong formula."""

    def test_a_constant_difference_that_is_actually_zero_is_proven(self):
        # Guard against the opposite failure: something genuinely zero must
        # not be reported as unresolved just because a tactic failed.
        r = _pi(sp.together(1 / x + 1 / (x + 1)), sp.together((2 * x + 1) / (x * (x + 1))))
        assert r["status"] == "proven"

    def test_no_point_means_no_high_precision_verdict(self):
        r = _pi(sp.sin(x) * sp.sin(x), sp.sin(x ** 2), point=None)
        assert r["status"] == "unresolved"
        assert r["high_precision_agrees"] is None

    def test_unresolved_carries_a_reason(self):
        r = _pi(sp.log(x ** 2), 2 * sp.log(x), point=None)
        assert r["status"] in ("unresolved", "proven")
        if r["status"] == "unresolved":
            assert r["note"], "unresolved must explain why"


class TestHighPrecisionCheck:
    def test_zero_at_a_point(self):
        assert high_precision_check(x - 1, {"x": 1}) is True

    def test_nonzero_at_a_point(self):
        assert high_precision_check(x - 1, {"x": 1.5}) is False

    def test_no_point_is_inconclusive(self):
        assert high_precision_check(x - 1, None) is None

    def test_a_missing_variable_is_inconclusive(self):
        assert high_precision_check(x + y - 1, {"x": 1}) is None

    def test_complex_argument_is_handled(self):
        assert high_precision_check(sp.exp(sp.I * x) - sp.cos(x) - sp.I * sp.sin(x),
                                    {"x": 2}) is True


class TestDegradation:
    """The stage must never raise, whatever it is handed."""

    def test_an_unprintable_difference_does_not_crash(self):
        # A difference that cannot be stringified must degrade, not raise.
        r = _pi(sp.Matrix([[x, 0]]), sp.Matrix([[0, 0]]))
        assert r["status"] in ("proven", "disproven", "unresolved")

    def test_a_max_ops_limit_is_respected(self):
        big = sum(sp.Symbol(f"z{i}") for i in range(30))
        r = _pi(big, big + x, point={"x": 2.0}, max_ops=5)
        assert r["status"] in ("unresolved", "disproven")

    def test_a_tiny_max_ops_still_returns_a_verdict(self):
        r = _pi(x + 1, x + 2, point={"x": 1.0}, max_ops=1)
        assert r["status"] == "disproven"
