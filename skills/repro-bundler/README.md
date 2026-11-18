# repro-bundler

Package a run's products, gate records and skill versions into a deterministic
zip — and verify a bundle handed to you without extracting it.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

Nothing. Standard library only (`zipfile`, `hashlib`).

## Usage

```bash
python run.py --root <workspace> --action bundle --name paper-x
python run.py --root <workspace> --action bundle --name paper-x --include process/bands.csv process/figure.pdf
python run.py --root <workspace> --action verify --bundle process/repro/paper-x-<stamp>.zip
```

## Bundle layout

```
paper-x-<stamp>.zip
├── manifest.json        files + SHA-256, gates, skill versions, Python/platform
└── files/
    ├── process/bands.csv
    └── process/figure.pdf
```

## Determinism

Entries are sorted, timestamps fixed at 1980-01-01, modes fixed at 0644, and
the manifest is written with sorted keys. Two bundles of unchanged inputs have
identical bytes.

## Verification refuses

- absolute paths and drive letters (`C:\`, `/etc`)
- `..` components
- symlink entries
- missing, mismatched or unexpected entries

Nothing is extracted: entries are read in memory and hashed.

## Outputs

| Path | Content |
|------|---------|
| `process/repro/<name>-<stamp>.zip` | the bundle |
| `process/gates/repro-bundler_<ts>.json` | gate result (PASS / FAIL / UNVERIFIED) |
