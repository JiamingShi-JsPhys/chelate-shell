# literature-retriever

Search arXiv by keyword phrase and store the hits as JSON in the workspace
`process/` zone.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

```bash
pip install arxiv
```

## Usage

```bash
python run.py --root <workspace> --action search --query "topological insulator surface state"
python run.py --root <workspace> --action search --query "blackbody radiation" --max-results 20 --sort-by submittedDate
```

Defaults (`max_results`, `sort_by`) come from `assets/config.yaml`.

## Outputs

| Path | Content |
|------|---------|
| `process/literature/literature_<stamp>.json` | query, count, and per-paper records: title, abstract, authors, dates, entry id, PDF link, categories, DOI, journal reference |
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
