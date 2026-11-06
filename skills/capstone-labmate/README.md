# capstone-labmate

`.cap` binary parsing and CSV/JSON conversion, PDF-to-`.cap` preconfiguration, and watermarked draft reports with provenance marking. All processing is local.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Usage

Legacy CLI (unchanged from v1.0.0):

```bash
python scripts/process_cap.py --input x.cap --outdir <dir>
```

Router adapter (v1.1.0, thin wrapper — same code underneath):

```bash
python run.py --root <workspace> --action ingest -- --input x.cap --outdir <dir>
```

## v1.1.0 migration note

The skill's internal tree is migrated byte-for-byte from v1.0.0 (verified
by SHA-256 on every test run). The only additions are the root-level
`run.py` adapter and `manifest.json`; `run.py` performs argument mapping
and gate emission only — all logic stays in the original modules, wired
through [`lib/chelate_core/adapter.py`](../../lib/chelate_core/adapter.py).

## License

MIT — see [LICENSE](LICENSE).
