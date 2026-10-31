---
name: ml-auditor
description: ML data-audit gate. Detects data leakage (feature==label, deterministic mapping, near-perfect correlation) and label errors (cross-validated label confidence) in a labelled CSV. Degrades to UNVERIFIED when scikit-learn/pandas are absent.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.2.0
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
version: 1.2.0
---

# ml-auditor

## Quick Execution

**Do NOT read the source code. Run this exact command format directly:**

```bash
python scripts/run.py --root <WS> --action gate --input data.csv --label target
python scripts/run.py --root <WS> --action gate --data data.csv      # label auto-detected
```

- `--root <WS>` = the user's workspace (absolute path). All artifacts land in
  `<WS>/process/gates/ml-auditor_<ts>.json` (plus a detailed
  `<WS>/process/audits/ml_auditor_<ts>.json`) — never in the skill's install
  dir.
- Valid `--action`: `gate`.
- `--input` / `--data` is a labelled CSV. `--label` names the target column;
  when omitted it is auto-detected (a column named `label`/`target`/`y`/
  `class`/`outcome`, else the last column).
- **This skill runs in a sandboxed process (sandbox_required: true).**
  The 120-second circuit-breaker force-kills the child on timeout and returns
  `UNVERIFIED` — not `FAIL`. Do not treat a timeout as a data failure.

## What it checks
1. **Data leakage** (deterministic, `EXACT`) — a feature that is identical to
   the label, fully determined by the label, perfectly predicts the label, or
   is (near-)perfectly correlated with it. Any hit is a hard **FAIL**.
2. **Label errors** (statistical, `EMPIRICAL`) — a `RandomForestClassifier`
   trained with stratified cross-validation gives each sample an out-of-fold
   probability for its recorded label. Samples below 0.5 are suspects; a
   suspect fraction above 5% is a **FAIL** (label noise).
Clean data with no leakage and few suspects → **PASS**. Degenerate columns
(constant / duplicate features) are reported as warnings, not failures.

## Dependency & graceful degrade
`scikit-learn` + `pandas` are the hard requirements; `cleanlab` is used only as
an optional second opinion on the label-issue set when installed. A missing
hard dependency degrades the gate to `UNVERIFIED` — never a fabricated verdict.

## When to use
- Screen a labelled dataset for leakage / label noise before training.

## When NOT to use
- Unstructured (text/image) datasets; real-time inference.

## Dependencies
- `scikit-learn`, `pandas` — hard (audit engine).
- `cleanlab` — optional label-quality cross-check.
