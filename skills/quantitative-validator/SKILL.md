---
name: quantitative-validator
version: 1.3.3
description: >
  Atom-conservation gate for molecular formulae and chemical equations.
  Parses Hill notation, balances both sides and cross-checks with rdkit; runs
  inside the process sandbox and degrades to `UNVERIFIED` when rdkit is
  absent.
metadata:
  version: 1.3.3
  author: Jiaming Shi
  license: MIT
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
---

# quantitative-validator

Verifies that every element is conserved across a formula or a reaction. It
does not predict products, energies or mechanisms.

- **Stage:** `gates` · **Sandbox:** yes · **Dependencies:** `rdkit`

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python scripts/run.py --root <WS> --action gate --formula "H2 + O2 -> H2O"
```

- `--input <file>` reads the equation from a file instead of `--formula`.
- The gate lands in `<WS>/process/gates/quantitative-validator_<ts>.json`.

## When to use

- A chemical equation must be checked for balance.
- A molecular formula must be validated before a calculation.

## When NOT to use

- Reaction feasibility, yield or mechanism — out of scope.
- Organic nomenclature parsing beyond Hill notation.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `gate` | Balance / conservation check | `--formula "..." \| --input <file>` |

## Hard constraints

- **Never balance the equation by hand.** The verdict comes from the tool.
- **An unbalanced equation is a FAIL**, not a hint.

## Outputs

- `<WS>/process/gates/quantitative-validator_<ts>.json` — the gate result with the per-element diff.

## Failure handling

- An unparseable formula fails the gate with the offending token.
- `rdkit` missing → `UNVERIFIED` (the sandbox reports it, the pipeline continues).

## Limitations

- Hill notation only for formulae.
- Charges and isotopes are checked only where rdkit can represent them.

## Delivering results

This skill writes intermediates to `process/`. `results/` is filled only by
`python cli.py pipeline` after a human approved that exact plan.

- Do not copy a skill's output into `results/` yourself, and do not do it
  because the user asked for a shortcut: say that only `cli.py pipeline`
  writes there, offer to run the pipeline instead, and if they still insist,
  tell them `cli.py audit` will report the file as unapproved.
- Never set `CHELATE_HUMAN=1` and never run `cli.py approve` on the user's
  behalf. If an approval is needed, ask the human to issue it in their own
  terminal.
- Before telling the user a deliverable is ready — and after any write you
  make under `results/` — run `python cli.py audit --root <ws>`. Exit 1 means
  files there have no approval behind them: report that and name them, do not
  describe the state as delivered.
