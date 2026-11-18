# 3d-modeler — reference

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

This skill writes intermediates to `process/`. `results/` is filled only by
`python cli.py pipeline` after a human approved that exact plan.

- Do not copy a skill's output into `results/` yourself, and do not do it
  because the user asked for a shortcut: say that only `cli.py pipeline`
  writes there, offer to run the pipeline instead, and if they still insist,
  tell them `cli.py audit` will report the file as unapproved.
- Never set `CHELATE_UNSAFE_AUTO_APPROVE=1` (formerly `CHELATE_HUMAN`) and
  never run `cli.py approve` on the user's behalf. If an approval is needed,
  ask the human to issue it in their own terminal.
- Before telling the user a deliverable is ready — and after any write you
  make under `results/` — run `python cli.py audit --root <ws>`. Exit 1 means
  files there have no approval behind them: report that and name them, do not
  describe the state as delivered.
