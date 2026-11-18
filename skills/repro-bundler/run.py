"""repro-bundler — processors-stage reproducibility bundle (thin adapter).

Packing and checking live in lib/chelate_core/repro.py:

    python run.py --root <workspace> --action bundle --name paper-x
    python run.py --root <workspace> --action bundle --name paper-x \
        --include process/bands.csv process/figure.pdf
    python run.py --root <workspace> --action verify --bundle <path.zip>

Nothing here extracts a zip; verify reads entries in memory.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, next(
    (p for p in (_HERE, os.path.dirname(_HERE),
                 os.path.dirname(os.path.dirname(_HERE)),
                 os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
     if os.path.isdir(os.path.join(p, "lib", "chelate_core"))),
    os.path.abspath(os.path.join(_HERE, "..", ".."))))

from lib.chelate_core import adapter, paths, repro  # noqa: E402

SKILL = "repro-bundler"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ()


def _configure(ap) -> None:
    ap.add_argument("--name", default="bundle",
                    help="bundle name, used in the file name")
    ap.add_argument("--include", nargs="*", default=None,
                    help="workspace-relative files to bundle (default: all of process/)")
    ap.add_argument("--bundle", default="",
                    help="path to the .zip to verify (--action verify)")


def _bundle(args) -> dict:
    try:
        result = repro.build(args.root, args.name, include=args.include)
    except repro.BundleError as exc:
        raise adapter.Failed(f"cannot build bundle: {exc}")
    return {
        "status": "PASS", "evidence_level": "EXACT",
        "reason": (f"bundled {result['files']} files into "
                   f"{os.path.basename(result['path'])} "
                   f"({result['bytes']} bytes)"),
        "artifacts": [result["path"]],
        "data": {"files": result["files"], "bytes": result["bytes"],
                 "gates": len(result["manifest"]["gates"]),
                 "skills": len(result["manifest"]["skills"])},
    }


def _verify(args) -> dict:
    if not args.bundle:
        raise adapter.Failed("--bundle <path.zip> is required for verify")
    path = paths.resolve_input(args.root, args.bundle)
    if not path.is_file():
        raise adapter.Failed(f"bundle not found: {path}")
    try:
        report = repro.verify(str(path))
    except repro.BundleError as exc:
        text = str(exc)
        if "not a zip" in text or "no manifest" in text:
            raise adapter.Degraded(f"not verifiable: {exc}")
        raise adapter.Failed(f"bundle refused: {exc}")
    if not report["ok"]:
        raise adapter.Failed(
            f"{os.path.basename(str(path))}: {report['problems'][0]}",
            evidence_level="EXACT")
    return {
        "status": "PASS", "evidence_level": "EXACT",
        "reason": (f"{report['files']} files match the manifest of "
                   f"{report['bundle']!r} (created {report['created']})"),
        "artifacts": [],
        "data": {"files": report["files"], "bundle": report["bundle"]},
    }


HANDLERS = {"bundle": _bundle, "verify": _verify}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Bundle a run's products into a reproducible zip, or "
                    "verify a bundle without extracting it."))
