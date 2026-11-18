---
name: quantitative-validator
version: 1.4.0
description: >
  Atom-conservation gate for molecular formulae and equations; balances and
  checks with rdkit.
metadata:
  version: 1.4.0
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
- **Never balance the equation by hand**: the verdict comes from the tool, and
  an unbalanced equation is a **FAIL**, not a hint.
- The gate lands in `<WS>/process/gates/quantitative-validator_<ts>.json`.

## When to use

- A chemical equation must be checked for balance.
- A molecular formula must be validated before a calculation.

## When NOT to use

- Reaction feasibility, yield or mechanism — out of scope.
- Organic nomenclature parsing beyond Hill notation.

## More

- [actions, outputs, failure handling and limits](references/quantitative-validator-reference.md)
