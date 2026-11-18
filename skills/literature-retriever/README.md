# literature-retriever

Search arXiv, Crossref or PubMed — or resolve a DOI — and store the hits as
JSON (optionally BibTeX) in the workspace `process/` zone.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

```bash
pip install arxiv      # only needed for --source arxiv
```

Crossref, PubMed and DOI resolution use the standard library and need
nothing installed.

## Usage

```bash
python run.py --root <workspace> --action search --query "topological insulator surface state"
python run.py --root <workspace> --action search --query "blackbody radiation" --max-results 20 --sort-by submittedDate
python run.py --root <workspace> --action search --query "twisted bilayer graphene" --source crossref --format bibtex
python run.py --root <workspace> --action search --query "graphene" --source pubmed
python run.py --root <workspace> --action search --query 10.1038/nature14539 --source doi
```

Defaults (`max_results`, `sort_by`) come from `assets/config.yaml`.

Crossref is asked for literature types only (journal articles, chapters,
proceedings, preprints, dissertations, reports), and anything else that slips
through is filtered out — a plain phrase query otherwise returns figure
captions and subject-heading entries as its top hits. Dates are normalised to
`YYYY[-MM[-DD]]` across all sources, so records from different databases sort
together.

## Outputs

| Path | Content |
|------|---------|
| `process/literature/literature_<stamp>.json` | query, source, count, and per-paper records: title, abstract, authors, dates, entry id, PDF link, categories, DOI, journal reference |
| `process/literature/literature_<stamp>.bib` | `--format bibtex\|both` — one `@article` per record, unique keys |
| `process/gates/literature-retriever_<ts>.json` | gate result (PASS / UNVERIFIED) |

## Gate semantics

- **PASS** — papers retrieved and stored (EMPIRICAL evidence).
- **UNVERIFIED** — the `arxiv` SDK is missing, the network/API call failed,
  or the query returned zero hits. A network outage never looks like
  "no results".
- **FAIL** — reserved for contract violations (none expected).

## Design

`run.py` is a thin adapter; the search core (polite 3 s delay, 2 retries,
normalized records) lives in
[`lib/chelate_core/arxiv_search.py`](../../lib/chelate_core/arxiv_search.py).

## License

MIT — see [LICENSE](LICENSE).
