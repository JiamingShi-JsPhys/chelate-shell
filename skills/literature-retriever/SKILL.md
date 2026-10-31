---
name: literature-retriever
description: Searches arXiv by keyword phrase via the arxiv SDK and stores titles, abstracts, authors, dates, links, categories, DOI and journal references as JSON in process/literature/.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.2.0
  entry_point: python run.py
  python_requires: '>=3.10'
version: 1.2.0
---

# literature-retriever

This skill builds a **reading list from arXiv**: one query in, a structured JSON of papers out — title, abstract, authors, dates, entry id, PDF link, categories, DOI, journal reference. It answers "what exists on this topic", not "what is true".

**Core Loop:** the skill retrieves metadata; the agent reads and judges. *Never present an abstract as your own summary of results.*

## Quick Execution

**Do NOT read the source code. Run this exact command format directly:**

```bash
python run.py --root <WS> --action search --query "topological insulator" --max-results 10 [--sort-by relevance]
```

- `--root <WS>` = the user's workspace (absolute path). The result lands in
  `<WS>/process/literature/literature_<stamp>.json` — never in the skill's
  install dir.
- Valid `--action`: `search` (the only one).
- `--query` is a keyword phrase (required). `--max-results` caps the paper
  count; `--sort-by` accepts `relevance` or `lastUpdatedDate` (both default to
  `assets/config.yaml`).
- Verdicts: PASS = results retrieved; UNVERIFIED = `arxiv` missing or the
  network is unreachable; FAIL = the query returned nothing.

## When to use
- Scoping a new topic before writing or experimenting.
- Finding prior work to cite (then verify DOIs with reference-auditor).
- Checking whether an idea has already been published.

## When NOT to use (Out of Scope)
- Downloading full texts (metadata and abstracts only).
- Paywalled journals (arXiv preprints only; use Crossref via reference-auditor for DOI existence).
- Real-time alerting or citation graphing (single query, single call).

## Core Workflow
1. **Search:** `python run.py --root <workspace> --action search --query "topological insulator surface state" [--max-results 10] [--sort-by relevance]`
2. **Inspect:** read `process/literature/literature_<stamp>.json`; PASS means hits were stored, UNVERIFIED means zero hits or a network/API failure.
3. **Select:** pick papers by title/abstract; record entry ids for the user.
4. **Verify:** feed the DOIs you actually cite to reference-auditor before shipping.

## Hard Constraints (Red Lines)
- **Network failures are UNVERIFIED, never PASS or FAIL.** Offline means "unknown", not "no results".
- **Polite rate limiting is built in** (3 s delay, 2 retries); do not loop the skill to scrape.
- **Abstracts belong to their authors.** Quote with attribution; never rewrite them into claimed findings.
- **No API key, no account.** The public arXiv API only.

## Resources
- `run.py`: thin adapter (argparse + gate emission only).
- `lib/chelate_core/arxiv_search.py`: the search core shared by the repo.
- `assets/config.yaml`: default max_results and sort_by.
