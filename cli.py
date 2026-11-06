"""Chelate Shell CLI entry point.

Usage:
    python cli.py list
    python cli.py run "task-organizer" --root /path/to/workspace
    python cli.py pipeline --root /path/to/workspace --mode a
    python cli.py pipeline --root /path/to/workspace --mode b --input-kind csv
    python cli.py pipeline --root /path/to/workspace --mode c --selected formula-validator,reference-auditor
    python cli.py pipeline --root /path/to/workspace --dry-run
    python cli.py pipeline --root /path/to/workspace --mode c \
        --selected reference-auditor --skill-arg "reference-auditor:--input draft.md"
    python cli.py pipeline --root ./test_workspace --inputs draft.md data.csv
    python cli.py pipeline --root /path/to/workspace --mode c --selected data-profiler --debug

Caller: a user / agent subprocess. No other file imports this module.
Data schemas:
    Reads:  skills/<skill>/manifest.json (via core.registry).
    Writes: results/pipeline_report_<ts>.json + _broadcast/pipeline_index_<ts>.json.
User instruction: "cli.py — the command-line entry point (run: python cli.py run <task>)".
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.registry import load_default_registry
from core.router import run as router_run
from lib.chelate_core import debug as debug_mod
from lib.chelate_core import paths


def cmd_list(args) -> int:
    reg = load_default_registry()
    print(f"{len(reg)} skills registered:")
    for rec in reg.all():
        deps = ",".join(rec.dependencies) if rec.dependencies else "-"
        print(f"  {rec.name:<28} stage={rec.stage:<10} deps=[{deps}]")
        if debug_mod.flag(args.debug):
            debug_mod.log(f"{rec.name}: entrypoint={rec.entrypoint} "
                          f"inputs={rec.input_types} outputs={rec.output_types} "
                          f"sandbox_required={rec.sandbox_required} "
                          f"run_path={rec.run_path}")
    return 0


def cmd_run(args) -> int:
    """Run a single skill directly (bypasses the pipeline).

    All skill-specific args (including --root) come after the skill name via
    argparse.REMAINDER, so any flag order works.
    """
    reg = load_default_registry()
    rec = reg.get(args.name)
    if rec is None:
        print(f"unknown skill: {args.name}; available: {reg.names()}",
              file=sys.stderr)
        return 1
    # --debug may sit before the skill name (parsed) or inside the REMAINDER
    # (swallowed by argparse); accept both and never forward it to the skill.
    skill_args = [a for a in (args.args or []) if a != "--debug"]
    debug_mod.flag(args.debug or "--debug" in (args.args or []))
    import subprocess
    cmd = [sys.executable, rec.run_path] + skill_args
    debug_mod.log(f"run: exec {' '.join(cmd)} (cwd={_REPO_ROOT})")
    proc = subprocess.run(cmd, cwd=_REPO_ROOT, env=decision_env(rec))
    return proc.returncode


def decision_env(rec):
    """Build the subprocess env for a skill (degraded deps -> UNVERIFIED)."""
    from core.sandbox import resolve_environment
    return resolve_environment(rec.dependencies).env()


def parse_skill_args(pairs) -> dict:
    """Parse repeated --skill-arg 'skill:flag [flag ...]' into {skill: [args]}."""
    out = {}
    for pair in pairs or []:
        if ":" not in pair:
            continue
        skill, _, rest = pair.partition(":")
        skill = skill.strip()
        args = rest.split()
        if skill and args:
            out.setdefault(skill, []).extend(args)
    return out


def cmd_pipeline(args) -> int:
    debug_mod.flag(args.debug)  # sets CHELATE_DEBUG for skill subprocesses
    root = os.path.abspath(args.root)
    inputs, missing = paths.resolve_inputs(root, args.inputs)
    if missing:
        print("input file(s) not found (resolved against --root "
              f"{root}): " + ", ".join(missing), file=sys.stderr)
        return 2
    selected = [s.strip() for s in args.selected.split(",") if s.strip()] if args.selected else None
    skill_args = parse_skill_args(args.skill_arg)
    result = router_run(
        root,
        mode=args.mode,
        input_kind=args.input_kind,
        inputs=inputs,
        selected=selected,
        dry_run=args.dry_run,
        skill_args=skill_args,
        timeout=args.timeout,
        debug=args.debug,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("terminated_by") else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cli.py", description="Chelate Shell microkernel CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    lp = sub.add_parser("list", help="list registered skills")
    lp.add_argument("--debug", action="store_true",
                    help="verbose stderr diagnostics (same as CHELATE_DEBUG=1)")
    lp.set_defaults(fn=cmd_list)

    pr = sub.add_parser("run", help="run a single skill")
    pr.add_argument("name")
    pr.add_argument("args", nargs=argparse.REMAINDER,
                    help="args passed to the skill run.py (incl. --root)")
    pr.add_argument("--debug", action="store_true",
                    help="verbose stderr diagnostics (same as CHELATE_DEBUG=1)")
    pr.set_defaults(fn=cmd_run)

    pp = sub.add_parser("pipeline", help="run a pipeline (mode a/b/c)")
    pp.add_argument("--root", default=".")
    pp.add_argument("--mode", choices=["a", "b", "c"], default="a")
    pp.add_argument("--input-kind", default="")
    pp.add_argument("--inputs", nargs="+", default=[], metavar="FILE",
                    help="input files for this run (workspace-relative or "
                         "absolute); each is forwarded as --input to the "
                         "plan skills that declare its type in the manifest")
    pp.add_argument("--selected", default="")
    pp.add_argument("--dry-run", action="store_true",
                    help="print the planned execution order without running")
    pp.add_argument("--skill-arg", action="append", default=[],
                    metavar="SKILL:ARGS",
                    help='per-skill args, e.g. "reference-auditor:--input draft.md"')
    pp.add_argument("--timeout", type=int, default=600,
                    help="per-skill subprocess timeout in seconds")
    pp.add_argument("--debug", action="store_true",
                    help="verbose stderr diagnostics (same as CHELATE_DEBUG=1)")
    pp.set_defaults(fn=cmd_pipeline)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
