---
name: multi-dim-manager
version: 1.4.0
description: >
  Parameter sweep with a hash-based audit trail and non-destructive rollback
  of any round.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# multi-dim-manager

Orchestrates repeated rounds: expands the parameter grid, snapshots declared
critical paths, records an auditable round log, and restores any past round.
It **never computes your domain result** — the per-round computation belongs to
your plugin and stays under `output/` as the config declares.

- **Stage:** `workspace` · **Sandbox:** no · **Dependencies:** stdlib only (`PyYAML` only for `.yaml` configs; JSON configs need nothing)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action dryrun -- --config config.example.yaml
```

- Always `dryrun` first: it prints the full round plan with no side effect.
- **Never compute the result yourself.** Domain math belongs in the plugin;
  snapshot only declared critical paths; rollback is non-destructive unless
  `--force`.
- The gate lands in `<WS>/process/gates/multi-dim-manager_<ts>.json`.

## When to use

- A workflow repeats over a grid of parameters (rounds, seeds, conditions).
- Per-round snapshots of declared critical files must exist before and after
  each round.
- A full audit trail — parameters, hashes, timestamps, status — must be
  reproducible, and rollback to any past round must stay possible.

## When NOT to use

- A single run with no parameter space — a plain script is enough.
- You want the manager to compute the result: it only orchestrates.

## More

- [actions, outputs, failure handling and limits](references/multi-dim-manager-reference.md)
