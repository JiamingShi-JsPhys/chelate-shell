---
name: model3d
description: Generate, merge, or audit a pure-Python OBJ 3D mesh.
metadata:
  skill: 3d-modeler
  stage: domain_extensions
  sandbox: true
---

# /model3d — build or audit a 3D mesh

Generates a Wavefront `.obj` mesh from a JSON spec, audits/normalises an
existing `.obj`, or merges several meshes. Pure standard library (no mesh
library), and runs inside an isolated sandbox process with a 120-second
circuit-breaker (timeouts degrade to `UNVERIFIED`, never `FAIL`).

## Usage

```bash
# generate from a JSON spec
python skills/3d-modeler/scripts/run.py \
    --root <WS> --action process --input mesh.json

# audit an existing .obj (optionally merge others in)
python skills/3d-modeler/scripts/run.py \
    --root <WS> --action process --input part.obj --merge other.obj
```

- `--input` is a `.json` mesh spec (`{name, vertices, faces}`) or a `.obj`.
- `--merge <file.obj>` may be repeated; each merged part is offset +10 on X.
- The resulting `.obj` is written to `<WS>/process/models/` and reported as an
  artifact; the gate is written to `<WS>/process/gates/`.

## Spec shape

```json
{
  "name": "cube",
  "vertices": [[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]],
  "faces": [[1,2,3,4],[5,6,7,8],[1,2,6,5],[2,3,7,6],[3,4,8,7],[4,1,5,8]]
}
```
