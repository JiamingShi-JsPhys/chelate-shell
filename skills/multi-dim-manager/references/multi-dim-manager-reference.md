# multi-dim-manager — reference

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `dryrun` | Print the round plan, no side effect | `--config <cfg>` |
| `run` | Execute the sweep | `--config <cfg>` |
| `rollback` | Restore a past round into a new directory | `--config <cfg> --round N [--force]` |
| `summary` | Regenerate the round summaries | `--config <cfg>` |
| `verify` | Check one round's recorded outcome | `--config <cfg> --round N` |

## Hard constraints

- **Never compute the result yourself.** Domain math belongs in the plugin.
- **Snapshot only declared critical paths.** A full workdir copy is not what
  this does.
- **Rollback is non-destructive by default.** Without `--force` the live state
  is only read.

## Outputs

- `<WS>/process/gates/multi-dim-manager_<ts>.json` — the gate result.
- Per-round snapshot directories and the round log under `process/`.

## Failure handling

- A plugin exiting `1` marks the round `failed`; exit `2` marks it `error`.
- A malformed config (missing space, bad YAML, no `{OUT}`) aborts before any
  round runs.
- Rolling back to an unrecorded round, or one without a post-snapshot, is
  refused with a message.

## Limitations

- Determinism covers orchestration only; the plugin's own output is its
  responsibility.
- Files not declared as critical paths are never snapshotted.
- `.yaml` configs need `PyYAML`; JSON configs run on the standard library.

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
