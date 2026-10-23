---
name: document-evolution-tracker
description: Tracks version alignment and concept lineage. Computes paragraph-level diffs across document families to generate evolution timelines.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.1.1
  entry_point: python run.py
  python_requires: '>=3.10'
---





# document-evolution-tracker







A self-contained skill that tracks how a document **evolves across



versions**. Given a version family (a directory of `v1.md, v2.md, ...` or



timestamped files), it computes paragraph-level diffs between consecutive



versions and tracks a concept lineage (introduced / retained / modified /



dropped).







## MANDATORY WORKFLOW


## Dependency bootstrap (run on first use)

Before the first run, probe the runtime deps for this skill:

- **Core**: pure standard library — no install required.
- **Optional**: `PyYAML` (only when the config is a `.yaml`; JSON configs
  work with the standard library alone).

If `PyYAML` is missing and the config is YAML, tell the user and ask
whether to `pip install pyyaml`; install only after they confirm. Never
install into the global environment without explicit consent.







1. Load a config (`config/examples/family.json` as reference; YAML configs are
   also supported when PyYAML is installed).



2. Verify `versions_dir` contains at least two versioned files.



3. `python -m src.cli run --config <path> [--concepts "A,B"]`.



4. Report the transition count and point the user at



   `./evolution/evolution_<tracking_id>.{md,json}`.







## When to use







- A family of document versions (timestamped or sequentially named) must



  be compared over time.



- The user asks "track document changes", "version history", "what



  changed between drafts", or "concept lineage".



- A named concept (a term, a heading, a definition) must be traced across



  drafts to see when it was introduced, modified, or dropped.



- The evolution of a draft must be reported as a timeline rather than a



  single end-to-end diff.







## Usage examples







```bash



# Validate a config and see the discovered version files.



python -m src.cli validate --config config/examples/family.json



python -m src.cli versions --config config/examples/family.json







# Run the tracker; optionally name the concepts to follow.



python -m src.cli run --config config/examples/family.json --concepts "entropy,partition function"



```







Reports are written to `./evolution/evolution_<tracking_id>.{md,json}`;



the Markdown timeline is for readers, the JSON for programmatic use.







## Failure handling







- **Config invalid** (`validate` exits non-zero) - fix the reported field



  and re-validate; the naming scheme and `versions_dir` are the usual



  culprits.



- **Fewer than two versions discovered** - the run aborts; check the



  `version_naming` rule against the actual filenames and retry.



- **A concept never appears** - it is reported as absent across all



  versions, which is a valid result, not an error.



- **Unexpected exit code** - report the message verbatim; do not fall back



  to diffing the files by hand.







## Diff granularity







| Granularity | Split rule |



| --- | --- |



| `line` | Non-empty lines |



| `paragraph` (default) | Blank-line separated blocks |



| `sentence` | Punctuation-delimited sentences |







## Limitations







- Diffing is **structural** (block alignment via `difflib`), not semantic.



  A concept is "present" only when its exact phrase (case-insensitive)



  appears in the version's text.



- Custom naming schemes beyond `sequential` / `timestamp` are not



  supported.






