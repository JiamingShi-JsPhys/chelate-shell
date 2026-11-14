---
name: security-guard
version: 1.3.3
description: >
  Screens text and Python sources before dispatch: prompt-injection markers in
  external text, and an AST walk for dangerous call sites (`eval`, `exec`,
  `os.system`, `subprocess.*`). A screen, not a sandbox.
metadata:
  version: 1.3.3
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
- The gate lands in `<WS>/process/gates/security-guard_<ts>.json`.

## When to use

- Untrusted text is about to enter the pipeline.
- A Python file must be checked for dangerous calls before it runs.

## When NOT to use

- You need containment — that is the sandbox, not this skill.
- The input is already trusted, first-party data.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `gate` | Screen and emit a gate result | `--input <path\|text> [--mode text\|source\|auto] [--json]` |
| `scan` | Screen without gating | same arguments |

## Hard constraints

- **A screen, not a sandbox.** Never describe a pass as "safe".
- **Report the marker and its line**, never a rewritten file.

## Outputs

- `<WS>/process/gates/security-guard_<ts>.json` — the gate result with every hit listed.

## Failure handling

- An unreadable input exits non-zero with a clear message.
- A clean input is a pass with an explicit "no marker found" note.

## Limitations

- Marker and AST heuristics only; unknown attack shapes pass.
- It never modifies the screened file.
