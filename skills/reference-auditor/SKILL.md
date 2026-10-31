---
name: reference-auditor
version: 1.2.0
description: >
  Extracts every DOI from a draft and verifies it against the Crossref API. A
  DOI that does not exist fails the gate and stops the pipeline; a network
  failure is reported as unknown, never as a pass.
metadata:
  version: 1.2.0
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
- `--timeout` overrides the per-DOI HTTP timeout (default from config).
- The gate lands in `<WS>/process/gates/reference-auditor_<ts>.json`.

## When to use

- A draft with citations is about to be delivered.
- A DOI is suspected to be fabricated.
- A bibliography must be checked before submission.

## When NOT to use

- The citation content must be judged — only existence is checked.
- No DOI is present; other identifiers are out of scope.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `audit` | Extract and verify every DOI | `--input <draft> \| --text "..." [--timeout N]` |

## Hard constraints

- **A non-existent DOI is a FAIL**, never a warning.
- **A network error is `unknown`**, never a pass.
- **Never rewrite the DOI.** Report it exactly as found.

## Outputs

- `<WS>/process/gates/reference-auditor_<ts>.json` — the gate result.
- A per-DOI verification table under `process/`.

## Failure handling

- Crossref unreachable → `UNVERIFIED`/`unknown` with the HTTP error.
- A draft with no DOI yields a pass with an explicit "nothing to check" note.

## Limitations

- Existence only — citation correctness stays the author's responsibility.
- One HTTP request per DOI; a large bibliography is rate-limited.
