---
name: literature-retriever
version: 1.2.0
description: >
  Searches arXiv for a keyword phrase and stores the result as JSON in
  `process/`. Returns metadata only — titles, authors, identifiers, abstracts —
  and never downloads or redistributes the papers themselves.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# literature-retriever

Queries the arXiv API and normalises the response into one JSON file per
search. It does not rank by relevance for you beyond the API's own sort.

- **Stage:** `ingest` · **Sandbox:** no · **Dependencies:** `arxiv`

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action search --query "topological insulator"
```

- `--max-results` and `--sort-by {relevance,lastUpdatedDate,submittedDate}`
  default to `assets/config.yaml`.
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
| `search` | arXiv keyword search → JSON | `--query "..." [--max-results N] [--sort-by ...] [--outdir <dir>]` |

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
