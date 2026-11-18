---
name: 3d-modeler
version: 1.4.0
description: >
  Generates, merges or audits pure-Python OBJ meshes: winding, degenerate
  faces, bounds.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
---

# 3d-modeler

> **Deprecated — audit only.** Printing-quality verification belongs to
> `3d-fabric --action inspect`; this skill's `.obj` audit still works and says
> it is deprecated.

Generates, merges and inspects OBJ meshes with no third-party geometry
library. It does not render or slice.

- **Stage:** `domain_extensions` · **Sandbox:** yes · **Dependencies:** stdlib only

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python scripts/run.py --root <WS> --action process --input spec.json
```

- `--spec` is an alias of `--input`; `--merge other.obj` may be repeated.
- An `.obj` as `--input` audits or merges instead of generating.
- Output lands under `<WS>/process/`; the gate in `<WS>/process/gates/`.

## What it guarantees

- The input mesh is never modified in place.
- Defects are **reported, never silently repaired**.

## When to use

- A mesh must be generated from a parameter spec.
- Several OBJ files must be combined into one.
- An existing mesh must be audited for defects.

## When NOT to use

- Rendering, slicing or 3D-printing preparation.
- Formats other than OBJ.

## More

- [actions, outputs, failure handling and limits](references/3d-modeler-reference.md)
