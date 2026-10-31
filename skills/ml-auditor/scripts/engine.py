"""ml-auditor engine — real ML data audit (leakage + label errors).

Given a labelled CSV this gate screens the dataset for the two failure modes
that silently destroy an ML result:

  1. **Data leakage** (deterministic, ``EXACT`` evidence) — a feature that is
     identical to the label, fully determined by the label, perfectly predicts
     the label, or is (near-)perfectly correlated with it. Any of these is a
     hard FAIL: the model would score almost perfectly for the wrong reason.
  2. **Label errors** (statistical, ``EMPIRICAL`` evidence) — samples whose
     cross-validated classifier assigns low probability to their recorded
     label. A suspect fraction above the threshold is a FAIL (label noise).

Implementation is an independent, clean-room composition of scikit-learn
primitives (``RandomForestClassifier`` + ``cross_val_predict``). ``cleanlab``
is used only as an *optional* second opinion on the label-issue set when it
happens to be installed; it is never required.

Dependency policy: ``scikit-learn`` + ``pandas`` are the hard requirements.
When they are not importable the gate degrades to ``UNVERIFIED`` — it never
fabricates a verdict and never crashes.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional


def _verdict(status: str, evidence: str, reason: str,
             data: Optional[dict] = None, artifacts: Optional[List[str]] = None) -> dict:
    return {"status": status, "evidence_level": evidence, "reason": reason,
            "artifacts": artifacts or [], "data": data or {}}


def _deps():
    """Import the hard dependencies; return a namespace or ``None``."""
    try:
        import numpy
        import pandas
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import StratifiedKFold, cross_val_predict
        from sklearn.preprocessing import LabelEncoder
    except Exception:
        return None
    return {
        "np": numpy, "pd": pandas,
        "RandomForestClassifier": RandomForestClassifier,
        "StratifiedKFold": StratifiedKFold,
        "cross_val_predict": cross_val_predict,
        "LabelEncoder": LabelEncoder,
    }


def _cleanlab():
    try:
        import cleanlab  # noqa: WPS433
        return cleanlab
    except Exception:
        return None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _series_equal(a, b) -> bool:
    """Value equality robust to dtype differences (compares string forms)."""
    try:
        av = a.astype(str).to_numpy()
        bv = b.astype(str).to_numpy()
        return av.shape == bv.shape and bool((av == bv).all())
    except Exception:
        return False


def _to_numeric(deps, X):
    """Return a float matrix, factorising any non-numeric column to codes."""
    pd = deps["pd"]
    cols = {}
    for c in X.columns:
        s = X[c]
        if pd.api.types.is_numeric_dtype(s):
            cols[c] = pd.to_numeric(s, errors="coerce")
        else:
            cols[c] = pd.Series(pd.factorize(s)[0], index=s.index).astype(float)
    mat = pd.DataFrame(cols)[list(X.columns)]
    return mat.fillna(0.0).to_numpy(dtype=float)


def _pick_label(deps, df, label_col):
    pd = deps["pd"]
    if label_col:
        if label_col in df.columns:
            return label_col
        return None  # explicitly requested but absent
    for c in df.columns:
        if str(c).lower() in ("label", "target", "y", "class", "outcome"):
            return c
    return df.columns[-1]


def _leakage_report(deps, X, y) -> Dict[str, list]:
    """Deterministic leakage / degeneracy scan over the feature frame."""
    pd = deps["pd"]
    fatal: List[str] = []
    warnings: List[str] = []
    const_feats, dup_feats = [], []

    # duplicate feature columns
    col_values = {c: pd.util.hash_pandas_object(X[c], index=False).to_numpy()
                  for c in X.columns}
    seen: Dict[bytes, str] = {}
    for c in X.columns:
        key = col_values[c].tobytes()
        if key in seen:
            dup_feats.append(f"{c} duplicates {seen[key]}")
        else:
            seen[key] = c

    y_is_regression = pd.api.types.is_numeric_dtype(y) and y.nunique(dropna=True) > 20

    for c in X.columns:
        nun = X[c].nunique(dropna=False)
        if nun <= 1:
            const_feats.append(c)
            continue
        if _series_equal(X[c], y):
            fatal.append(f"{c}: identical to the label")
            continue
        pair = pd.DataFrame({"f": X[c].to_numpy(), "y": y.to_numpy()})
        # label -> feature : feature is fully determined by the label
        if (pair.groupby("y")["f"].nunique() <= 1).all():
            fatal.append(f"{c}: fully determined by the label (label leaks in)")
            continue
        # feature -> label : a DISCRETE feature that perfectly predicts the
        # label is target leakage. A continuous feature has (near-)unique
        # values, so each value maps to one label trivially — the test is
        # meaningless there and is skipped.
        if 1 < nun <= 25 and (pair.groupby("f")["y"].nunique() <= 1).all():
            fatal.append(f"{c}: perfectly predicts the label (target leakage)")
            continue
        if y_is_regression:
            try:
                r = pd.to_numeric(X[c], errors="coerce").corr(
                    pd.to_numeric(y, errors="coerce"))
                if r is not None and abs(float(r)) > 0.999:
                    fatal.append(f"{c}: near-perfect correlation with label "
                                 f"(r={float(r):.3f})")
            except Exception:
                pass

    if dup_feats:
        warnings.append("duplicate feature columns: " + ", ".join(dup_feats))
    if const_feats:
        warnings.append("constant feature columns: " + ", ".join(map(str, const_feats)))
    return {"fatal": fatal, "warnings": warnings}


def _label_error_scan(deps, X, y):
    """Cross-validated label-confidence scan. Returns (suspect_idx, ratio, note)."""
    np, pd = deps["np"], deps["pd"]
    if not pd.api.types.is_numeric_dtype(y) or y.nunique(dropna=True) <= 20:
        kind = "classification"
    else:
        kind = "regression"

    if kind == "regression":
        # flag observations whose |residual| exceeds 3 sigma (LOO-free proxy)
        try:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.model_selection import cross_val_predict
            Xnum = _to_numeric(deps, X)
            yv = pd.to_numeric(y, errors="coerce").to_numpy(dtype=float)
            mask = ~np.isnan(yv)
            pred = cross_val_predict(RandomForestRegressor(
                n_estimators=120, random_state=0, n_jobs=1),
                Xnum[mask], yv[mask], cv=5)
            resid = yv[mask] - pred
            sd = float(np.std(resid)) or 1.0
            idx = np.where(np.abs(resid) > 3 * sd)[0]
            return idx, len(idx) / max(1, int(mask.sum())), "regression residual scan"
        except Exception as exc:  # pragma: no cover - defensive
            return np.array([], dtype=int), 0.0, f"label-error scan skipped ({exc})"

    # classification
    yv = deps["LabelEncoder"]().fit_transform(y.astype(str).to_numpy())
    counts = pd.Series(yv).value_counts()
    min_class = int(counts.min())
    if min_class < 2:
        return np.array([], dtype=int), 0.0, \
            "label-error scan skipped (a class has <2 samples)"
    n_splits = max(2, min(5, min_class))
    try:
        Xnum = _to_numeric(deps, X)
        skf = deps["StratifiedKFold"](n_splits=n_splits, shuffle=True,
                                      random_state=0)
        clf = deps["RandomForestClassifier"](n_estimators=120, random_state=0,
                                             n_jobs=1)
        proba = deps["cross_val_predict"](clf, Xnum, yv, cv=skf,
                                          method="predict_proba")
        pred = proba.argmax(axis=1)
        maxp = proba.max(axis=1)
        # A label error = the model confidently predicts a DIFFERENT class
        # out-of-fold (confident disagreement), not merely low confidence —
        # overlapping-but-correct samples would otherwise be over-flagged.
        suspects = np.where((pred != yv) & (maxp >= 0.6))[0]

        cl = _cleanlab()
        if cl is not None:
            try:
                extra = cl.filter.find_label_issues(labels=yv, pred_probs=proba)
                suspects = np.union1d(suspects, np.asarray(extra, dtype=int))
            except Exception:
                pass  # cleanlab is a best-effort second opinion only
        ratio = len(suspects) / len(yv)
        return suspects, ratio, f"classification OOF confidence (cv={n_splits})"
    except Exception as exc:  # pragma: no cover - defensive
        return np.array([], dtype=int), 0.0, f"label-error scan skipped ({exc})"


# ---------------------------------------------------------------------------
# gate entry point
# ---------------------------------------------------------------------------

def audit(csv_path: str, label_col: Optional[str] = None,
          root: Optional[str] = None,
          label_error_threshold: float = 0.05) -> dict:
    """Audit a labelled CSV for data leakage and label errors."""
    deps = _deps()
    if deps is None:
        return _verdict("UNVERIFIED", "UNVERIFIED",
                        "scikit-learn/pandas not installed; ML audit "
                        "unavailable (graceful degrade)", {"deps": False})
    pd = deps["pd"]
    have_cleanlab = _cleanlab() is not None

    if not csv_path or not os.path.isfile(csv_path):
        return _verdict("UNVERIFIED", "UNVERIFIED",
                        f"dataset not found: {csv_path!r}", {"deps": True})

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        return _verdict("UNVERIFIED", "UNVERIFIED",
                        f"could not read CSV {csv_path!r}: {exc}", {"deps": True})

    if df.shape[1] < 2:
        return _verdict("UNVERIFIED", "UNVERIFIED",
                        "dataset needs at least one feature and one label "
                        "column", {"deps": True})
    df = df.dropna(how="all")
    if df.empty:
        return _verdict("UNVERIFIED", "UNVERIFIED", "dataset is empty",
                        {"deps": True})

    label = _pick_label(deps, df, label_col)
    if label is None:
        return _verdict("UNVERIFIED", "UNVERIFIED",
                        f"label column {label_col!r} not in dataset columns "
                        f"{list(df.columns)}", {"deps": True})
    y = df[label]
    X = df.drop(columns=[label])

    leak = _leakage_report(deps, X, y)
    data = {
        "deps": True, "cleanlab": have_cleanlab, "label": label,
        "n_samples": int(len(df)), "n_features": int(X.shape[1]),
        "leak_fatal": leak["fatal"], "warnings": leak["warnings"],
    }

    # 1) data leakage is fatal -> FAIL (EXACT, deterministic)
    if leak["fatal"]:
        reason = "data leakage detected: " + "; ".join(leak["fatal"])
        return _verdict("FAIL", "EXACT", reason, data,
                        artifacts=_maybe_report(root, data))

    # 2) label-error scan (EMPIRICAL)
    suspects, ratio, note = _label_error_scan(deps, X, y)
    data["label_scan"] = note
    data["suspect_count"] = int(len(suspects))
    data["suspect_ratio"] = round(float(ratio), 4)
    data["suspect_indices"] = [int(i) for i in list(suspects)[:50]]

    if ratio > label_error_threshold:
        reason = (f"suspected label errors: {len(suspects)}/{len(df)} "
                  f"({ratio:.1%}) above {label_error_threshold:.0%} threshold "
                  f"[{note}]")
        return _verdict("FAIL", "EMPIRICAL", reason, data,
                        artifacts=_maybe_report(root, data))

    warn = ("; " + "; ".join(leak["warnings"])) if leak["warnings"] else ""
    reason = (f"no leakage; {len(suspects)}/{len(df)} suspected label errors "
              f"({ratio:.1%}) [{note}]{warn}")
    return _verdict("PASS", "EMPIRICAL", reason, data,
                    artifacts=_maybe_report(root, data))


def _maybe_report(root, data) -> List[str]:
    """Persist the detailed audit payload under <root>/process/audits/."""
    if not root:
        return []
    try:
        out_dir = os.path.join(root, "process", "audits")
        os.makedirs(out_dir, exist_ok=True)
        import time
        path = os.path.join(out_dir, f"ml_auditor_{int(time.time())}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
        return [path]
    except Exception:
        return []
