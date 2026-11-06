[English](README.md) · [中文说明](README_zh.md)

# multi-dim-manager

Cartesian parameter-space expansion, SHA-256 file snapshots per round, hash audit logs, and safe rollback to any past round.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

The test suite covers 87 cases.

## Usage

Legacy CLI (unchanged from the original release):

```bash
python -m scripts.run <run|dryrun|rollback|summary|verify> --config <yaml>
```

Router adapter (thin wrapper — same code underneath):

```bash
python run.py --root <workspace> --action dryrun -- --config config.example.yaml
```

## Migration note

The skill's internal tree is migrated byte-for-byte from the original
release (verified by SHA-256 on every test run). The only additions are the
root-level `run.py` adapter and `manifest.json`; `run.py` performs argument
mapping and gate emission only — all logic stays in the original modules,
wired through [`lib/chelate_core/adapter.py`](../../lib/chelate_core/adapter.py).

## Limitations

- Snapshots are content-addressed (SHA-256); a parameter sweep that rewrites
  the same file twice keeps only the newest digest — history is per-round,
  not per-keystroke.
- Rollback restores file bytes and round state; it does not undo side
  effects outside the workspace (network calls, external jobs).
- Large Cartesian spaces grow combinatorially; the planner reports the
  estimated round count before execution so you can cap dimensions.

## License

MIT — see [LICENSE](LICENSE).
