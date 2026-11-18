---
name: security-guard
version: 1.4.0
description: >
  Screens text for prompt injection and Python sources for dangerous calls
  (eval, exec, subprocess).
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# security-guard

Flags known injection markers and dangerous call sites so a later stage can
refuse the input. It reports risk; it cannot prove a file is safe.

- **Stage:** `infrastructure` · **Sandbox:** no · **Dependencies:** stdlib only

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action gate --input draft.md --mode auto
```

- `--mode {text,source,auto}` picks the scanner; `auto` decides from the file.
- `--json` emits the raw report.
- **A screen, not a sandbox**: never describe a pass as "safe", and never
  rewrite the screened file — report the marker and its line.
- The gate lands in `<WS>/process/gates/security-guard_<ts>.json`.

## When to use

- Untrusted text is about to enter the pipeline.
- A Python file must be checked for dangerous calls before it runs.

## When NOT to use

- You need containment — that is the sandbox, not this skill.
- The input is already trusted, first-party data.

## More

- [actions, outputs, failure handling and limits](references/security-guard-reference.md)
