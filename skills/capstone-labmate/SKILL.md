---
name: capstone-labmate
version: 1.2.0
description: >
  Parses PASCO Capstone `.cap` files into down-sampled CSV/JSON, pre-configures
  a Capstone run from a lab manual PDF, and drafts a watermarked lab report. It
  is an interoperability helper for teaching; it never fabricates data and
  never claims the experiment was performed by the tool.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# capstone-labmate

Turns Capstone's binary `.cap` output into analysis-ready tables and helps with
the pre-lab and post-lab paperwork. All parsing runs locally.

- **Stage:** `ingest` · **Sandbox:** no · **Dependencies:** stdlib only (`numpy`/`matplotlib`/`pypdf` add optional paths)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action ingest -- <file.cap>
```

- `ingest` and `process` both map to the `.cap` parser; `preconfigure` reads a
  PDF lab manual; `draft` writes the watermarked report.
- Outputs land in `<WS>/process/stage_a|stage_c|stage_d` — never in the skill
  directory.

## When to use

- A `.cap` file must become CSV/JSON for analysis.
- A lab manual PDF must be turned into a preconfigured Capstone run.
- A draft lab report must be generated from already-collected data.

## When NOT to use

- No data was collected — the tool never invents measurements.
- The user wants the AI to run the experiment; it is physically isolated from that stage.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `ingest` | `.cap` → down-sampled CSV/JSON | `<file.cap>` |
| `process` | Alias of `ingest` | `<file.cap>` |
| `preconfigure` | Lab manual PDF → preconfigured `.cap` | `<file.pdf>` |
| `draft` | Summary → watermarked draft report | `<summary>` |

## Hard constraints

- **Never fabricate data.** Every number comes from the parsed file.
- **Reports are drafts.** They carry a watermark; academic responsibility stays with the user.

## Outputs

- `<WS>/process/stage_c/` — converted JSON/CSV.
- `<WS>/process/stage_a/` — the preconfigured run.
- `<WS>/process/stage_d/draft.md` — the watermarked draft.
- `<WS>/process/gates/capstone-labmate_<ts>.json` — the gate result.

## Failure handling

- An unreadable or truncated `.cap` fails the gate with the parser's message.
- A PDF without a recognisable procedure is reported, never guessed.

## Limitations

- "PASCO" and "Capstone" are trademarks of PASCO Scientific; this skill is independent.
- Conversion down-samples: the full native resolution is not preserved.
