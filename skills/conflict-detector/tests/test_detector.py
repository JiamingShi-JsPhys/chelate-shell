"""Unit tests for the detector orchestrator, reporter, and normaliser."""

from __future__ import annotations

import json
from pathlib import Path

from src.config import ConflictDetectorConfig, DocumentSource, load_config, _parse_sources
from src.detector import DetectionResult, detect_conflicts, run_config
from src.normalize import Normaliser, normalize_key, normalize_value
from src.report import render_csv, render_json, render_markdown, write_report


# ---------------------------------------------------------------------------
# normalize.py
# ---------------------------------------------------------------------------

def test_normalize_key_canonical() -> None:
    n = Normaliser({}, {})
    assert n.normalize_key("My Key") == "my_key"
    assert n.normalize_key("my-key") == "my_key"
    assert n.normalize_key("my.key") == "my_key"


def test_normalize_key_alias() -> None:
    n = Normaliser({"old_name": "new_name"}, {})
    assert n.normalize_key("old name") == "new_name"


def test_normalize_value_unit_rescale() -> None:
    n = Normaliser({}, {"km": 1000.0})
    assert n.normalize_value(5, "km") == 5000.0
    assert n.normalize_value(5, "m") == 5.0
    assert n.normalize_value("  A ") == "a"


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------

def test_load_config_missing_file(tmp_path) -> None:
    from src.config import load_config as _lc

    try:
        _lc(tmp_path / "nope.yaml")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_parse_sources_str_and_mapping() -> None:
    srcs = _parse_sources(["a.txt", {"id": "b", "kind": "text", "value": "hi"}])
    assert srcs[0].id == "doc0" and srcs[0].kind == "path"
    assert srcs[1].id == "b" and srcs[1].kind == "text"


def test_config_validate_requires_docs() -> None:
    bad = ConflictDetectorConfig(
        version="1.0.0", run_id="r", documents=[], levels=["entity"]
    )
    try:
        bad.validate()
        assert False, "expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# detector.py
# ---------------------------------------------------------------------------

def test_detect_conflicts_empty_docs() -> None:
    cf = detect_conflicts({}, ["entity"], {})
    assert cf == []


def test_detect_conflicts_multi_doc() -> None:
    docs = {
        "a": '{"x": 1}',
        "b": '{"x": 2}',
    }
    cf = detect_conflicts(docs, ["entity"], {})
    assert len(cf) == 1
    assert cf[0].kind == "numeric_mismatch"


def test_run_config_end_to_end(tmp_path) -> None:
    cfg = ConflictDetectorConfig(
        version="1.0.0",
        run_id="e2e",
        documents=[
            DocumentSource(id="a", kind="text", value='{"x": 1}'),
            DocumentSource(id="b", kind="text", value='{"x": 2}'),
        ],
        levels=["entity"],
        output_dir=str(tmp_path / "out"),
    )
    result = run_config(cfg, fmt="json,csv,md")
    assert result.run_id == "e2e"
    assert result.counts.get("entity", 0) == 1
    out = tmp_path / "out"
    assert (out / "conflicts_e2e.json").exists()
    assert (out / "conflicts_e2e.csv").exists()
    assert (out / "conflicts_e2e.md").exists()
    data = json.loads((out / "conflicts_e2e.json").read_text())
    assert len(data) == 1


# ---------------------------------------------------------------------------
# report.py
# ---------------------------------------------------------------------------

def test_report_render_json_roundtrip() -> None:
    from src.detect import Conflict

    c = Conflict(
        level="entity",
        claim_a="x=1",
        claim_b="x=2",
        source_a="a",
        source_b="b",
        kind="numeric_mismatch",
    )
    s = render_json([c])
    parsed = json.loads(s)
    assert parsed[0]["kind"] == "numeric_mismatch"


def test_report_render_csv_quoting() -> None:
    from src.detect import Conflict

    c = Conflict(
        level="clause",
        claim_a='say "hello"',
        claim_b='say "world"',
        source_a="a",
        source_b="b",
        kind="categorical",
    )
    s = render_csv([c])
    # Quoting must escape the embedded quotes.
    assert '"""hello"""' in s or '"say ""hello"""' in s


def test_report_markdown_no_conflicts() -> None:
    s = render_markdown([], run_id="r")
    assert "No conflicts" in s


def test_write_report_unknown_format(tmp_path) -> None:
    try:
        write_report([], tmp_path, fmt="bogus")
        assert False, "expected ValueError"
    except ValueError:
        pass
