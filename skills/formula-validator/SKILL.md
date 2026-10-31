---
name: formula-validator
version: 1.2.0
description: >
  Deterministic formula checker for physics and maths. You extract the
  equation and declare the units; the tool runs five CAS layers plus a pint
  unit cross-check and returns a strict pass / fail / unknown verdict. Fires
  on any formula whose correctness matters.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# formula-validator

Checks a formula with five independent layers (parse, dimension, limit,
numeric, symbolic) plus a pint unit cross-check, and returns one strict
verdict. You extract and interpret; the tool computes.

- **Stage:** `gates` · **Sandbox:** no · **Dependencies:** `sympy`, `numpy`, `pint`

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action validate -- --expr "F = m*a" --units F=N --units m=kg --units a=m/s**2
```

- Everything after `--` goes to the legacy CLI unchanged.
- `--units sym=unit` may be repeated; leave a symbol undeclared rather than
  guessing its unit.
- The verdict is written to `<WS>/process/gates/formula-validator_<ts>.json`
  and a Markdown report to `<WS>/process/reports/`.

## When to use

- A formula, identity or derived result appears and its correctness matters.
- A multi-step derivation must be checked, or a wrong result localised.
- A matrix must be confirmed Hermitian, unitary or otherwise structured.
- A dimensional or limiting-case check is requested.

## When NOT to use

- Purely numeric evaluation with no symbolic claim.
- Prose or literature work with no formula.
- Curve fitting or statistics on measured data.
- A formula the user only wants typeset.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `validate` | D1–D5 layers + pint cross-check | `--expr "..." [--units s=u ...]` |
| `check` | Alias of `validate` | same as `validate` |
| `derive` | Check a multi-step derivation | `--expr "..."` |
| `matrix` | Matrix property check | `--expr "..."` |
| `units` | pint unit check only | `--expr "..." --units s=u` |

## Hard constraints

- **Never compute the algebra yourself.**
- **Never report a verdict the tool did not produce.** `unknown` is a valid outcome and must never be reinterpreted as a pass.
- **Never guess a unit silently** — an undeclared symbol is a legitimate state.

## Outputs

- `<WS>/process/gates/formula-validator_<ts>.json` — the merged gate result.
- `<WS>/process/reports/` — the Markdown report with the failing layer named.

## Failure handling

- Exit `3` (parse error) — retry in SymPy syntax, then quote the message.
- Exit `2` (unknown) — report it as unknown and name what was not checked.
- Exit `4` — report the message verbatim; never fall back to guessing.
- D2 disagrees while D4 agrees → verdict `conflict`; almost always a unit error.

## Limitations

- Only `validate`/`check` run the pint layer; `derive`/`matrix` are D1–D5 only.
- Pint cannot unit-check a decision; the report is a deterministic verdict.
