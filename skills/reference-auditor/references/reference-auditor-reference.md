# reference-auditor — reference

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `audit` | Extract and verify every DOI | `--input <draft> \| --text "..." [--timeout N]` |

## Hard constraints

- **A non-existent DOI is a FAIL**, never a warning.
- **A network error is `unknown`**, never a pass.
- **Never rewrite the DOI.** Report it exactly as found.

## Outputs

- `<WS>/process/gates/reference-auditor_<ts>.json` — the gate result.
- A per-DOI verification table under `process/`.

## Failure handling

- Crossref unreachable → `UNVERIFIED`/`unknown` with the HTTP error.
- A draft with no DOI yields a pass with an explicit "nothing to check" note.

## Limitations

- Existence only — citation correctness stays the author's responsibility.
- One HTTP request per DOI; a large bibliography is rate-limited.

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
