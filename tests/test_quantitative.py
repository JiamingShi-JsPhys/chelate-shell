"""quantitative-validator skill tests: graceful degradation, the pure
atom-conservation grammar, the rdkit-backed real path, and the CLI gate.

The engine is loaded directly from the skill's scripts/ directory (via
importlib, under a unique module name) so it never collides on sys.path.
The formula/equation grammar is pure Python, so its correctness is proven
here without rdkit; the rdkit-backed verdict path is exercised when (and only
when) rdkit is importable (``pytest.importorskip``), and the missing-dependency
degradation is proven unconditionally.
"""
from __future__ import annotations

import builtins
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, SKILLS_DIR

QV_SCRIPTS = SKILLS_DIR / "quantitative-validator" / "scripts"
QV_RUN = SKILLS_DIR / "quantitative-validator" / "scripts" / "run.py"


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "quantitative_validator_engine", QV_SCRIPTS / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _block_import(name):
    """Return a fake builtins.__import__ that raises ImportError for `name`."""
    original = builtins.__import__

    def fake(name_, *args, **kwargs):
        if name_ == name or name_.startswith(name + "."):
            raise ImportError(f"simulated: {name} not installed")
        return original(name_, *args, **kwargs)

    return fake


# ------------------------------------------------- pure grammar (no rdkit)

def test_parse_formula_basic():
    e = _load_engine()
    assert e.parse_formula("H2O") == {"H": 2, "O": 1}
    assert e.parse_formula("Ca(OH)2") == {"Ca": 1, "O": 2, "H": 2}
    assert e.parse_formula("Mg3(PO4)2") == {"Mg": 3, "P": 2, "O": 8}


def test_parse_formula_hydrate():
    e = _load_engine()
    # CuSO4 (Cu1 S1 O4) + 5 H2O (H10 O5) -> O = 9
    assert e.parse_formula("CuSO4·5H2O") == {"Cu": 1, "S": 1, "O": 9, "H": 10}


def test_parse_formula_rejects_malformed():
    e = _load_engine()
    for bad in ("H2O(", "((H)2", "@@@", ""):
        with pytest.raises(ValueError):
            e.parse_formula(bad)


def test_balance_balanced_equations():
    e = _load_engine()
    assert e.balance("2H2 + O2 -> 2H2O")["balanced"] is True
    assert e.balance("CH4 + 2 O2 -> CO2 + 2 H2O")["balanced"] is True
    assert e.balance("H2 + O2 = H2O2")["balanced"] is True  # '=' arrow


def test_balance_unbalanced_reports_diffs():
    e = _load_engine()
    b = e.balance("H2 + O2 -> H2O")
    assert b["balanced"] is False
    assert b["diffs"] == {"O": (2, 1)}


# ------------------------------------------------- graceful degradation

def test_degradation_when_rdkit_missing(monkeypatch):
    """Missing rdkit must yield UNVERIFIED with an rdkit reason, never a
    fabricated PASS/FAIL and never a crash."""
    e = _load_engine()
    monkeypatch.setattr(builtins, "__import__", _block_import("rdkit"))
    res = e.validate("H2 + O2 -> H2O")
    assert res["status"] == "UNVERIFIED"
    assert res["evidence_level"] == "UNVERIFIED"
    assert "rdkit" in res["reason"].lower()
    assert res["data"].get("rdkit") is False


def test_empty_input_is_unverified():
    e = _load_engine()
    res = e.validate("   ")
    assert res["status"] == "UNVERIFIED"


# ------------------------------------------------- rdkit-backed real path

def test_real_path_balanced_passes():
    pytest.importorskip("rdkit")
    e = _load_engine()
    res = e.validate("2H2 + O2 -> 2H2O")
    assert res["status"] == "PASS", res
    assert res["evidence_level"] == "EXACT"


def test_real_path_unbalanced_fails():
    pytest.importorskip("rdkit")
    e = _load_engine()
    res = e.validate("H2 + O2 -> H2O")
    assert res["status"] == "FAIL", res
    assert res["evidence_level"] == "EXACT"
    assert "not conserved" in res["reason"].lower()


def test_real_path_single_formula_passes():
    pytest.importorskip("rdkit")
    e = _load_engine()
    res = e.validate("Ca(OH)2")
    assert res["status"] == "PASS", res


def test_real_path_unknown_element_fails():
    pytest.importorskip("rdkit")
    e = _load_engine()
    res = e.validate("Xx2")
    assert res["status"] == "FAIL", res
    assert "unknown element" in res["reason"].lower()


# ------------------------------------------------- CLI integration

def test_cli_emits_gate_via_subprocess(tmp_path):
    """The adapter prints a gate JSON on stdout and writes it into the
    workspace (status is UNVERIFIED here because rdkit is absent, PASS/FAIL
    where rdkit is installed — either way a well-formed gate)."""
    proc = subprocess.run(
        [sys.executable, str(QV_RUN), "--root", str(tmp_path),
         "--action", "gate", "--formula", "2H2 + O2 -> 2H2O"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-500:]
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["status"] in {"PASS", "FAIL", "UNVERIFIED"}, payload
    assert payload["reason"]
    gates = sorted((tmp_path / "process" / "gates").glob(
        "quantitative-validator_*.json"))
    assert gates, "no gate written into the workspace"
    gate = json.loads(gates[-1].read_text(encoding="utf-8"))
    assert gate["skill"] == "quantitative-validator"
