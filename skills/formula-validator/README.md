[English](README.md) · [中文说明](README_zh.md)

# formula-validator

SymPy D1-D5 layers (dimensional analysis, limit enumeration, numeric sampling, symbolic proof) merged with a pint physical-unit cross-check.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

- 246 cases

## Usage

Legacy CLI (unchanged from the original release):

```bash
python -m scripts.cli <validate|check|derive|matrix> --expr "F = m*a" --units F=N
```

Router adapter (thin wrapper — same code underneath):

```bash
python run.py --root <workspace> --action validate -- --expr "F = m*a" --units F=N --units m=kg --units a=m/s**2
```

## Migration note

The skill's internal tree is migrated byte-for-byte from the original
release (verified by SHA-256 on every test run). The only additions are the
root-level `run.py` adapter and `manifest.json`; `run.py` performs argument
mapping and gate emission only — all logic stays in the original modules,
wired through [`lib/chelate_core/adapter.py`](../../lib/chelate_core/adapter.py).

## Limitations

- The checker is deterministic, not a substitute for physical reasoning: a
  dimensionally consistent expression can still be physically wrong, and a
  dimensionally inconsistent one is always suspect.
- The symbolic layer can time out on deeply nested expressions; the
  numeric sampling layer remains the practical backstop.
- Scanned-image or hand-drawn equations are out of scope; input must be
  parseable symbolic text.

## License

MIT — see [LICENSE](LICENSE).
