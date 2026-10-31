# bibtex-normalizer

Parse a `.bib` file, remove duplicate entries, and emit a normalized
bibliography plus a dedupe report into the workspace `process/` zone.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

```bash
pip install bibtexparser
```

## Usage

```bash
python run.py --root <workspace> --action normalize --input refs.bib
python run.py --root <workspace> --action normalize --input refs.bib --outdir process/bibtex
```

## Dedupe rule

Two entries collide when their **normalized citation key** OR their
**(lowercased title, year)** pair matches. The first occurrence wins; every
removal is itemized in the report with its reason, so
`total = unique + duplicates` always holds — including keys that
bibtexparser v2 collapses at parse time.

## Outputs

| Path | Content |
|------|---------|
| `process/bibtex/<stem>.normalized.bib` | cleaned bibliography, sorted by key, canonical field order |
| `process/bibtex/<stem>.report.json` | total / unique / duplicates with reasons / fields seen |
| `process/gates/bibtex-normalizer_<ts>.json` | gate result (PASS / UNVERIFIED / FAIL) |

## Gate semantics

- **PASS** — at least one unique entry emitted (EMPIRICAL evidence).
- **UNVERIFIED** — `bibtexparser` missing, or zero entries parsed.
- **FAIL** — input missing or unparseable.

## Design

`run.py` is a thin adapter; the parse/dedupe/format core (compatible with
bibtexparser v1 dicts and v2 Entry objects) lives in
[`lib/chelate_core/bibtex_norm.py`](../../lib/chelate_core/bibtex_norm.py).

## License

MIT — see [LICENSE](LICENSE).
