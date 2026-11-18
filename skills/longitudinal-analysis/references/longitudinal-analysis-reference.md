# longitudinal-analysis — reference

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `validate` | Check the config | `--config <cfg>` |
| `list-steps` | Show the enabled steps and their R needs | `--config <cfg>` |
| `run` | Run the whole pipeline, or one step | `--config <cfg> [--step lmm]` |
| `export` | Export the generated tables | `--config <cfg> --format csv\|docx` |

## Hard constraints

- **Never hand-write Python to replace a skipped R step.** Report the skip.
- **Never install R.** List the missing packages and stop.
- **Report each step's own status**; do not merge them into one verdict.

## Outputs

- `<WS>/process/gates/longitudinal-analysis_<ts>.json` — the gate result.
- Per-step tables (CSV, or DOCX with `--format docx`) under `process/`.

## Failure handling

- A step reporting `skipped` means R or an R package is missing — list it and
  stop.
- An invalid config exits non-zero naming the field.
- A mid-pipeline error keeps earlier outputs and reports the failing step.

## Limitations

- R packages (`lme4`, `lavaan`, `emmeans`, `jsonlite`) must already be
  installed.
- The mediation bootstrap count is the user's choice (default 5000) and
  dominates wall-clock time.

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
