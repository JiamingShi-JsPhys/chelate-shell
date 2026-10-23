"""Chelate Shell contracts — unified gate-result schema (single source of truth).

Caller: every skill's root-level `run.py` imports this module and writes a
        GateResult to `process/gates/<skill>_<ts>.json`; `core/router.py`
        reads these files back to adjudicate the pipeline.
No existing file in chelate-shell-v1.1.0/ serves this purpose (the old
contract/ layer lived in chelate-shell-v1.0.0/ and is not reused).
Data schemas:
    Reads:  none (pure definition module).
    Writes: GateResult JSON -> process/gates/<skill>_<ts>.json, schema:
            {skill, status, evidence_level, reason, artifacts, timestamp}
User instruction: v1.1.0 blueprint section 2 — the output contract that all
        gates-stage skills MUST return:
        {"skill": ..., "status": "PASS|FAIL|UNVERIFIED",
         "evidence_level": "EXACT|SYMBOLIC|EMPIRICAL|UNVERIFIED",
         "reason": ..., "artifacts": [...]}

Design: pure stdlib, no third-party dependencies, so the contract layer itself
stays zero-friction.

Fields:
    skill:           emitting skill name (e.g. "formula-validator").
    status:          PASS | FAIL | UNVERIFIED.  (WARN was merged into
                     UNVERIFIED: a warning is not a hard block, and the
                     router only terminates on FAIL.)
    evidence_level:  EXACT (deterministic proof / exact match) |
                     SYMBOLIC (CAS-level symbolic reasoning) |
                     EMPIRICAL (numeric sampling / statistical) |
                     UNVERIFIED (degraded, dependency missing, skipped).
    reason:          human-readable explanation of the verdict.
    artifacts:       output paths this gate produced (relative to the
                     workspace root when possible).
    timestamp:       UTC ISO-8601 timestamp.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"


class EvidenceLevel(str, Enum):
    EXACT = "EXACT"
    SYMBOLIC = "SYMBOLIC"
    EMPIRICAL = "EMPIRICAL"
    UNVERIFIED = "UNVERIFIED"


# Backwards-compatible alias for the evidence-level enum.
Evidence = EvidenceLevel

GRADE_ORDER = {
    EvidenceLevel.EXACT: 0,
    EvidenceLevel.SYMBOLIC: 1,
    EvidenceLevel.EMPIRICAL: 2,
    EvidenceLevel.UNVERIFIED: 3,
}


def weakest(grades: List[EvidenceLevel]) -> EvidenceLevel:
    """Return the weakest (least trusted) evidence level in the list."""
    if not grades:
        return EvidenceLevel.UNVERIFIED
    return max(grades, key=lambda g: GRADE_ORDER[g])


@dataclass
class GateResult:
    skill: str
    status: GateStatus
    evidence_level: EvidenceLevel
    reason: str = ""
    artifacts: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["evidence_level"] = self.evidence_level.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GateResult":
        return cls(
            skill=d["skill"],
            status=GateStatus(d["status"]),
            evidence_level=EvidenceLevel(d["evidence_level"]),
            reason=d.get("reason", ""),
            artifacts=list(d.get("artifacts", [])),
            timestamp=d.get("timestamp", ""),
        )

    def to_json(self, path: Optional[str] = None) -> str:
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        if path:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    @classmethod
    def from_json(cls, path: str) -> "GateResult":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pass_gate(skill: str, evidence_level: EvidenceLevel = EvidenceLevel.EXACT,
              reason: str = "", artifacts: Optional[List[str]] = None,
              ts: str = "") -> GateResult:
    return GateResult(skill=skill, status=GateStatus.PASS,
                      evidence_level=evidence_level, reason=reason,
                      artifacts=artifacts or [], timestamp=ts or _now())


def fail_gate(skill: str, evidence_level: EvidenceLevel = EvidenceLevel.EXACT,
              reason: str = "", artifacts: Optional[List[str]] = None,
              ts: str = "") -> GateResult:
    return GateResult(skill=skill, status=GateStatus.FAIL,
                      evidence_level=evidence_level, reason=reason,
                      artifacts=artifacts or [], timestamp=ts or _now())


def unverified_gate(skill: str, reason: str = "",
                    artifacts: Optional[List[str]] = None,
                    ts: str = "") -> GateResult:
    return GateResult(skill=skill, status=GateStatus.UNVERIFIED,
                      evidence_level=EvidenceLevel.UNVERIFIED, reason=reason,
                      artifacts=artifacts or [], timestamp=ts or _now())
