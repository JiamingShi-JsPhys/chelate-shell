"""Shared fixtures for the longitudinal-analysis test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest

# tests/ -> skill_root
SKILL_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PANEL = SKILL_ROOT / "tests" / "fixture_panel.csv"


@pytest.fixture()
def fixture_panel_csv() -> Path:
    """Path to the deterministic 36-row panel CSV."""
    return FIXTURE_PANEL


@pytest.fixture()
def pipeline_config(tmp_path) -> Dict:
    """A minimal enabled-only pipeline config targeting tmp dirs."""
    return {
        "version": "1.0.0",
        "analysis_id": "test-pipeline",
        "data": {
            "input": str(FIXTURE_PANEL),
            "id_column": "subject_id",
            "time_column": "session",
            "condition_columns": ["default", "info", "cancel"],
        },
        "steps": [
            {"name": "descriptive", "type": "descriptive",
             "config": {"group_by": ["default", "session"], "dv": ["pain", "willingness"]}},
        ],
        "outputs": {
            "tables": str(tmp_path / "tables"),
            "figures": str(tmp_path / "figures"),
            "logs": str(tmp_path / "logs"),
        },
        "seed": 42,
    }
