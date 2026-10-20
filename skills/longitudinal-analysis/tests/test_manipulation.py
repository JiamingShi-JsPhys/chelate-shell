"""Manipulation-check step tests (statsmodels Type-II ANOVA).

``statsmodels`` is importable in the test sandbox so the full path is
exercised end-to-end against the deterministic fixture panel.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.steps import manipulation

_FIXTURE = Path(__file__).resolve().parent / "fixture_panel.csv"


@pytest.fixture()
def df() -> pd.DataFrame:
    return pd.read_csv(_FIXTURE)


@pytest.fixture()
def cfg_obj(pipeline_config: dict, tmp_path):
    from src.config import load_config

    import yaml

    # Write to tmp_path, never next to the tracked fixtures: the config
    # embeds machine-specific tmp paths and must not dirty the repo (or
    # leak the author's username into the shipped zip).
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(pipeline_config), encoding="utf-8")
    return load_config(p)


def test_manipulation_writes_anova_csv(df, cfg_obj) -> None:
    """manipulation.run must produce a Type-II ANOVA table CSV."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = manipulation.run(
            df, {"dv": "manipulation_score", "between": ["default", "info", "cancel"]}, cfg_obj
        )
    assert out.exists()
    table = pd.read_csv(out, index_col=0)
    # statsmodels Type-II ANOVA: one row per factor + Residual.
    assert "default" in table.index
    assert "info" in table.index
    assert "cancel" in table.index
    assert "Residual" in table.index


def test_manipulation_requires_dv(df, cfg_obj) -> None:
    """manipulation.run must reject a config without 'dv'."""
    with pytest.raises(ValueError, match="dv"):
        manipulation.run(df, {"between": ["default"]}, cfg_obj)


def test_manipulation_requires_between(df, cfg_obj) -> None:
    """manipulation.run must reject a config without any 'between' factor."""
    with pytest.raises(ValueError, match="between"):
        manipulation.run(df, {"dv": "manipulation_score", "between": []}, cfg_obj)
