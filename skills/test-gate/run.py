"""test-gate — gates-stage test-command check (thin adapter).

Engine: lib/chelate_core/testgate.py

    python run.py --root <WS> --action run
    python run.py --root <WS> --action run --command '["python","-m","pytest","-q"]'
    python run.py --root <WS> --action run --input tests --timeout 60

Nothing here executes anything: the argv, the whitelist, the timeout and
the verdict all live in testgate.py.
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

from lib.chelate_core import adapter, paths, testgate  # noqa: E402

SKILL = "test-gate"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ()


def _configure(ap) -> None:
    ap.add_argument("--input", default="",
                    help="directory to run in (default: the workspace root)")
    ap.add_argument("--command", default="",
                    help='test command as a JSON array of arguments')
    ap.add_argument("--config", default="",
                    help="declaration file (default: .chelate/test-gate.json)")
    ap.add_argument("--timeout", type=int, default=0,
                    help="seconds; keep it under the router's own sandbox "
                         f"timeout (default: {testgate.DEFAULT_TIMEOUT})")


def _run(args) -> dict:
    try:
        declaration = testgate.resolve(args.root, args.command, args.config,
                                       args.timeout or None)
        cwd = ""
        if args.input:
            target = paths.ensure_within(
                args.root, str(paths.resolve_input(args.root, args.input)),
                what="--input")
            # The Router wires a declared file's --input to every skill that
            # takes its type. This gate's target is the project, not one
            # file, so a file means "run the project's tests" and the
            # command keeps the workspace root as its working directory.
            cwd = str(target) if os.path.isdir(str(target)) else ""
        outcome = testgate.run(args.root, declaration["command"],
                               timeout=declaration["timeout"], cwd=cwd or None)
    except (testgate.TestGateError, paths.WorkspaceEscape) as exc:
        raise adapter.Degraded(f"cannot run tests: {exc}")

    report = testgate.report(outcome, declaration["timeout"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = adapter.bootstrap().write_json(
        os.path.join(args.root, "process"), f"test_report_{stamp}.json", report)
    if report["status"] == "FAIL":
        raise adapter.Failed(report["reason"], evidence_level="EXACT",
                             artifacts=[out_path])
    if report["status"] == "UNVERIFIED":
        raise adapter.Degraded(report["reason"], artifacts=[out_path])
    kept = ("rc", "passed", "failed", "errors", "skipped", "summary",
            "framework")
    return {"status": "PASS", "evidence_level": "EXACT",
            "reason": report["reason"], "artifacts": [out_path],
            "data": {key: report["data"][key] for key in kept}}


HANDLERS = {"run": _run}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Run the project's declared test command and gate on "
                    "the result it actually printed."))
