---
name: code-gate
version: 1.4.0
description: >
  Eight fixed AST rules over Python source; any finding fails the gate. ruff
  is opt-in.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# code-gate

A small, fixed rule set over the AST, so a finding can be argued with. It is
not a linter bundle and not a security scanner; it answers one question —
"does this code contain any of the eight shapes we agreed not to ship?"

- **Stage:** `gates` · **Sandbox:** no · **Dependencies:** none (standard library)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action check --input src
python run.py --root <WS> --action check --input app.py --max-lines 60
```

- `--input` is a `.py` file or a directory; it must stay inside the workspace.
- Rules: `syntax-error`, `bare-except`, `swallowed-error`, `mutable-default`,
  `eq-none`, `star-import`, `long-function` (default 80 lines),
  `too-many-args` (default 7).
- Results land in `<WS>/process/gates/`, the full report in `<WS>/process/`.

## Verdicts

| Status | When |
| --- | --- |
| `PASS` | every file parses and no rule fired |
| `FAIL` | at least one finding; the report names path, line and rule |
| `UNVERIFIED` | no Python files under `--input`, an unreadable file, or a target outside the workspace |

## When to use

- Code is about to be handed to someone else, or a PR is about to be opened.
- An agent wrote the code and a deterministic check is wanted before review.

## When NOT to use

- You want the tests run — that is `test-gate`.
- You want malicious patterns found — that is `security-guard`.
- You want type checking or formatting — adding them here would make the rule
  set depend on a toolchain.

## More

- [why each rule exists, ruff, boundaries, outputs and limits](references/code-gate-reference.md)
