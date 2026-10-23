# multi-dim-manager

Cartesian parameter-space expansion, SHA-256 file snapshots per round, hash audit logs, and safe rollback to any past round.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Usage

Legacy CLI (unchanged from v1.0.0):

```bash
python -m scripts.run <run|dryrun|rollback|summary|verify> --config <yaml>
```

Router adapter (v1.1.0, thin wrapper — same code underneath):

```bash
python run.py --root <workspace> --action dryrun -- --config config.example.yaml
```

## v1.1.0 migration note

The skill's internal tree is migrated byte-for-byte from v1.0.0 (verified
by SHA-256 on every test run). The only additions are the root-level
`run.py` adapter and `manifest.json`; `run.py` performs argument mapping
and gate emission only — all logic stays in the original modules, wired
through [`lib/chelate_core/adapter.py`](../../lib/chelate_core/adapter.py).

## License

MIT — see [LICENSE](LICENSE).
