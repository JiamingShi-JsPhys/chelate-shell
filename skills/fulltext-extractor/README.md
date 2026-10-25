# fulltext-extractor

Extract text from a local PDF with pdfminer.six (pypdf fallback) and write it into the workspace
`process/` zone for downstream gates.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

```bash
pip install pdfminer.six   # primary backend
pip install pypdf        # fallback backend (used when pdfminer is absent)
```

## Usage

```bash
python run.py --root <workspace> --action extract --input paper.pdf
python run.py --root <workspace> --action extract --input paper.pdf --pages 1-5,8
python run.py --root <workspace> --action extract --input paper.pdf --outdir process/fulltext
```

Defaults come from `assets/config.yaml` (page selection, output directory);
CLI flags override them.

## Outputs

| Path | Content |
|------|---------|
| `process/fulltext/<stem>.txt` | full text, one `===== PAGE i/n =====` section per page |
| `process/fulltext/<stem>.json` | source, page counts, per-page char totals, metadata |
| `process/gates/fulltext-extractor_<ts>.json` | gate result (PASS / UNVERIFIED) |

## Gate semantics

- **PASS** — text extracted (EMPIRICAL evidence).
- **UNVERIFIED** — neither pdfminer.six nor pypdf is importable, file unreadable, or zero characters
  (scanned PDF without a text layer). The pipeline continues; nothing is
  faked.
- **FAIL** — the input path does not exist.

## Design

`run.py` is a thin adapter: it parses arguments and emits the gate. All
extraction logic lives in [`lib/chelate_core/pdf_text.py`](../../lib/chelate_core/pdf_text.py).

## License

MIT — see [LICENSE](LICENSE).
