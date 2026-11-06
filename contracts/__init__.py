"""Chelate Shell contracts package.

Exposes the unified GateResult schema and the status / evidence-level enums so
skill scripts can do a single `from contracts import ...`.

Caller: every skill's run.py and core/router.py import this package.
No existing file in chelate-shell-v1.1.0/ serves this purpose.
User instruction: build the flat microkernel + contracts framework,
step 2 (write contracts/gate_result.py).
"""
from .gate_result import (
    GateResult,
    GateStatus,
    EvidenceLevel,
    Evidence,
    GRADE_ORDER,
    weakest,
    pass_gate,
    fail_gate,
    unverified_gate,
)

__all__ = [
    "GateResult",
    "GateStatus",
    "EvidenceLevel",
    "Evidence",
    "GRADE_ORDER",
    "weakest",
    "pass_gate",
    "fail_gate",
    "unverified_gate",
]
