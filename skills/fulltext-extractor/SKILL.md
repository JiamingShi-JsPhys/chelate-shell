---
name: fulltext-extractor
version: 1.2.0
description: >
  Extracts the text of a local PDF into `process/` so later stages can read
  plain text instead of a binary. Uses `pdfminer.six` with a `pypdf` fallback,
  and can be limited to selected pages.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# fulltext-extractor

Converts a PDF into text files under `process/fulltext/`. It does not
summarise, translate or interpret the text.

- **Stage:** `ingest` · **Sandbox:** no · **Dependencies:** `pdfminer.six` or `pypdf`

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action extract --input paper.pdf
```

- `--pages '1-5,8'` selects 1-based pages; omit it to extract everything.
- The text lands in `<WS>/process/fulltext/`, the gate in `<WS>/process/gates/`.

## When to use

- A PDF must become text before an ingest or gate stage can read it.
- Only a page range is needed from a long document.

## When NOT to use

- The file is already text or Markdown.
- You need OCR of a scanned image-only PDF — this is not an OCR tool.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `extract` | PDF → text files | `--input <pdf> [--pages 1-5,8] [--outdir <dir>]` |

## Hard constraints

- **Read-only on the source.** The PDF is never modified.
- **No interpretation.** Extracted text is passed through unchanged.

## Outputs

- `<WS>/process/fulltext/<stem>.txt` — one file per input (plus a JSON index).
- `<WS>/process/gates/fulltext-extractor_<ts>.json` — the gate result.

## Failure handling

- An unreadable PDF fails the gate with the backend's message.
- Neither backend installed → `UNVERIFIED` with an install hint.

## Limitations

- Image-only PDFs yield no text (no OCR).
- Layout and tables are flattened to reading order.
