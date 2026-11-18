"""Contract tests: contracts/gate_result.py GateResult structure."""
from __future__ import annotations

import json

from contracts import (EvidenceLevel, GateResult, GateStatus, fail_gate,
                       pass_gate, unverified_gate, weakest)


def test_gate_result_fields_and_roundtrip():
    g = fail_gate("reference-auditor", EvidenceLevel.EXACT,
                  reason="DOI 10.9999/fake not found",
                  artifacts=["process/gates/x.json"])
    d = g.to_dict()
    # blueprint section 2 field set (+ timestamp), plus the two provenance
    # fields v1.3.6 added: which bytes the gate judged, and which code judged
    # them.  They are what makes a PASS expire when either one changes.
    assert set(d) == {"skill", "status", "evidence_level", "reason",
                      "artifacts", "timestamp", "inputs", "provenance"}
    assert d["inputs"] == {} and d["provenance"] == {}
    assert d["skill"] == "reference-auditor"
    assert d["status"] == "FAIL"
    assert d["evidence_level"] == "EXACT"
    assert GateResult.from_dict(d) == g
    # JSON string round trip
    assert GateResult.from_dict(json.loads(json.dumps(d))) == g


def test_gate_provenance_roundtrip():
    g = pass_gate("formula-validator", EvidenceLevel.SYMBOLIC)
    g.inputs = {"material/initial/model.py": "a" * 64}
    g.provenance = {"skill_version": "1.3.6", "skill_digest": "b" * 32,
                    "gate_contract": 2}
    back = GateResult.from_dict(json.loads(json.dumps(g.to_dict())))
    assert back == g
    # A gate written by an older version has neither field and must still
    # load: the router reports those as unbound rather than rejecting them.
    old = {"skill": "x", "status": "PASS", "evidence_level": "EXACT"}
    legacy = GateResult.from_dict(old)
    assert legacy.inputs == {} and legacy.provenance == {}


def test_status_and_evidence_enums():
    assert [s.value for s in GateStatus] == ["PASS", "FAIL", "UNVERIFIED"]
    assert [e.value for e in EvidenceLevel] == [
        "EXACT", "SYMBOLIC", "EMPIRICAL", "UNVERIFIED"]
    # WARN is folded into UNVERIFIED — only FAIL hard-blocks
    assert GateStatus("UNVERIFIED").value == "UNVERIFIED"
    assert not hasattr(GateStatus, "WARN")


def test_weakest_evidence():
    order = [EvidenceLevel.EXACT, EvidenceLevel.SYMBOLIC,
             EvidenceLevel.EMPIRICAL, EvidenceLevel.UNVERIFIED]
    assert weakest(order) == EvidenceLevel.UNVERIFIED
    assert weakest([EvidenceLevel.EXACT, EvidenceLevel.SYMBOLIC]) \
        == EvidenceLevel.SYMBOLIC
    assert weakest([EvidenceLevel.EXACT]) == EvidenceLevel.EXACT


def test_helpers():
    assert pass_gate("formula-validator", EvidenceLevel.SYMBOLIC).status \
        == GateStatus.PASS
    assert unverified_gate("video-tracker", "fft inconclusive").status \
        == GateStatus.UNVERIFIED
    bad = fail_gate("data-profiler", EvidenceLevel.EMPIRICAL)
    assert bad.status == GateStatus.FAIL and bad.artifacts == []
