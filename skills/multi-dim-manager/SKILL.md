---
name: multi-dim-manager
version: 1.3.3
description: >
  Runs a parameter sweep over many rounds and keeps a hash-based audit trail.
  Snapshots the declared critical files before and after each round, records
  parameters, hashes, timestamps and status, and rolls any past round back
  non-destructively. Fires when a workflow repeats over a Cartesian parameter
  space or when rollback to an earlier round must stay possible.
metadata:
  version: 1.3.3
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# multi-dim-manager

Orchestrates repeated rounds: expands the parameter grid, snapshots declared
critical paths, records an auditable round log, and restores any past round.
It **never computes your domain result** — the per-round computation belongs to
your plugin.

- **Stage:** `workspace` · **Sandbox:** no · **Dependencies:** stdlib only (`PyYAML` only for `.yaml` configs; JSON configs need nothing)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action dryrun -- --config config.example.yaml
```

- Always `dryrun` first: it prints the full round plan with no side effect.
- `--config` is a workspace-relative or absolute config file (JSON or YAML).
- The gate lands in `<WS>/process/gates/multi-dim-manager_<ts>.json`.

## When to use

- A workflow repeats over a grid of parameters (rounds, seeds, conditions).
- Per-round snapshots of declared critical files must exist before and after each round.
- A full audit trail — parameters, hashes, timestamps, status — must be reproducible.
- The user must be able to roll back to any past round without destroying the live state.

## When NOT to use

- A single run with no parameter space — a plain script is enough.
- You want the manager to compute the result: it only orchestrates.

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
- **Snapshot only declared critical paths.** A full workdir copy is not what this does.
- **Rollback is non-destructive by default.** Without `--force` the live state is only read.

## Outputs

- `<WS>/process/gates/multi-dim-manager_<ts>.json` — the gate result.
- Per-round snapshot directories and the round log under `process/`.

## Failure handling

- A plugin exiting `1` marks the round `failed`; exit `2` marks it `error`.
- A malformed config (missing space, bad YAML, no `{OUT}`) aborts before any round runs.
- Rolling back to an unrecorded round, or one without a post-snapshot, is refused with a message.

## Limitations

- Determinism covers orchestration only; the plugin's own output is its responsibility.
- Files not declared as critical paths are never snapshotted.
- `.yaml` configs need `PyYAML`; JSON configs run on the standard library.

## Delivering results

This skill writes intermediates to `process/`. `results/` is filled only by
`python cli.py pipeline` after a human approved that exact plan.

- Do not copy a skill's output into `results/` yourself, and do not do it
  because the user asked for a shortcut: say that only `cli.py pipeline`
  writes there, offer to run the pipeline instead, and if they still insist,
  tell them `cli.py audit` will report the file as unapproved.
- Never set `CHELATE_HUMAN=1` and never run `cli.py approve` on the user's
  behalf. If an approval is needed, ask the human to issue it in their own
  terminal.
- Before telling the user a deliverable is ready — and after any write you
  make under `results/` — run `python cli.py audit --root <ws>`. Exit 1 means
  files there have no approval behind them: report that and name them, do not
  describe the state as delivered.
