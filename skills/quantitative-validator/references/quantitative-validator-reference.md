# quantitative-validator — reference

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `gate` | Balance / conservation check | `--formula "..." \| --input <file>` |

## Hard constraints

- **Never balance the equation by hand.** The verdict comes from the tool.
- **An unbalanced equation is a FAIL**, not a hint.

## Outputs

- `<WS>/process/gates/quantitative-validator_<ts>.json` — the gate result with
  the per-element diff.

## Failure handling

- An unparseable formula fails the gate with the offending token.
- `rdkit` missing → `UNVERIFIED` (the sandbox reports it, the pipeline
  continues).

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
- Never set `CHELATE_UNSAFE_AUTO_APPROVE=1` (formerly `CHELATE_HUMAN`) and
  never run `cli.py approve` on the user's behalf. If an approval is needed,
  ask the human to issue it in their own terminal.
- Before telling the user a deliverable is ready — and after any write you
  make under `results/` — run `python cli.py audit --root <ws>`. Exit 1 means
  files there have no approval behind them: report that and name them, do not
  describe the state as delivered.
