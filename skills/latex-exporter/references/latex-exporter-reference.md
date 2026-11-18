# latex-exporter — reference

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `export` | Merge reports + figures into one `.tex` | `[--name report.tex]` |
| `process` | Alias of `export` | `[--name report.tex]` |

## Hard constraints

- **Stdlib only.** Never introduce a pandoc dependency.
- **Never rewrite the prose** — the Markdown is embedded as authored.

## Outputs

- `<WS>/process/latex/merged_report.tex` (or `--name`) — the merged document.
- `<WS>/process/gates/latex-exporter_<ts>.json` — the gate result.

## Failure handling

- No Markdown to merge fails the gate with a clear message.
- A missing figure file is reported, and the include is written commented out.

## Limitations

- No compilation step.
- Only Markdown and the common image formats are handled.

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
