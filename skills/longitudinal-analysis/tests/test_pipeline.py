"""Unit tests for the longitudinal-analysis config loader and pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.config import AnalysisConfig, Step, load_config, VALID_STEP_TYPES
from src.pipeline import run_pipeline


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------

def test_load_config_from_yaml(tmp_path, pipeline_config: dict, fixture_panel_csv: Path):
    """load_config must parse YAML and return a validated config."""
    import yaml

    cfg_yaml = tmp_path / "cfg.yaml"
    cfg_yaml.write_text(yaml.safe_dump(pipeline_config), encoding="utf-8")
    cfg = load_config(cfg_yaml)
    assert isinstance(cfg, AnalysisConfig)
    assert cfg.analysis_id == "test-pipeline"
    assert cfg.data_input == fixture_panel_csv
    assert cfg.id_column == "subject_id"
    assert len(cfg.steps) == 1
    assert cfg.seed == 42


def test_load_config_rejects_missing_file(tmp_path):
    """A non-existent config must raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_step_validate_rejects_unknown_type():
    """Step.validate must reject unknown types."""
    bad = Step(name="x", type="not-a-real-type")
    with pytest.raises(ValueError, match="unknown type"):
        bad.validate()


def test_step_validate_rejects_empty_name():
    """Step.validate must reject an empty name."""
    bad = Step(name="", type="descriptive")
    with pytest.raises(ValueError, match="step name"):
        bad.validate()


def test_valid_step_types_cover_spec():
    """The dispatch table must know every spec step type."""
    assert {"descriptive", "anova", "lmm", "mediation", "sensitivity"} <= VALID_STEP_TYPES


def test_analysis_config_validate_rejects_missing_outputs(tmp_path):
    """Missing outputs.* keys must raise ValueError."""
    import yaml

    cfg = yaml.safe_load(
        json.dumps({
            "version": "1.0.0",
            "analysis_id": "x",
            "data": {"input": "d.csv", "id_column": "id", "time_column": "t"},
            "steps": [],
        })
    )
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ValueError, match="outputs.tables"):
        load_config(path)


# ---------------------------------------------------------------------------
# pipeline.py
# ---------------------------------------------------------------------------

def test_run_pipeline_descriptive_writes_csv(tmp_path, pipeline_config: dict, fixture_panel_csv: Path):
    """A descriptive-only pipeline must write descriptives.csv."""
    import yaml

    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(yaml.safe_dump(pipeline_config), encoding="utf-8")
    cfg = load_config(cfg_path)

    summary = run_pipeline(cfg, data_input=fixture_panel_csv)
    assert summary["analysis_id"] == "test-pipeline"
    assert summary["steps"][0]["status"] == "success"

    out = Path(pipeline_config["outputs"]["tables"]) / "descriptives.csv"
    assert out.exists()
    # Tidy format: one row per (group..., variable, statistic).
    tidy = pd.read_csv(out)
    assert set(tidy["statistic"]) == {"mean", "std", "count"}
    assert set(tidy["variable"]) == {"pain", "willingness"}


def test_run_pipeline_r_steps_skip_when_r_missing(tmp_path, pipeline_config: dict, fixture_panel_csv: Path):
    """LMM / mediation / sensitivity must skip gracefully when Rscript is absent."""
    import yaml

    cfg = dict(pipeline_config)
    cfg["steps"] = [
        {"name": "lmm", "type": "lmm",
         "config": {"formula": "willingness ~ session", "reml": True}},
    ]
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    analysis = load_config(cfg_path)

    summary = run_pipeline(analysis, data_input=fixture_panel_csv)
    rec = summary["steps"][0]
    # Rscript is not installed in the sandbox, so the step must be skipped (not crash).
    assert rec["status"] in ("skipped", "success")
    if rec["status"] == "skipped":
        assert "R unavailable" in rec.get("reason", "")


def test_run_pipeline_writes_audit_log(tmp_path, pipeline_config: dict, fixture_panel_csv: Path):
    """The pipeline must append one audit entry per enabled step."""
    import yaml

    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(yaml.safe_dump(pipeline_config), encoding="utf-8")
    cfg = load_config(cfg_path)
    run_pipeline(cfg, data_input=fixture_panel_csv)

    log = Path(pipeline_config["outputs"]["logs"]) / "analysis_log.jsonl"
    assert log.exists()
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["step"] == "descriptive"
    assert "input_hash" in entries[0] and "output_hash" in entries[0]
