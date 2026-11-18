"""code-gate — gates-stage static check on Python source (thin adapter).

Engine: lib/chelate_core/codegate.py

    python run.py --root <WS> --action check --input src
    python run.py --root <WS> --action check --input app.py --max-lines 60
    python run.py --root <WS> --action check --input src --ruff

--ruff is opt-in: its findings are a second, versioned opinion, and the
report names the version that produced them.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, next(
    (p for p in (_HERE, os.path.dirname(_HERE),
                 os.path.dirname(os.path.dirname(_HERE)),
                 os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
     if os.path.isdir(os.path.join(p, "lib", "chelate_core"))),
    os.path.abspath(os.path.join(_HERE, "..", ".."))))

from lib.chelate_core import adapter, codegate, paths  # noqa: E402

SKILL = "code-gate"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ()


def _configure(ap) -> None:
    ap.add_argument("--input", required=True,
                    help="a .py file or a directory, inside the workspace")
    ap.add_argument("--max-lines", type=int, default=80,
                    help="line budget per function (default: 80)")
    ap.add_argument("--max-args", type=int, default=7,
                    help="argument budget per function (default: 7)")
    ap.add_argument("--ruff", action="store_true",
                    help="add ruff's findings (needs ruff installed)")


def _check(args) -> dict:
    try:
        report = codegate.check(args.root, args.input,
                                max_lines=args.max_lines,
                                max_args=args.max_args, ruff=args.ruff)
    except (codegate.CodeGateError, paths.WorkspaceEscape) as exc:
        raise adapter.Degraded(f"cannot check: {exc}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = adapter.bootstrap().write_json(
        os.path.join(args.root, "process"), f"code_report_{stamp}.json", report)
    if not report["files"]:
        raise adapter.Degraded(f"no Python files under {args.input!r}",
                               artifacts=[out_path])
    if report["unreadable"]:
        raise adapter.Degraded(
            f"{len(report['unreadable'])} file(s) could not be read: "
            f"{report['unreadable'][0]}", artifacts=[out_path])
    if report["finding_count"]:
        first = (report["findings"] or report["ruff"]["findings"])[0]
        counted = ", ".join(f"{rule}={n}" for rule, n in
                            sorted(report["by_rule"].items()))
        raise adapter.Failed(
            f"{report['finding_count']} finding(s) in {report['files']} "
            f"file(s) ({counted}); first: "
            f"{first['path']}:{first['line']} {first['rule']}",
            evidence_level="EXACT", artifacts=[out_path])
    note = report["ruff"]["note"]
    return {"status": "PASS", "evidence_level": "EXACT",
            "reason": (f"{report['files']} file(s) clean under "
                       f"{len(codegate.RULES)} fixed rule(s)"
                       + (f"; {note}" if note else "")),
            "artifacts": [out_path],
            "data": {"files": report["files"], "rules": len(codegate.RULES)}}


HANDLERS = {"check": _check}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Check Python source against a fixed, declared rule set "
                    "and fail on any finding."))
