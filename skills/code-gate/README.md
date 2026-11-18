# code-gate

Check Python source against eight fixed AST rules and fail on any finding.
`ruff` is opt-in, and the report names the version that produced its
findings.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

Nothing. Standard library only (`--ruff` needs `ruff` installed, and says so
when it is absent).

## Usage

```bash
python run.py --root <workspace> --action check --input src
python run.py --root <workspace> --action check --input app.py --max-lines 60
python run.py --root <workspace> --action check --input src --ruff
```

## Rules

| Rule | Why it is a finding |
| --- | --- |
| `syntax-error` | the file does not parse, so nothing else about it is checked |
| `bare-except` | `except:` also catches `KeyboardInterrupt` and `SystemExit` |
| `swallowed-error` | `except X: pass` discards the failure it caught |
| `mutable-default` | a list/dict/set default is shared by every call |
| `eq-none` | `== None` is False for any object that overrides `__eq__` |
| `star-import` | `from x import *` hides where a name came from |
| `long-function` | past `--max-lines` (80) a function stops being reviewable |
| `too-many-args` | past `--max-args` (7) a call site needs a structure |

## What it will not do

- **Change its verdict between machines.** There is no severity slider and no
  "all linters" mode: the rule set is fixed, so two machines agree.
- **Replace `security-guard`.** Screening `eval`/`exec`/`subprocess` happens
  there, once, so there is never a second answer to quote.
- **Pass an empty target.** A directory with no `.py` files is UNVERIFIED,
  not a clean bill of health.

## Outputs

| Path | Content |
|------|---------|
| `process/gates/code-gate_<ts>.json` | gate result (PASS / FAIL / UNVERIFIED) |
| `process/code_report_<ts>.json` | files checked, findings by rule, the first 50 findings, and any unreadable files |
