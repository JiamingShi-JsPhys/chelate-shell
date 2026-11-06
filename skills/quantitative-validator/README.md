# quantitative-validator

Atom-conservation gate for chemistry. Parses a molecular formula or a full
chemical equation and verifies that the left- and right-hand sides carry
identical element tallies. Part of **chelate-shell v1.2.0** (MIT).

## Usage

```bash
# a balanced equation
python scripts/run.py --root <WS> --action gate --formula "H2 + O2 -> H2O"
# -> PASS  "atom-conserved (equation): H:4, O:2"

# an unbalanced equation
python scripts/run.py --root <WS> --action gate --formula "H2 + O2 -> H2O2"
# -> FAIL  "atom NOT conserved — O left=2 right=2" (H differs) ...

# a lone formula (well-formedness check)
python scripts/run.py --root <WS> --action gate --formula "Ca(OH)2"
# -> PASS

# from a file
python scripts/run.py --root <WS> --action gate --input reaction.txt
```

The gate verdict is written to `<WS>/process/gates/quantitative-validator_<ts>.json`
and printed as one JSON line on stdout:

```json
{"gate": ".../process/gates/quantitative-validator_<ts>.json",
 "status": "PASS", "evidence_level": "EXACT",
 "reason": "atom-conserved (equation): H:4, O:2", "artifacts": []}
```

## Grammar
- Element symbols (`H`, `He`, `Ca`), stoichiometric counts, nested parentheses
  (`Mg3(PO4)2`) and dot/asterisk hydrates (`CuSO4·5H2O`).
- Equation arrows: `->`, `=>`, `==`, `=`, `→`. Species separated by ` + `.
- Ionic charges (`^{2+}`, `2-`) are stripped — they do not affect atom counts.

## Dependency
`rdkit` is required. When absent the gate degrades to `UNVERIFIED`
(`"rdkit not installed; ..."`) instead of guessing. The pure-Python formula
grammar (`parse_formula`, `balance`) is unit-tested without rdkit.

## Clean-room
Independent implementation; no third-party chemistry source is copied.
