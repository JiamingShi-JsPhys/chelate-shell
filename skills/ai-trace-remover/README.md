# ai-trace-remover

Template-sentence removal and a 0-100 AI-likeness score, with a clean-room English lexicon plus the full Chinese lexicon and scoring rubric.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Usage

Legacy CLI (unchanged from v1.0.0):

```bash
python -m src.cli <file|-> --json
```

Router adapter (v1.1.0, thin wrapper — same code underneath):

```bash
python run.py --root <workspace> --action scan -- <manuscript>
```

## v1.1.0 migration note

The skill's internal tree is migrated byte-for-byte from v1.0.0 (verified
by SHA-256 on every test run). The only additions are the root-level
`run.py` adapter and `manifest.json`; `run.py` performs argument mapping
and gate emission only — all logic stays in the original modules, wired
through [`lib/chelate_core/adapter.py`](../../lib/chelate_core/adapter.py).

## License

MIT — see [LICENSE](LICENSE).
