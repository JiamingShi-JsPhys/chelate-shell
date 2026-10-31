"""Unit tests for the conflict-detector detection primitives."""

from __future__ import annotations

import pytest

from src.detect import (
    Conflict,
    detect_boolean_conflict,
    detect_categorical_mismatch,
    detect_interval_overlap,
    detect_numeric_mismatch,
)
from src.extract import Fact, extract_facts
from src.rules import pair_facts, run_detection


# ---------------------------------------------------------------------------
# detect.py
# ---------------------------------------------------------------------------

def test_detect_numeric_mismatch_flags_diff() -> None:
    from src.detect import NumericClaim

    c = detect_numeric_mismatch(
        NumericClaim(key="s", value=10.0, source="a"),
        NumericClaim(key="s", value=20.0, source="b"),
    )
    assert c is not None
    assert c.kind == "numeric_mismatch"
    assert c.level == "entity"
    assert c.detail["delta"] == 10.0


def test_detect_numeric_mismatch_accepts_within_tol() -> None:
    from src.detect import NumericClaim

    c = detect_numeric_mismatch(
        NumericClaim(key="s", value=10.0, source="a"),
        NumericClaim(key="s", value=10.000000001, source="b"),
    )
    assert c is None


def test_detect_interval_overlap_flags() -> None:
    c = detect_interval_overlap("k", 0, 5, "k", 3, 8, "a", "b")
    assert c is not None and c.kind == "interval_overlap"


def test_detect_interval_overlap_disjoint_none() -> None:
    c = detect_interval_overlap("k", 0, 2, "k", 3, 8, "a", "b")
    assert c is None


def test_detect_boolean_conflict() -> None:
    c = detect_boolean_conflict("k", True, "k", False, "a", "b")
    assert c is not None and c.kind == "boolean"
    assert detect_boolean_conflict("k", True, "k", True, "a", "b") is None


def test_detect_categorical_mismatch() -> None:
    c = detect_categorical_mismatch("k", "red", "k", "blue", "a", "b")
    assert c is not None and c.kind == "categorical"
    assert c.severity == "medium"


def test_conflict_to_dict_roundtrip() -> None:
    c = Conflict(
        level="entity",
        claim_a="x = 1",
        claim_b="x = 2",
        source_a="a",
        source_b="b",
        kind="numeric_mismatch",
    )
    d = c.to_dict()
    assert d["level"] == "entity"
    assert d["kind"] == "numeric_mismatch"
    assert d["source_a"] == "a"


# ---------------------------------------------------------------------------
# extract.py
# ---------------------------------------------------------------------------

def test_extract_from_json_dict() -> None:
    facts = extract_facts("d", '{"a": 1, "b": true}')
    keys = {f.key for f in facts}
    assert keys == {"a", "b"}
    kinds = {f.key: f.kind for f in facts}
    assert kinds["a"] == "numeric"
    assert kinds["b"] == "bool"


def test_extract_from_text_kv() -> None:
    facts = extract_facts("d", "speed: 10\nactive: true")
    d = {f.key: (f.kind, f.value) for f in facts}
    assert d["speed"] == ("numeric", 10.0)
    assert d["active"] == ("bool", True)


def test_extract_free_text() -> None:
    facts = extract_facts("d", "some free text line")
    assert len(facts) == 1
    assert facts[0].kind == "text"
    assert facts[0].key == "line"


# ---------------------------------------------------------------------------
# rules.py
# ---------------------------------------------------------------------------

def _facts(doc: str, pairs) -> list:
    return [Fact(key=k, value=v, source=doc, kind=Fact._infer_kind(v)) for k, v in pairs]


def test_pair_facts_only_cross_doc_groups() -> None:
    fb = {
        "a": _facts("a", [("k", 1), ("only_a", "x")]),
        "b": _facts("b", [("k", 2)]),
    }
    groups = pair_facts(fb, {})
    keys = [f.key for f in groups[0]]
    assert "k" in keys
    # only_a never appears (single-doc group is dropped).
    for f in groups[0]:
        assert f.key != "only_a"


def test_run_detection_numeric_and_bool() -> None:
    fb = {
        "a": _facts("a", [("speed", 10.0), ("active", True)]),
        "b": _facts("b", [("speed", 20.0), ("active", False)]),
    }
    cf = run_detection(fb, ["entity", "clause"], {}, 1e-6)
    kinds = {c.kind for c in cf}
    assert "numeric_mismatch" in kinds
    assert "boolean" in kinds


def test_run_detection_identical_no_conflict() -> None:
    fb = {
        "a": _facts("a", [("speed", 10.0)]),
        "b": _facts("b", [("speed", 10.0)]),
    }
    cf = run_detection(fb, ["entity"], {}, 1e-6)
    assert cf == []
