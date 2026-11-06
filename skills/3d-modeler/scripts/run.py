"""3d-modeler — v1.3.0 domain-extension engine skill (thin CLI).

Pure-Python OBJ generation / merge / audit lives in scripts/engine.py; this
adapter only wires the uniform CLI contract (--root/--action) onto it and
delegates through lib.chelate_core.adapter. The manifest declares
`sandbox_required: true`, so the Router isolates this skill in a real
subprocess with a 120-second circuit-breaker (timeouts -> UNVERIFIED).
"""
from __future__ import annotations

import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
# Walk up to the directory holding lib/chelate_core/, so the adapter does not
# depend on how deep the skill sits under skills/.
_REPO = next((p for p in _HERE.parents
              if (p / "lib" / "chelate_core" / "adapter.py").is_file()),
             _HERE.parents[1])
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_HERE))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "3d-modeler"


def _configure(ap):
    ap.add_argument("--input", required=False,
                    help="spec file (.json) describing the mesh, or an .obj "
                         "to audit / merge")
    ap.add_argument("--spec", required=False,
                    help="alias of --input (JSON mesh spec)")
    ap.add_argument("--merge", action="append", default=[],
                    help="additional .obj file to merge in (repeatable)")


def _handler(args):
    from engine import build_from_spec, audit_obj, merge_objs
    import pathlib

    root = pathlib.Path(args.root)
    out_dir = root / "process" / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = args.input or args.spec
    if not spec:
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": "no --input/--spec provided"}
    spec_path = pathlib.Path(spec)
    if not spec_path.is_file():
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": f"input not found: {spec}"}
    try:
        if spec_path.suffix.lower() == ".json":
            mesh = build_from_spec(spec_path)
            obj_path = out_dir / (spec_path.stem + ".obj")
        else:  # .obj -> audit (and optionally merge)
            mesh = audit_obj(spec_path)
            obj_path = out_dir / (spec_path.stem + "_audited.obj")
        merges = [pathlib.Path(m) for m in (args.merge or []) if m]
        if merges:
            mesh = merge_objs(mesh, merges)
        obj_path.write_text(mesh, encoding="utf-8")
        return {"status": "PASS", "evidence_level": "SYMBOLIC",
                "reason": f"wrote {obj_path.name}",
                "artifacts": [str(obj_path)]}
    except Exception as exc:
        return {"status": "FAIL", "evidence_level": "UNVERIFIED",
                "reason": f"3d-modeler failed: {exc}"}


if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, {"process": _handler},
        description="Pure-Python OBJ 3D mesh generation, merge, and audit "
                    "(sandboxed)."))
