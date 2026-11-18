---
name: literature-retriever
version: 1.4.0
description: >
  Searches arXiv, Crossref or PubMed, or resolves a DOI; stores metadata
  JSON, optionally BibTeX.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# literature-retriever

Queries one bibliographic source and normalises the response into one JSON
file per search. Four sources: `arxiv` (SDK), `crossref` and `pubmed`
(standard library), and `doi` (resolve one DOI through Crossref). It does not
rank for you beyond the API's own ordering.

- **Stage:** `ingest` · **Sandbox:** no · **Dependencies:** `arxiv` (only for
  `--source arxiv`; the other three need nothing installed)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action search --query "topological insulator"
python run.py --root <WS> --action search --query "twisted bilayer graphene" --source crossref --format bibtex
python run.py --root <WS> --action search --query 10.1038/nature14539 --source doi
```

- `--source {arxiv,crossref,pubmed,doi}` defaults to `arxiv`.
- `--max-results` and `--sort-by {relevance,lastUpdatedDate,submittedDate}`
  default to `assets/config.yaml`; `--sort-by` is arXiv-only.
- `--format {json,bibtex,both}` writes a `.bib` next to the JSON.
- Dates are normalised to `YYYY[-MM[-DD]]` whichever source answered.
- Results land in `<WS>/process/literature/`, the gate in `<WS>/process/gates/`.

## When to use

- A topic needs a first pass of candidate papers.
- A keyword search result must be captured as structured JSON for later stages.

## When NOT to use

- You need the full text — use `fulltext-extractor` on a PDF you have.
- The citation must be verified — that is `reference-auditor`'s job.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `search` | keyword search (or one DOI) → JSON (+ `.bib`) | `--query "..." [--source arxiv\|crossref\|pubmed\|doi] [--max-results N] [--sort-by ...] [--format json\|bibtex\|both] [--outdir <dir>]` |

## Hard constraints

- **Metadata only.** No PDF is downloaded.
- **The API's answer is reported as-is.** No invented hits.

## Outputs

- `<WS>/process/literature/<slug>_<ts>.json` — the normalised result set.
- `<WS>/process/gates/literature-retriever_<ts>.json` — the gate result.

## Failure handling

- A network failure fails the gate with the HTTP error.
- `arxiv` missing → `UNVERIFIED` with an install hint.

## Limitations

- arXiv only; other indexes are out of scope.
- Ranking is the API's, not a relevance model.

## Delivering results

This skill writes intermediates to `process/`. `results/` is filled only by
`python cli.py pipeline` after a human approved that exact plan.

- Do not copy a skill's output into `results/` yourself, and do not do it
  because the user asked for a shortcut: say that only `cli.py pipeline`
  writes there, offer to run the pipeline instead, and if they still insist,
  tell them `cli.py audit` will report the file as unapproved.
- Never set `CHELATE_UNSAFE_AUTO_APPROVE=1` (formerly `CHELATE_HUMAN`) and never run `cli.py approve` on the user's
  behalf. If an approval is needed, ask the human to issue it in their own
  terminal.
- Before telling the user a deliverable is ready — and after any write you
  make under `results/` — run `python cli.py audit --root <ws>`. Exit 1 means
  files there have no approval behind them: report that and name them, do not
  describe the state as delivered.
