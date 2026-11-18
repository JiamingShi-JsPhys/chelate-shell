---
name: reference-auditor
version: 1.4.0
description: >
  Verifies every DOI in a draft against Crossref; a missing DOI fails, a
  network error is unknown.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# reference-auditor

Checks that each DOI in the draft resolves in Crossref. It confirms existence
only — not that the DOI is the paper you meant to cite.

- **Stage:** `gates` · **Sandbox:** no · **Dependencies:** `requests`

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action audit --input draft.md
```

- `--text "..."` audits inline text instead of a file.
- A **non-existent DOI is a FAIL**; a **network error is `unknown`**, never a
  pass. The DOI is reported exactly as found, never rewritten.
- The gate lands in `<WS>/process/gates/reference-auditor_<ts>.json`.

## When to use

- A draft with citations is about to be delivered.
- A DOI is suspected to be fabricated.
- A bibliography must be checked before submission.

## When NOT to use

- The citation content must be judged — only existence is checked.
- No DOI is present; other identifiers are out of scope.

## More

- [actions, outputs, failure handling and limits](references/reference-auditor-reference.md)
