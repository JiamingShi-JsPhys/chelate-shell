# ml-auditor

ML data-audit gate. Screens a labelled CSV for the two failure modes that
silently destroy an ML result — **data leakage** and **label errors** — and
returns a `PASS` / `FAIL` / `UNVERIFIED` verdict. Part of **chelate-shell
v1.2.0** (MIT).

## Usage

```bash
python scripts/run.py --root <WS> --action gate --input data.csv --label target
python scripts/run.py --root <WS> --action gate --data data.csv   # label auto-detected
```

The verdict is written to `<WS>/process/gates/ml-auditor_<ts>.json` and printed
as one JSON line on stdout; a detailed payload lands in
`<WS>/process/audits/ml_auditor_<ts>.json`.

## What it checks

1. **Data leakage** (deterministic, `EXACT`) — a feature that is:
   - identical to the label,
   - fully determined by the label (label leaks into the feature),
   - a *discrete* feature that perfectly predicts the label, or
   - (near-)perfectly correlated (`|r| > 0.999`) with a continuous label.
   Any hit is a hard **FAIL**.

2. **Label errors** (statistical, `EMPIRICAL`) — a `RandomForestClassifier` is
   trained with stratified cross-validation; a sample is a *suspect* when the
   model **confidently predicts a different class** out-of-fold. A suspect
   fraction above 5% is a **FAIL** (label noise).

Clean data → **PASS** (`EMPIRICAL`). Constant / duplicate feature columns are
reported as warnings, not failures.

## Dependencies & graceful degrade
`scikit-learn` + `pandas` are hard requirements; a missing one degrades the
gate to `UNVERIFIED`. `cleanlab` is used only as an optional second opinion on
the label-issue set when it happens to be installed — it is never required
(which is why it is *not* a manifest dependency: the sandbox router would
otherwise short-circuit the skill whenever cleanlab is absent).

## Clean-room
Independent composition of scikit-learn primitives; no third-party audit
source is copied.
