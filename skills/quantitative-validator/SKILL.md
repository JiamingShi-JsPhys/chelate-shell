---
name: quantitative-validator
version: 1.2.0
description: >
  Atom-conservation gate for molecular formulae and chemical equations.
  Parses Hill notation, balances both sides and cross-checks with rdkit; runs
  inside the process sandbox and degrades to `UNVERIFIED` when rdkit is
  absent.
metadata:
  version: 1.2.0
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
