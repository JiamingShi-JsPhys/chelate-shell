---
name: reference-auditor
description: Extracts DOIs from a draft manuscript and verifies each against the Crossref REST API; any non-existent DOI fails the gate and terminates the pipeline.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.1.0
  entry_point: python run.py
  python_requires: '>=3.10'
---

# reference-auditor

This skill is the **anti-fabrication gate for references**: it pulls every DOI out of a draft and asks Crossref whether each one exists. A DOI that returns 404 is a hard FAIL — the pipeline stops and the draft stays locked in `process/`.

**Core Loop:** the skill checks existence; the agent fixes citations. *Never edit the draft to remove the DOI instead of fixing the reference.*

## When to use
- Before shipping any manuscript with DOI references.
- Auditing a bibliography received from collaborators or an LLM.
- As a pipeline gate after fulltext-extractor produced a draft.

## When NOT to use (Out of Scope)
- References without DOIs (books, arXiv IDs, private reports) — out of scope by design.
- Citation formatting or style checking.
- Bibliometrics (citation counts, impact factors).

## Core Workflow
1. **Audit:** `python run.py --root <workspace> --action audit --input draft.md`
2. **Read the gate:** FAIL names every non-existent DOI; PASS means all resolve; UNVERIFIED means network failure or no DOIs found.
3. **Fix:** for each failed DOI, correct it, replace the reference, or delete the claim that needed it.
4. **Re-run:** audit again until PASS — a FAIL must never be argued away.

## Hard Constraints (Red Lines)
- **HTTP 404 is FAIL, full stop.** A fabricated reference can never ship.
- **Network errors are UNVERIFIED, never PASS.** Offline means "unknown"; retry later.
- **No API key, no account.** The public Crossref API with a politeness mailto only.
- **The draft is read, never written.** The skill audits; the agent (or human) edits.

## Resources
- `run.py`: thin adapter (argparse + gate emission only).
- `lib/chelate_core/doi_audit.py`: DOI extraction + Crossref verification core.
- `assets/config.yaml`: per-DOI HTTP timeout.
