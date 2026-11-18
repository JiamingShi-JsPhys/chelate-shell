---
name: longitudinal-analysis
version: 1.4.0
description: >
  Repeated-measures panel analysis in Python; R steps skip, never substitute,
  without Rscript.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# longitudinal-analysis

Orchestrates a fixed pipeline of statistical steps over panel data and reports
each step's status. It never substitutes hand-written Python for a missing R
step.

- **Stage:** `gates` · **Sandbox:** no · **Dependencies:** `pandas` (`numpy`, R with lme4/lavaan, `python-docx` optional)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action list-steps -- --config config/examples/behavior_2x2x2.yaml
```

- `validate` then `list-steps` shows which steps the config enables and which
  need R; `run` executes everything or one named step (`--step lmm`).
- **Never hand-write Python to replace a skipped R step, and never install
  R.** Report each step's own status; do not merge them into one verdict.
- The gate lands in `<WS>/process/gates/longitudinal-analysis_<ts>.json`.

## When to use

- The data has repeated measures (one or more sessions per subject).
- The request names LMM, mixed model, mediation or sensitivity analysis.
- Descriptive statistics or a manipulation check are needed over panel data.

## When NOT to use

- The data is a single cross-section — a plain test is enough.
- You intend to imitate a skipped R step in Python — never do that.

## More

- [actions, outputs, failure handling and limits](references/longitudinal-analysis-reference.md)
