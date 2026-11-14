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
   - a *discrete* feature that perfectly predicts the label,
   - (near-)perfectly correlated (`|r| > 0.999`) with a continuous label, or
   - **booked after the outcome**: one class puts ≥ 90% of its rows on a
     single value while the other class spreads over ≥ 30 distinct values and
     barely touches that value. A continuous column that exists only for the
     positives (a recovery amount, a settlement figure, a post-decision flag
     with an amount beside it) looks harmless to every test above and still
     drives a model to ~0.98.
   Any hit is a hard **FAIL**.

2. **Label errors** (statistical, `EMPIRICAL`) — a `RandomForestClassifier` is
   trained with stratified cross-validation; a sample is a *suspect* when the
   model **confidently predicts a different class** out-of-fold (≥ 0.75
   probability). A suspect fraction above 5% is a **FAIL** (label noise).

   The scan needs the features to carry signal. When out-of-fold accuracy sits
   at the majority-class baseline, chance disagreement is not evidence of a
   wrong label, so the gate returns **UNVERIFIED** — "no leakage found, but
   label quality cannot be assessed" — rather than naming rows the model got
   wrong by accident. This matters after a leak is removed: a dataset whose
   only informative column *was* the leak becomes unlearnable, and an earlier
   version of this gate accused 145 of 600 rows when 12 had been flipped.

Clean data → **PASS** (`EMPIRICAL`). Constant / duplicate feature columns are
reported as warnings, not failures.

### What it cannot see

Leakage is a property of *how* a column was produced, and no statistic proves
it. These rules catch columns that are (nearly) determined by the label; a
column that merely records something decided at the same time as the label —
or a leak diluted with noise — can pass every test. The verdict certifies what
was tested, not that the feature set is free of leakage. Read the column list
against the study timeline before trusting a model that scores well.

## Dependencies & graceful degrade
`scikit-learn` + `pandas` are hard requirements; a missing one degrades the
gate to `UNVERIFIED`. `cleanlab` is used only as an optional second opinion on
the label-issue set when it happens to be installed — it is never required
(which is why it is *not* a manifest dependency: the sandbox router would
otherwise short-circuit the skill whenever cleanlab is absent).

## Clean-room
Independent composition of scikit-learn primitives; no third-party audit
source is copied.
