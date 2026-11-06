"""Lightweight verification of a round's plugin contract outcome.

This is the MVP verifier: it confirms the plugin honoured the contract
(exit code 0 and a parseable result file were produced). Comparison against a
**golden** expected output is deferred to v0.2 and is signalled by the
``golden`` flag in the result so callers can detect the gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .audit import RoundRecord
from .common import sha256

_NO_OUTPUT = "NO_OUTPUT"


@dataclass
class VerifyResult:
    """Outcome of verifying one round."""

    round_no: int
    passed: bool
    detail: str
    golden: bool = False
    expected_hash: Optional[str] = None
    actual_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_no": self.round_no,
            "passed": self.passed,
            "detail": self.detail,
            "golden": self.golden,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
        }


def verify_round(rec: RoundRecord, golden: Optional[str] = None) -> VerifyResult:
    """Verify a single round.

    Args:
        rec: The audited round record.
        golden: Optional expected output-hash. When provided, the actual
            output hash is compared against it (v0.2 golden mechanism).

    Returns:
        A :class:`VerifyResult`.
    """
    if rec.output_hash == sha256(_NO_OUTPUT.encode()):
        return VerifyResult(
            round_no=rec.round_no,
            passed=False,
            detail="no result file was produced by the plugin",
        )
    if rec.plugin_exit != 0:
        return VerifyResult(
            round_no=rec.round_no,
            passed=False,
            detail=f"plugin exited with code {rec.plugin_exit}",
        )
    if golden is not None:
        return VerifyResult(
            round_no=rec.round_no,
            passed=rec.output_hash == golden,
            detail="golden hash comparison"
            + (" matched" if rec.output_hash == golden else " mismatched"),
            golden=True,
            expected_hash=golden,
            actual_hash=rec.output_hash,
        )
    return VerifyResult(
        round_no=rec.round_no,
        passed=True,
        detail="contract satisfied: exit 0 and result file present",
    )
