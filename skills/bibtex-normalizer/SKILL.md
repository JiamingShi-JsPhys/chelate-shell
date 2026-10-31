---
name: bibtex-normalizer
description: Parses a .bib file with bibtexparser, removes duplicate entries by citation key or title+year, and emits a normalized bibliography plus a dedupe report into process/bibtex/.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.2.0
  entry_point: python run.py
  python_requires: '>=3.10'
version: 1.2.0
---

# bibtex-normalizer

This skill **cleans a bibliography without losing anything silently**: entries are deduplicated (citation key, or title+year), re-ordered by key, and re-emitted with a canonical field order — and every removal is itemized in a JSON report so `total = unique + duplicates` always holds.

**Core Loop:** the skill dedupes mechanically; the agent resolves ambiguous cases. *Never delete an entry the report flagged without looking at it.*

## Quick Execution

**Do NOT read the source code. Run this exact command format directly:**

```bash
python run.py --root <WS> --action normalize --input refs.bib [--outdir process/bibtex]
```

- `--root <WS>` = the user's workspace (absolute path). Artifacts land under
  `<WS>/process/bibtex/` — never in the skill's install dir.
- Valid `--action`: `normalize` (the only one).
- `--input` is the source `.bib` (required). `--outdir` overrides the output
  directory.
- Outputs: `<stem>.normalized.bib` (canonical field order, sorted by key) and
  `<stem>.report.json` (`total`, `unique`, `duplicates`, `fields_seen`) so
  `total = unique + duplicates` is always checkable.
- Verdicts: PASS = normalization completed; UNVERIFIED = `bibtexparser`
  missing; FAIL = the input is missing or unparseable.

## When to use
- Merging `.bib` files from several sources before submission.
- Enforcing a consistent entry format across a manuscript.
- Auditing a bibliography for accidental duplicates.

## When NOT to use (Out of Scope)
- Verifying that DOIs exist (use reference-auditor).
- Converting between citation styles (that is a bst/CSL job, not dedupe).
- Fixing wrong metadata automatically — the skill normalizes form, never facts.

## Core Workflow
1. **Normalize:** `python run.py --root <workspace> --action normalize --input refs.bib`
2. **Inspect:** read `<stem>.report.json` — every dropped entry carries a reason.
3. **Resolve:** for each duplicate, keep the richer entry by hand if the automatic first-wins choice is wrong.
4. **Re-run:** normalize again until the report shows zero unexpected duplicates.

## Hard Constraints (Red Lines)
- **First occurrence wins** — deterministic, but not smart; review the report.
- **Nothing disappears silently.** bibtexparser v2 collapsing repeated keys at parse time is reported as its own line item.
- **Form only.** Titles, authors and years are never rewritten or "corrected".
- **Unparseable input is FAIL, empty input is UNVERIFIED.**

## Resources
- `run.py`: thin adapter (argparse + gate emission only).
- `lib/chelate_core/bibtex_norm.py`: parse/dedupe/format core (bibtexparser v1 and v2).
- `assets/config.yaml`: default output directory.
