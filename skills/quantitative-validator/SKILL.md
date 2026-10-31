---
name: quantitative-validator
description: Atom-conservation gate. Parses a molecular formula or chemical equation and verifies the left/right element tallies match (rdkit cross-check). Degrades to UNVERIFIED when rdkit is absent.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.2.0
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
version: 1.2.0
---

# quantitative-validator

## Quick Execution

**Do NOT read the source code. Run this exact command format directly:**

```bash
python scripts/run.py --root <WS> --action gate --formula "H2 + O2 -> H2O"
python scripts/run.py --root <WS> --action gate --input equation.txt
```

- `--root <WS>` = the user's workspace (absolute path). All artifacts land in
  `<WS>/process/gates/quantitative-validator_<ts>.json` — never in the skill's
  install dir.
- Valid `--action`: `gate` (the generic stage actions `gate`/`process` map to
  the same handler).
- Input is a **molecular formula** (`H2O`, `Ca(OH)2`, `CuSO4·5H2O`) or a full
  **chemical equation** (`CH4 + 2 O2 -> CO2 + 2 H2O`). Pass it with `--formula`
  or point `--input` at a text file. Separate the two sides with `->`, `=>`,
  `==`, `=` or the unicode arrow; separate species with ` + `.
- **This skill runs in a sandboxed process (sandbox_required: true).**
  The 120-second circuit-breaker force-kills the child on timeout and returns
  `UNVERIFIED` — not `FAIL`. Do not treat a timeout as a data failure.

## What it checks — Atom Conservation
Given an equation, the gate sums every element on the left and on the right
(coefficients × per-species counts, hydrates expanded, charges ignored) and
compares. Equal tallies on both sides → `PASS`; any imbalance → `FAIL` with the
offending elements (`"atom NOT conserved — O left=2 right=1"`). A lone formula
is checked for well-formedness. Every element symbol is cross-checked against
RDKit's periodic table. Verdicts are `EXACT` (deterministic integer comparison).

## Dependency & graceful degrade
`rdkit` is a **hard** dependency. When it is importable the gate runs the real
check; when it is absent the gate returns `UNVERIFIED`
(`"rdkit not installed; ..."`) — it never fabricates a PASS/FAIL and never
raises. The underlying Hill-formula grammar is pure Python and unit-tested
independently of rdkit.

## When to use
- A reaction must be checked for balance before it goes into a manuscript.
- A formula must be validated for well-formedness / correct element symbols.

## When NOT to use
- Symbolic/algebraic proofs (use formula-validator).

## Dependencies
- `rdkit` — periodic-table element validation (hard dependency).
