# 3d-modeler

Domain-extension skill for Chelate Shell. Generates, merges, and audits
**pure-Python OBJ 3D meshes** — no third-party mesh library required. Runs
sandboxed with a 120-second circuit-breaker.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Usage

```bash
# generate from a JSON spec
python scripts/run.py --root <workspace> --action process --input mesh.json

# audit an existing .obj (optionally merge others in)
python scripts/run.py --root <workspace> --action process \
    --input part.obj --merge other.obj
```

## Output

- `PASS` with `artifacts = [<root>/process/models/<stem>.obj]` (generation)
  or `<stem>_audited.obj` (audit), or the merged mesh.
- `UNVERIFIED` when no `--input` is given or the file is missing.
- `FAIL` only on malformed input (e.g. out-of-range face indices), never on a
  sandbox timeout (timeouts degrade to `UNVERIFIED`).

## Engine API (`scripts/engine.py`)

- `build_from_spec(spec_path)` — JSON `{name, vertices, faces}` -> OBJ text.
- `audit_obj(obj_path)` — validate + normalise an OBJ; raises on bad indices.
- `merge_objs(base_text, others)` — concatenate meshes (X-offset per merge).

## License

The skill code is MIT (see [LICENSE](LICENSE)). It has no third-party
dependencies, so there are no downstream license obligations.
