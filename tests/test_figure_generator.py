"""figure-generator skill tests: graceful degradation, PASS (PDF+PNG), and
sandbox routing of the real verdict.

The engine is loaded directly from the skill's scripts/ directory (via
importlib, under a unique module name) so the two skills' `engine.py`
modules never collide on sys.path.
"""
from __future__ import annotations

import builtins
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import REPO_ROOT, SKILLS_DIR

FIG_SCRIPTS = SKILLS_DIR / "figure-generator" / "scripts"
FIG_RUN = SKILLS_DIR / "figure-generator" / "scripts" / "run.py"


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "figure_generator_engine", FIG_SCRIPTS / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_csv(path: Path):
    rng = np.random.default_rng(3)
    n = 120
    g = rng.integers(0, 3, n)
    pd.DataFrame({
        "x": rng.normal(0, 1, n),
        "y": rng.normal(0, 1, n),
        "group": g,
    }).to_csv(path, index=False)
    return g


def _block_import(name):
    original = builtins.__import__

    def fake(name_, *args, **kwargs):
        if name_ == name or name_.startswith(name + "."):
            raise ImportError(f"simulated: {name} not installed")
        return original(name_, *args, **kwargs)

    return fake


# ----------------------------------------------------------- unit: engine

def test_degradation_when_matplotlib_missing(monkeypatch):
    engine = _load_engine()
    monkeypatch.setattr(builtins, "__import__", _block_import("matplotlib"))
    res = engine.generate("does_not_exist.csv", "scatter", "x", "y")
    assert res["status"] == "UNVERIFIED"
    assert res["reason"] == "matplotlib not installed"


def test_pass_writes_pdf_and_png(tmp_path):
    engine = _load_engine()
    csv = tmp_path / "data.csv"
    _write_csv(csv)
    out = tmp_path / "out"
    res = engine.generate(str(csv), "scatter", "x", "y", hue="group",
                          output_dir=str(out))
    assert res["status"] == "PASS", res
    arts = res["artifacts"]
    assert len(arts) == 2
    pdf, png = arts
    assert pdf.endswith(".pdf") and png.endswith(".png")
    assert Path(pdf).is_file() and Path(png).is_file()


def test_unverified_on_missing_csv(tmp_path):
    engine = _load_engine()
    res = engine.generate(str(tmp_path / "nope.csv"), "scatter", "x", "y")
    assert res["status"] == "UNVERIFIED"
    assert "dataset not found" in res["reason"]


def test_unverified_on_unsupported_chart(tmp_path):
    engine = _load_engine()
    csv = tmp_path / "data.csv"
    _write_csv(csv)
    res = engine.generate(str(csv), "pie", "x", "y")
    assert res["status"] == "UNVERIFIED"
    assert "unsupported chart" in res["reason"].lower()


# --------------------------------------------------- integration: real CLI

def test_cli_emits_gate_and_artifacts(tmp_path):
    import subprocess
    csv = tmp_path / "data.csv"
    _write_csv(csv)
    proc = subprocess.run(
        [sys.executable, str(FIG_RUN), "--root", str(tmp_path),
         "--action", "process", "--input", str(csv), "--chart", "scatter",
         "--x", "x", "--y", "y"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-500:]
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["status"] == "PASS", payload
    assert len(payload["artifacts"]) == 2


# --------------------------------------------------- integration: sandbox

def test_sandbox_routing_returns_pass_with_artifacts(tmp_path):
    from core import router
    from core.registry import load_default_registry

    csv = tmp_path / "data.csv"
    _write_csv(csv)
    rec = load_default_registry().get("figure-generator")
    assert rec is not None
    record = router.run_skill(rec, str(tmp_path), "process",
                              extra_args=["--input", str(csv), "--chart",
                                          "scatter", "--x", "x", "--y", "y"],
                              timeout=120)
    assert record["status"] == "PASS", record
    assert len(record["artifacts"]) == 2
    assert any(a.endswith(".pdf") for a in record["artifacts"])
    assert any(a.endswith(".png") for a in record["artifacts"])
