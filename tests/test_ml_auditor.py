"""ml-auditor skill tests: graceful degradation, PASS (clean data), FAIL
(leakage), FAIL (label noise), and the CLI gate surfacing the real verdict.

The engine is loaded directly from the skill's scripts/ directory (via
importlib, under a unique module name). scikit-learn + pandas are present in
the test environment, so the real audit path is exercised here; the
missing-dependency degradation is proven by blocking the sklearn import.
"""
from __future__ import annotations

import builtins
import importlib.util
import json
import subprocess
import sys

import pytest

# CI installs pytest and nothing else, on purpose: the UNVERIFIED path is what
# a fresh user gets. Skip the module there instead of failing collection.
np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")

from conftest import REPO_ROOT, SKILLS_DIR

ML_SCRIPTS = SKILLS_DIR / "ml-auditor" / "scripts"
ML_RUN = SKILLS_DIR / "ml-auditor" / "scripts" / "run.py"


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "ml_auditor_engine", ML_SCRIPTS / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _block_import(name):
    original = builtins.__import__

    def fake(name_, *args, **kwargs):
        if name_ == name or name_.startswith(name + "."):
            raise ImportError(f"simulated: {name} not installed")
        return original(name_, *args, **kwargs)

    return fake


def _clean_frame():
    """A well-separated, zero-intrinsic-noise binary classification frame."""
    from sklearn.datasets import make_classification
    X, y = make_classification(n_samples=400, n_features=6, n_informative=4,
                               n_redundant=1, flip_y=0.0, class_sep=2.0,
                               random_state=0)
    df = pd.DataFrame(X, columns=[f"f{i}" for i in range(6)])
    df["label"] = y
    return df


def _write_clean_csv(path):
    _clean_frame().to_csv(path, index=False)


def _write_leak_csv(path):
    df = _clean_frame()
    df["leak"] = df["label"]           # feature identical to the label
    df.to_csv(path, index=False)


def _write_discrete_leak_csv(path):
    df = _clean_frame()
    df["code"] = df["label"].map({0: "A", 1: "B"})  # discrete, determined by label
    df.to_csv(path, index=False)


def _write_noisy_csv(path, flip=0.15):
    df = _clean_frame()
    y = df["label"].to_numpy().copy()
    rng = np.random.default_rng(1)
    idx = rng.choice(len(y), size=int(flip * len(y)), replace=False)
    y[idx] = 1 - y[idx]
    df["label"] = y
    df.to_csv(path, index=False)


def _write_post_outcome_csv(path, stray_negatives=4):
    """A column booked after the outcome: 0 for almost every negative.

    Not constant, not identical to the label, not discrete, only mildly
    correlated -- invisible to the other four leakage rules, while a model
    fitted on it scores ~0.98 for a reason that will not exist at prediction
    time. This is the shape of the leak that got through a real audit run.
    """
    df = _clean_frame()
    rng = np.random.default_rng(3)
    y = df["label"].to_numpy()
    amount = np.where(y == 1, rng.gamma(2.0, 300.0, len(y)), 0.0)
    neg = np.flatnonzero(y == 0)
    pick = rng.choice(neg, size=min(stray_negatives, len(neg)), replace=False)
    amount[pick] = rng.uniform(10.0, 900.0, len(pick))
    df["recovery"] = amount
    df.to_csv(path, index=False)


# ------------------------------------------------- graceful degradation

def test_degradation_when_sklearn_missing(monkeypatch, tmp_path):
    e = _load_engine()
    _write_clean_csv(tmp_path / "data.csv")
    monkeypatch.setattr(builtins, "__import__", _block_import("sklearn"))
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["status"] == "UNVERIFIED"
    assert res["evidence_level"] == "UNVERIFIED"
    assert "scikit-learn" in res["reason"].lower()


def test_unverified_on_missing_csv(tmp_path):
    e = _load_engine()
    res = e.audit(str(tmp_path / "nope.csv"))
    assert res["status"] == "UNVERIFIED"
    assert "not found" in res["reason"].lower()


# ------------------------------------------------- real verdicts

def test_pass_on_clean_dataset(tmp_path):
    e = _load_engine()
    _write_clean_csv(tmp_path / "data.csv")
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["status"] == "PASS", res
    assert res["evidence_level"] == "EMPIRICAL"
    assert res["data"]["n_samples"] == 400
    assert res["data"]["suspect_ratio"] <= 0.05


def test_fail_on_identical_feature_leakage(tmp_path):
    e = _load_engine()
    _write_leak_csv(tmp_path / "data.csv")
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["status"] == "FAIL", res
    assert res["evidence_level"] == "EXACT"
    assert "leakage" in res["reason"].lower()
    assert any("identical to the label" in f for f in res["data"]["leak_fatal"])


def test_fail_on_discrete_target_leakage(tmp_path):
    e = _load_engine()
    _write_discrete_leak_csv(tmp_path / "data.csv")
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["status"] == "FAIL", res
    assert "leakage" in res["reason"].lower()


def test_fail_on_post_outcome_column(tmp_path):
    """A column that exists only after the outcome is leakage, not a feature."""
    e = _load_engine()
    _write_post_outcome_csv(tmp_path / "data.csv")
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["status"] == "FAIL", res
    assert res["evidence_level"] == "EXACT"
    assert any("post-outcome" in f for f in res["data"]["leak_fatal"])


def test_a_count_column_is_not_a_post_outcome_column(tmp_path):
    """Both classes take the same few values: nothing to separate."""
    e = _load_engine()
    df = _clean_frame()
    df["late_payments"] = np.random.default_rng(5).integers(0, 7, len(df))
    df.to_csv(tmp_path / "data.csv", index=False)
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["data"]["leak_fatal"] == [], res["data"]["leak_fatal"]


def test_a_column_mostly_zero_in_both_classes_is_not_flagged(tmp_path):
    """A sparse amount that is sparse for everyone is not asymmetric."""
    e = _load_engine()
    df = _clean_frame()
    rng = np.random.default_rng(6)
    df["deposit"] = np.where(rng.random(len(df)) < 0.95, 0.0,
                             rng.uniform(1.0, 900.0, len(df)))
    df.to_csv(tmp_path / "data.csv", index=False)
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["data"]["leak_fatal"] == [], res["data"]["leak_fatal"]


def test_a_tiny_class_is_not_a_post_outcome_column():
    """Ten rows on one value say nothing about where the column came from."""
    e = _load_engine()
    y = pd.Series([0] * 300 + [1] * 10)
    f = pd.Series(np.r_[np.random.default_rng(2).uniform(1.0, 900.0, 300),
                        np.zeros(10)])
    assert e._post_outcome_signature(pd, f, y, [0, 1]) is None


def test_labels_are_not_judged_when_the_features_carry_no_signal(tmp_path):
    """Chance disagreement is not evidence of a wrong label.

    With labels drawn at random the out-of-fold classifier is confidently
    wrong by chance; the gate must say it cannot assess the labels instead of
    accusing a fifth of the rows (measured: 145/600 on a real dataset).
    """
    e = _load_engine()
    df = _clean_frame()
    df["label"] = np.random.default_rng(7).integers(0, 2, len(df))
    df.to_csv(tmp_path / "data.csv", index=False)
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["status"] == "UNVERIFIED", res
    assert "cannot be assessed" in res["reason"], res["reason"]
    assert res["data"]["suspect_count"] == 0


def test_fail_on_label_errors(tmp_path):
    e = _load_engine()
    _write_noisy_csv(tmp_path / "data.csv", flip=0.15)
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["status"] == "FAIL", res
    assert res["evidence_level"] == "EMPIRICAL"
    assert "label errors" in res["reason"].lower()
    assert res["data"]["suspect_ratio"] > 0.05


def test_auto_detects_label_column(tmp_path):
    e = _load_engine()
    _write_clean_csv(tmp_path / "data.csv")
    res = e.audit(str(tmp_path / "data.csv"), root=str(tmp_path))
    assert res["status"] in {"PASS", "FAIL"}
    assert res["data"]["label"] == "label"


# ------------------------------------------------- CLI integration

def test_cli_emits_gate_via_subprocess(tmp_path):
    _write_clean_csv(tmp_path / "data.csv")
    proc = subprocess.run(
        [sys.executable, str(ML_RUN), "--root", str(tmp_path),
         "--action", "gate", "--input", str(tmp_path / "data.csv"),
         "--label", "label"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-500:]
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["status"] == "PASS", payload
    assert payload["evidence_level"] == "EMPIRICAL"
    gates = sorted((tmp_path / "process" / "gates").glob("ml-auditor_*.json"))
    assert gates, "no gate written into the workspace"
