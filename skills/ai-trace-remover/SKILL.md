---
name: ai-trace-remover
version: 1.4.0
description: >
  Strips template sentences from a manuscript, scores 0–100 AI-likeness and
  reports each edit.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# ai-trace-remover

Strips formulaic phrasing and grades the residue. It never rewrites your
argument and never deletes a sentence silently.

- **Stage:** `processors` · **Sandbox:** no · **Dependencies:** stdlib only

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action scan -- <file>
```

- Everything after `--` is forwarded to the legacy CLI, which takes the
  manuscript path positionally.
- Only matched patterns are touched, and every change is reported.
- The gate lands in `<WS>/process/gates/ai-trace-remover_<ts>.json`.

## When to use

- A draft is about to be delivered and formulaic phrasing must go.
- A text's template density must be measured.

## When NOT to use

- The content itself must be improved — that is writing, not cleaning.
- The user wants a sentence deleted outright without a report.

## More

- [actions, outputs, failure handling and limits](references/ai-trace-remover-reference.md)
- [English pattern library, 24 tells](references/ai-patterns-en.md)
- [中文 AI 写作痕迹模式库](references/ai-patterns-zh.md)
- [改写前后对照](references/example-diff.md)
- [改稿清单：七遍改稿 + 声音五条](references/revision.md)
- [评分规则：0–100](references/scoring-rubric.md)
