---
name: fulltext-extractor
description: Extracts text from a local PDF with pdfminer.six (pypdf fallback) and writes it into process/fulltext/ with page markers and a JSON metadata sidecar; degrades to UNVERIFIED on scanned/image PDFs.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.2.0
  entry_point: python run.py
  python_requires: '>=3.10'
version: 1.2.0
---

# fulltext-extractor

This skill turns a **local PDF into citable plain text**: one section per page with `===== PAGE i/n =====` markers, plus a JSON sidecar recording page counts and per-page character totals. It is the standard first hop of any document pipeline.

**Core Loop:** the skill extracts mechanically; the agent decides what the text means. *Never quote a page the extractor marked empty.*

## Quick Execution

**Do NOT read the source code. Run this exact command format directly:**

```bash
python run.py --root <WS> --action extract --input paper.pdf [--pages 1-5] [--outdir process/fulltext]
```

- `--root <WS>` = the user's workspace (absolute path). All artifacts land under
  `<WS>/process/fulltext/` — never in the skill's install dir.
- Valid `--action`: `extract` (the only one).
- `--input` is the source PDF (required). `--pages` selects 1-based pages,
  e.g. `1-5,8` (default: all). `--outdir` overrides the output directory.
- Outputs: `<stem>.txt` (one `===== PAGE i/n =====` section per page) and
  `<stem>.json` (page counts, per-page character totals).
- Verdicts: PASS = text extracted; UNVERIFIED = no text layer (scanned PDF) or
  a missing backend; FAIL = the input file does not exist.

## When to use
- A PDF must be read by downstream gates (reference-auditor, formula-validator).
- Batch-extracting local papers before a literature review.
- Checking whether a PDF has a text layer at all.

## When NOT to use (Out of Scope)
- Scanned/image PDFs without a text layer (result: UNVERIFIED, not a guess).
- Encrypted or DRM-protected PDFs (the backend will refuse; do not crack them).
- Editing, merging or re-flowing PDFs (this is extraction only).

## Core Workflow
1. **Extract:** `python run.py --root <workspace> --action extract --input paper.pdf [--pages 1-5]`
2. **Inspect:** read the gate line on stdout — PASS means text was found; UNVERIFIED means scan/no-text-layer or unreadable file.
3. **Cite:** downstream skills should reference `===== PAGE i/n =====` markers, never raw line numbers.
4. **Feed:** pass the `.txt` artifact to reference-auditor (DOIs) or formula-validator (equations).

## Hard Constraints (Red Lines)
- **Local only.** No network calls, ever; the PDF never leaves the machine.
- **Never fabricate text.** A page with no text layer stays empty — do not fill it from memory.
- **Empty extraction is UNVERIFIED, never PASS.** Zero characters cannot certify a document.
- **Page selection is 1-based inclusive** (`--pages 1-5,8`); an unparsable spec falls back to all pages.

## Resources
- `run.py`: thin adapter (argparse + gate emission only).
- `lib/chelate_core/pdf_text.py`: the extraction core shared by the repo.
- `assets/config.yaml`: default page selection and output directory.
