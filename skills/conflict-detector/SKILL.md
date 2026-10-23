---
name: conflict-detector
description: Cross-document contradiction engine. Compares entities, clauses, and arguments across multiple sources to output structured JSON/CSV conflict reports.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.1.1
  entry_point: python run.py
  python_requires: '>=3.10'
---



# conflict-detector







A self-contained skill that finds **contradictions across a set of



documents**. Each document is loaded (path / inline text / inline JSON),



its facts are extracted, and a cross-document rule engine pairs claims by



canonical key and flags mismatches.







## MANDATORY WORKFLOW


## Dependency bootstrap (run on first use)

Before the first run, probe the runtime deps for this skill:

- **Core**: pure standard library — no install required.
- **Optional**: `PyYAML` (only when the config / input is a `.yaml`; JSON
  inputs work with the standard library alone).

If `PyYAML` is missing and the input is YAML, tell the user and ask
whether to `pip install pyyaml`; install only after they confirm. Never
install into the global environment without explicit consent.







1. Load the YAML config (`config/examples/two_docs.yaml` as reference).



2. Verify every `documents[].value` / `documents[].path` is reachable.



3. `python -m src.cli run --config <path> [--format json,csv,md]`.



4. Report the per-level conflict count and point the user at



   `./conflicts/conflicts_<run_id>.*`.







## When to use







- Two or more documents, datasets, or extracted fact tables must be checked



  against each other for contradictions.



- The user asks to "detect conflicts", "find contradictions", "cross-check



  claims", or asks "do these documents agree".



- A single claim (a number, a status, a named fact) appears in several



  sources and must be compared across them.



- A fact table extracted from documents must be audited for internal



  consistency before it is relied on.







## Usage examples







```bash



# Validate a config before running it (fast, no report written).



python -m src.cli validate --config config/examples/two_docs.yaml







# List the document sources a config resolves to.



python -m src.cli list-docs --config config/examples/two_docs.yaml







# Run a detection; pick the output formats (default: json).



python -m src.cli run --config config/examples/two_docs.yaml --format json,csv,md



```







Reports are written to `./conflicts/conflicts_<run_id>.{json,csv,md}`; the



JSON is the machine-readable contract.







## Failure handling







- **Config invalid** (`validate` exits non-zero) - fix the reported field



  and re-validate; do not hand-edit around a schema violation.



- **A document source is unreachable** - the run aborts naming the



  offending `documents[]` entry; verify the path or inline value, retry.



- **No conflicts found** - a valid, reportable result (an empty report),



  not an error; say so explicitly instead of re-running.



- **Unexpected exit code** - report the message verbatim; do not fall back



  to comparing the documents by hand.







## Detection levels







| Level | Kind | Severity | Example |



| --- | --- | --- | --- |



| `entity` | `numeric_mismatch`, `boolean` | high | `speed = 10` vs `speed = 20` |



| `clause` | `categorical` | medium | `status = "active"` vs `status = "archived"` |



| `argument` | `categorical` (text) | low | free-text lines that disagree |







## Limitations







- Extraction is key-value oriented; free-text paragraphs only participate



  at the `argument` level (line-level comparison).



- Unit normalisation is table-driven (`unit_map`); custom unit rules must



  be supplied via the config.






