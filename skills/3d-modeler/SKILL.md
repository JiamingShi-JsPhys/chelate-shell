---
name: 3d-modeler
version: 1.3.3
description: >
  Pure-Python OBJ mesh work: generate a mesh from a JSON spec, merge several
  OBJ files, and audit an existing mesh (winding, degenerate faces, bounds).
  Runs inside the process sandbox.
metadata:
  version: 1.3.3
  author: Jiaming Shi
  license: MIT
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
---
> **Deprecated — audit only.** This action still generates and merges OBJ
> meshes, but its `.obj` audit path is deprecated. For print-quality
> verification (watertightness, non-manifold edges, normals, size) use
> `3d-fabric`: `python run.py --action inspect --input part.obj`.


# 3d-modeler

Generates, merges and inspects OBJ meshes with no third-party geometry
library. It does not render or slice.

- **Stage:** `domain_extensions` · **Sandbox:** yes · **Dependencies:** stdlib only

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python scripts/run.py --root <WS> --action process --input spec.json
```

- `--spec` is an alias of `--input`; `--merge other.obj` may be repeated.
- Point `--input` at an `.obj` to audit or merge instead of generate.
- Output lands under `<WS>/process/`; the gate in `<WS>/process/gates/`.

## When to use

- A mesh must be generated from a parameter spec.
- Several OBJ files must be combined into one.
- An existing mesh must be audited for defects.

## When NOT to use

- Rendering, slicing or 3D printing preparation.
- Formats other than OBJ.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `process` | Generate / merge (+ deprecated audit) | `--input <spec.json\|.obj> [--spec ...] [--merge other.obj ...]` |

## Hard constraints

- **Never modify the input mesh in place.**
- **Report defects, do not silently repair them.**

## Outputs

- `<WS>/process/<name>.obj` — the generated or merged mesh.
- `<WS>/process/gates/3d-modeler_<ts>.json` — the gate result and QC findings.

## Failure handling

- A malformed spec or OBJ exits non-zero with the offending line.
- A merge with mismatched vertex layout is refused, not forced.

## Limitations

- OBJ only; no textured or animated formats.
- Pure Python, so very large meshes are slow.

## Delivering results

This skill writes intermediates to `process/`. Do not copy its output into
`results/` yourself — `results/` is filled only by `python cli.py pipeline`
after a human approved that exact plan. Before telling the user a deliverable
is ready, run `python cli.py audit --root <ws>`: exit 1 means `results/` holds
files no approval accounts for, and the honest answer is to report that
instead of claiming delivery.
