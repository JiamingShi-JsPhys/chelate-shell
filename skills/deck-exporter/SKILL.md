---
name: deck-exporter
version: 1.4.0
description: >
  Renders process/*.md into one self-contained HTML deck; absolute paths
  refuse the export.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# deck-exporter

The last step before a report leaves the machine: one file that opens
anywhere, and that does not carry the author's directory layout with it.

- **Stage:** `processors` · **Sandbox:** no · **Dependencies:** none (standard library)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action build --name deck
```

- Reads `process/*.md`, in filename order. The first `# ` heading becomes the
  title slide; every `## ` heading starts a slide.
- Writes `process/deck/<name>.html` and the report beside it.

## What the deck will not contain

- **An absolute path.** A Windows drive, a UNC prefix, `file://`, `/home/…` or
  `/Users/…` anywhere in the output refuses the whole export — a sanitiser
  that half-works is worse than a refusal.
- **A network reference.** Images are `data:` URIs, the CSS is inline, there is
  no `<script>`; the deck opens with no network.
- **A silent omission.** A missing, remote, unsupported or over-2-MiB image
  becomes its alt text *and* is counted in the report.

## Verdicts

| Status | When |
| --- | --- |
| `PASS` | the deck was written; the reason counts slides and images |
| `FAIL` | the deck would embed an absolute path |
| `UNVERIFIED` | there is no Markdown in `process/` to export |

## When to use

- A report is finished and has to be shown to someone who does not have this
  workspace, this tool or this network.
- A figure has to travel with the text that explains it, in one file.

## When NOT to use

- You need a `.tex` or a PDF — that is `latex-exporter`, and a PDF needs a
  toolchain this skill deliberately does not require.
- You want to edit the slides afterwards: the HTML is generated, so edit the
  Markdown and re-export.

## More

- [outputs, failure handling and limits](references/deck-exporter-reference.md)
