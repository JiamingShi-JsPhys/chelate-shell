"""Tests for the R-backed step modules (lmm / mediation / sensitivity).

Since ``Rscript`` is not installed in the sandbox these tests exercise the
*skip path*: each module must raise :class:`RNotAvailableError` (caught by
the pipeline) when R is unavailable, and must also validate its input shape
before ever attempting to run R.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src import r_runner
from src.r_runner import RNotAvailableError
from src.steps import lmm, mediation, sensitivity

_FIXTURE = Path(__file__).resolve().parent / "fixture_panel.csv"


@pytest.fixture()
def df() -> pd.DataFrame:
    return pd.read_csv(_FIXTURE)


@pytest.fixture()
def cfg_obj(pipeline_config: dict, tmp_path):
    """A real AnalysisConfig object the step modules expect."""
    from src.config import load_config

    import yaml

    # Write to tmp_path, never next to the tracked fixtures: the config
    # embeds machine-specific tmp paths and must not dirty the repo (or
    # leak the author's username into the shipped zip).
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(pipeline_config), encoding="utf-8")
    return load_config(p)


# ---------------------------------------------------------------------------
# r_runner
# ---------------------------------------------------------------------------

def test_has_rscript_returns_bool() -> None:
    """has_rscript must return a bool (True if installed, False otherwise)."""
    assert isinstance(r_runner.has_rscript(), bool)


def test_run_r_raises_when_r_missing(tmp_path, monkeypatch) -> None:
    """run_r must raise RNotAvailableError when Rscript is absent."""
    monkeypatch.setattr(r_runner, "has_rscript", lambda: False)
    with pytest.raises(RNotAvailableError):
        r_runner.run_r(str(tmp_path / "x.R"), {"a": 1})


def test_plugin_result_to_dict() -> None:
    """PluginResult.to_dict must round-trip its fields."""
    r = r_runner.PluginResult(exit_code=0, stdout="{}", stderr="")
    d = r.to_dict()
    assert d["exit_code"] == 0
    assert d["stdout"] == "{}"
    assert d["stderr"] == ""


# ---------------------------------------------------------------------------
# steps/lmm.py
# ---------------------------------------------------------------------------

def test_lmm_requires_formula(df, cfg_obj) -> None:
    """lmm.run must reject a config without a formula."""
    with pytest.raises(ValueError, match="formula"):
        lmm.run(df, {}, cfg_obj)


def test_lmm_raises_when_r_missing(df, cfg_obj) -> None:
    """lmm.run must raise RNotAvailableError when Rscript is missing."""
    import src.steps.lmm as lmm_mod

    if not r_runner.has_rscript():
        with pytest.raises(RNotAvailableError):
            lmm_mod.run(df, {"formula": "willingness ~ session"}, cfg_obj)
    else:  # pragma: no cover - R installed path
        pass


# ---------------------------------------------------------------------------
# steps/mediation.py
# ---------------------------------------------------------------------------

def test_mediation_requires_xmy(df, cfg_obj) -> None:
    """mediation.run must reject a config missing x / m / y."""
    with pytest.raises(ValueError, match="x.*m.*y|'x'"):
        mediation.run(df, {"x": "pain"}, cfg_obj)


def test_mediation_build_lagged(df, cfg_obj) -> None:
    """The T-1 lag construction must add the expected columns."""
    out = mediation._build_lagged(df, cfg_obj, x="pain", m="pain", y="willingness", controls=[])
    for col in ("pain_t_minus_1", "willingness_t_minus_1", "pain_t", "willingness_t", "subject_mean"):
        assert col in out.columns


def test_mediation_rejects_unknown_control(df, cfg_obj) -> None:
    """mediation._build_lagged must reject an unknown control column."""
    with pytest.raises(ValueError, match="not in data"):
        mediation._build_lagged(df, cfg_obj, x="pain", m="pain", y="willingness", controls=["not_a_column"])


# ---------------------------------------------------------------------------
# steps/sensitivity.py
# ---------------------------------------------------------------------------

def test_sensitivity_sweeps_default_combos(df, cfg_obj, monkeypatch) -> None:
    """sensitivity.run must produce 4 rows (2 RE x 2 cov) and write CSV."""
    import src.steps.sensitivity as sens_mod

    def fake_run_r(script, payload, timeout=600):
        return {"aic": 1.0, "bic": 2.0}

    monkeypatch.setattr(r_runner, "run_r", fake_run_r)
    out = sens_mod.run(df, {"vary": ["random_effects", "covariance_structure"]}, cfg_obj)
    table = pd.read_csv(out)
    assert len(table) == 4
    assert set(table.columns) >= {"random_effects", "covariance", "aic", "bic"}


def test_sensitivity_single_vary_produces_2_rows(df, cfg_obj, monkeypatch) -> None:
    """A single-vary config must produce 2 rows (one per RE structure)."""
    import src.steps.sensitivity as sens_mod

    def fake_run_r(script, payload, timeout=600):
        return {"aic": 1.0, "bic": 2.0}

    monkeypatch.setattr(r_runner, "run_r", fake_run_r)
    out = sens_mod.run(df, {"vary": ["random_effects"]}, cfg_obj)
    table = pd.read_csv(out)
    assert len(table) == 2
