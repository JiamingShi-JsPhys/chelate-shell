# data-profiler — reference

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `profile` | Profile the CSV | `--input <data.csv>` |

## Hard constraints

- **Missing values and outliers are REPORTED, not FAIL.**
- **FAIL means unreadable, empty or header-only.**
- **The input CSV is never modified.**

## Outputs

- `<WS>/process/data_profile_<stem>_<ts>.json` — the full profile.
- `<WS>/process/gates/data-profiler_<ts>.json` — the gate result.

## Failure handling

- An unreadable or empty CSV fails the gate.
- A header-only file is a FAIL (no rows to characterise).
- `pandas` missing → `UNVERIFIED`.

## Limitations

- Numeric-only outliers; non-numeric columns get counts only.
- The Tukey multiplier is `assets/config.yaml` (default 1.5).

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
