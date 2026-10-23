---
name: multi-dim-manager
description: State manager for multi-round parameter sweeps. Handles Cartesian expansion, per-round snapshots, audit logging, and non-destructive rollbacks.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.1.0
  entry_point: python run.py
  python_requires: '>=3.10'
---



# multi-dim-manager







A self-contained skill that brings order to the *state* of long-running,



multi-dimensional computational experiments. Your compute plugin does the



math; this skill manages the surrounding chaos: iteration, snapshots,



audit, and rollback.







> The skill only orchestrates. It never computes a result itself - every



> number comes from your plugin.







## When to use







- A workflow runs many rounds over a parameter space (a Cartesian grid of



  dimensions) and needs each round's state recorded.



- Per-round snapshots of declared critical files are required before and



  after each round.



- A full audit trail (params, hashes, timestamps, status) must exist for



  every round.



- The user must be able to roll back to any past round, non-destructively.



- Typical shapes: longitudinal studies, parameter scans, or symbolic /



  numerical sweeps calling external solvers (Mathematica, GAP, SymPy,



  custom scripts).







## MANDATORY WORKFLOW


## Dependency bootstrap (run on first use)

Before the first run, probe the runtime deps for this skill:

- **Core**: pure standard library — no install required.
- **Optional**: `PyYAML` (only when the config is a `.yaml`; JSON configs
  work with the standard library alone).

If `PyYAML` is missing and the user's config is YAML, tell them and ask
whether to `pip install pyyaml`; install only after they confirm. Never
install into the global environment without explicit consent.







Follow these steps in order whenever the user asks to run, inspect, or



recover a multi-dimensional experiment.







1. **Load the config.** Read the experiment config (`config.example.yaml`



   is the template). Confirm `param_space.dimensions`, `critical_paths`,



   and the `plugin.command` are present. If YAML is used, PyYAML must be



   installed; otherwise use JSON.



2. **Expand the space.** Enumerate the Cartesian product of all



   dimensions. Report the total round count to the user before executing.



3. **Prefer a dry run.** Run `python scripts/run.py dryrun --config <cfg>`



   so the user sees the full plan (every parameter combination) without



   any side effect. Only proceed to execution after they confirm.



4. **Execute the sweep.** Run `python scripts/run.py run --config <cfg>`.



   For each round, in order: snapshot the declared critical paths



   *before*, invoke the plugin, snapshot *after*, and append one audit



   record.



5. **React to failure correctly.** If a round's plugin exits non-zero,



   record its status (`failed`/`error`). When `auto_rollback` is on,



   recover the last successful round's post-state into the working



   directory so later rounds start clean; this recovery is itself



   audited. Do not stop the whole sweep on a single bad combination.



6. **Summarize.** After the sweep the skill writes `results_summary.csv`,



   `results_summary.md`, `report_draft.md`, and `run_metadata.json` under



   the output directory. Point the user at these.



7. **Recover on request.** To restore a past round, run



   `python scripts/run.py rollback --config <cfg> --round <N>`. By default



   it restores into a NEW directory; only add `--force` when the user



   explicitly wants the live working directory overwritten.







## Hard constraints







- **Never compute the result yourself.** All domain math belongs in the



  user plugin. The skill only calls it and records the contract outcome.



- **Snapshot only declared critical paths.** A full working-directory copy



  is never taken; content is stored addressed by hash, so unchanged files



  cost nothing extra.



- **Rollback is non-destructive by default.** Without `--force` the live



  working directory is never modified; the restored state lands in a new



  directory. Every rollback (manual or automatic) is written to the audit



  log.



- **Determinism is the user's promise.** The skill guarantees the



  *orchestration* is reproducible (same params -> same recorded plan,



  same hashes). It cannot make a non-deterministic plugin deterministic;



  see Limitations.







## Usage examples







```bash



# Print the full round plan without any side effect (always do this first).



python scripts/run.py dryrun --config config.example.yaml







# Execute the sweep.



python scripts/run.py run --config config.example.yaml







# Restore a past round (into a NEW directory unless --force).



python scripts/run.py rollback --config config.example.yaml --round 7







# Regenerate the summaries, or verify one round's outcome.



python scripts/run.py summary --config config.example.yaml



python scripts/run.py verify --config config.example.yaml --round 7



```







## Plugin contract







The manager launches exactly one shell command per round:







```



python your_plugin.py --params {PARAMS} --out {OUT}



```







- `{PARAMS}` - path to a JSON file with this round's parameter



  combination.



- `{OUT}` - path the plugin MUST write its result JSON to.



- Exit codes: `0` success, `1` assertion failed / check failed, `2` error



  or skipped.







Any external solver (Mathematica, GAP, a Python LMM script) is wrapped to



honor this contract: it reads the params file and writes a result file.



The skill does not care what is computed.







## Failure handling







- A round whose plugin exits `1` is marked `failed`; exit `2` is `error`.



  Both are kept in the audit log; the sweep continues.



- `config` errors (missing space, bad YAML, missing `{OUT}`) abort before



  any side effect and print a clear message (exit code 2).



- `rollback` to a round that was never recorded, or has no post-snapshot,



  fails with a clear error rather than corrupting state.







## Limitations







- **Determinism is orchestration-layer only.** The manager records hashes



  and replays the same plan for the same params, but it cannot enforce



  that the plugin is deterministic. If the plugin touches the network,



  uses random seeds, or reads the wall clock, the same inputs may yield



  different outputs. Declare such non-determinism in the plugin yourself.



- **Critical paths must be declared up front.** Files not listed in



  `critical_paths` are never snapshotted and therefore cannot be rolled



  back.



- **Golden-output verification is v0.2.** The current verifier only



  checks the plugin contract (exit 0 + result file present). Comparison



  against a known expected output is planned but not yet implemented.



- **YAML configs need PyYAML.** JSON configs work with the standard



  library alone.






