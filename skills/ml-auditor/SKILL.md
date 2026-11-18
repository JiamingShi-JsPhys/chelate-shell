---
name: ml-auditor
version: 1.4.0
description: >
  Audits a labelled dataset for leakage and label errors with scikit-learn;
  cleanlab is optional.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
---

# ml-auditor

Detects data leakage (a feature that encodes the target) and suspicious labels
in a CSV. It audits the dataset; it does not train your final model.

- **Stage:** `gates` · **Sandbox:** yes · **Dependencies:** `scikit-learn`, `pandas` (`cleanlab` optional)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python scripts/run.py --root <WS> --action gate --input data.csv --label target
```

- `--label` may be omitted; the target column is then auto-detected.
- `--data` is an alias of `--input`.
- **Never modify the dataset** — the audit is read-only, and a suspect feature
  is reported, never dropped.
- The gate lands in `<WS>/process/gates/ml-auditor_<ts>.json`.

## When to use

- A supervised dataset is about to be used for training or reporting.
- A model reports suspiciously high accuracy.

## When NOT to use

- Unlabelled data — there is no target to audit.
- You want the model trained or tuned.

## More

- [actions, outputs, failure handling and limits](references/ml-auditor-reference.md)
