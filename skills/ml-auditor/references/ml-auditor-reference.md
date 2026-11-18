# ml-auditor — reference

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `gate` | Leakage + label-error audit | `--input\|--data <csv> [--label <col>]` |

## Hard constraints

- **Never modify the dataset.** The audit is read-only.
- **Report leakage, do not silently drop the feature.**

## Outputs

- `<WS>/process/gates/ml-auditor_<ts>.json` — the gate result with suspects
  listed.

## Failure handling

- A CSV without a usable target fails the gate.
- `scikit-learn` missing → `UNVERIFIED`.

## Limitations

- Heuristic leakage detection; every suspect must be reviewed.
- A column booked after the outcome is caught only in its clear shape (one
  class on a single value, the other spread over many). Read the column list
  against the study timeline; no statistic proves a column's provenance.
- The label scan needs signal. When the features predict no better than the
  majority class, `UNVERIFIED` is returned and no label verdict is possible.
- `cleanlab` is optional and only refines the label report.

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
