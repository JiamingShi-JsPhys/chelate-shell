"""secret-gate — credential shapes in a tree, reported without the secret.

    python run.py --root <WS> --action scan [--path process/]
                  [--allowlist .chelate/secret-allowlist.json]

All scanning logic lives in lib/chelate_core/secret_scan.py; this file maps
its report onto the gate contract.

Verdicts:
    PASS        every scanned file is free of unallowlisted credential shapes
    FAIL        at least one finding; the reason names path:line, rule and
                fingerprint, never the matched string
    UNVERIFIED  there was nothing scannable (no text files under --path)

Outputs:
    process/gates/secret-gate_<ts>.json   the gate result
    process/secret_scan_<ts>.json         every finding, fingerprints only
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, next(
    (p for p in (_HERE, os.path.dirname(_HERE),
                 os.path.dirname(os.path.dirname(_HERE)),
                 os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
     if os.path.isdir(os.path.join(p, "lib", "chelate_core"))),
    os.path.abspath(os.path.join(_HERE, "..", ".."))))

from lib.chelate_core import adapter, paths, secret_scan  # noqa: E402

SKILL = "secret-gate"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ()


def _configure(ap) -> None:
    ap.add_argument("--path", default=".",
                    help="directory to scan, relative to --root "
                         "(default: the workspace root)")
    ap.add_argument("--allowlist", default="",
                    help="allowlist JSON (default: "
                         ".chelate/secret-allowlist.json in the workspace)")


def _scan(args) -> dict:
    root = os.path.abspath(args.root)
    target = paths.ensure_within(root, os.path.join(root, args.path),
                                 "scan path")
    allowlist = args.allowlist
    if allowlist:
        allowlist = paths.ensure_within(root, os.path.join(root, allowlist),
                                        "allowlist")
    else:
        allowlist = os.path.join(root, secret_scan.ALLOWLIST_PATH)
    try:
        report = secret_scan.scan(target, allowlist=allowlist)
    except ValueError as exc:
        raise adapter.Failed(str(exc))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = adapter.bootstrap().write_json(
        str(Path(root) / "process"), f"secret_scan_{stamp}.json", report)
    if report["files_scanned"] == 0:
        raise adapter.Degraded(
            f"no text files to scan under "
            f"{os.path.relpath(target, root).replace(os.sep, '/')}")
    reason = secret_scan.summarise(report)
    if report["findings"]:
        raise adapter.Failed(reason, evidence_level="EXACT",
                             artifacts=[out_path])
    return {"status": "PASS", "evidence_level": "EXACT", "reason": reason,
            "artifacts": [out_path], "data": {"files_scanned":
                                              report["files_scanned"],
                                              "allowed": report["allowed"]}}


HANDLERS = {"scan": _scan}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Scan a tree for credential shapes, never echoing them."))
