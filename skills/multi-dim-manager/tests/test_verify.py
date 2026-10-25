"""Tests for the MVP verifier."""

from scripts.audit import RoundRecord
from scripts.common import sha256
from scripts.verify import verify_round


def _rec(status="success", out=sha256(b"data"), exit_code=0):
    return RoundRecord(
        round_no=1, status=status, params={"a": 1},
        input_hash="i", output_hash=out, plugin_exit=exit_code,
    )


def test_verify_success():
    r = verify_round(_rec())
    assert r.passed is True
    assert "exit 0" in r.detail
    assert r.golden is False


def test_verify_no_output_file():
    r = verify_round(_rec(out=sha256(b"NO_OUTPUT")))
    assert r.passed is False
    assert "no result file" in r.detail


def test_verify_nonzero_exit():
    r = verify_round(_rec(exit_code=1))
    assert r.passed is False
    assert "exited with code 1" in r.detail


def test_verify_golden_match():
    h = sha256(b"data")
    r = verify_round(_rec(out=h), golden=h)
    assert r.golden is True
    assert r.passed is True


def test_verify_golden_mismatch():
    r = verify_round(_rec(out=sha256(b"data")), golden=sha256(b"other"))
    assert r.golden is True
    assert r.passed is False
    assert "mismatched" in r.detail
