# security-guard — reference

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `gate` | Screen and emit a gate result | `--input <path\|text> [--mode text\|source\|auto] [--json]` |
| `scan` | Screen without gating | same arguments |

## Hard constraints

- **A screen, not a sandbox.** Never describe a pass as "safe".
- **Report the marker and its line**, never a rewritten file.

## Outputs

- `<WS>/process/gates/security-guard_<ts>.json` — the gate result with every
  hit listed.

## Failure handling

- An unreadable input exits non-zero with a clear message.
- A clean input is a pass with an explicit "no marker found" note.

## Limitations

- Marker and AST heuristics only; unknown attack shapes pass.
- It never modifies the screened file.

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
