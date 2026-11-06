"""Command-line entry point for multi-dim-manager.

Subcommands:
  run       Execute the full multi-dimensional sweep (default action).
  dryrun    Print the plan without executing any plugin.
  rollback  Restore a past round's post-state (non-destructive by default).
  summary   Regenerate the CSV / Markdown summaries from the audit log.
  verify    Check one round's plugin-contract outcome.

Exit codes: 0 = ok, 1 = at least one round failed, 2 = usage/config error,
3 = unexpected internal error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

# Allow this file to run both as `python scripts/run.py` and
# `python -m scripts.run`. When executed directly, __package__ is empty, so we
# put the project root on sys.path and pretend to belong to the `scripts`
# package; relative imports then resolve correctly.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "scripts"

from . import __version__
from .aggregator import aggregate, write_csv
from .audit import AuditLog, RoundRecord, now_iso, write_metadata
from .common import now_iso as _now
from .config import Config, load_config
from .errors import ManagerError, RollbackError
from .executor import run_plugin
from .report import write_draft, write_markdown
from .rollback import rollback_to
from .snapshot import Manifest, restore, snapshot
from .verify import verify_round


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _output_paths(cfg: Config):
    out = cfg.output
    return {
        "audit": out / "audit_log.jsonl",
        "store": out / "snapshots" / "store",
        "meta": out / "run_metadata.json",
        "csv": out / "results_summary.csv",
        "md": out / "results_summary.md",
        "draft": out / "report_draft.md",
    }


def _summarize(cfg: Config, audit: AuditLog) -> None:
    paths = _output_paths(cfg)
    records = audit.rounds()
    summary = aggregate(records, cfg.param_keys())
    write_csv(summary, paths["csv"])
    write_markdown(summary, paths["md"])
    write_draft(records, summary, paths["draft"])


# --------------------------------------------------------------------------- #
# Sub-command implementations
# --------------------------------------------------------------------------- #
def cmd_run(args) -> int:
    cfg = load_config(args.config)
    cfg.plugin_command = args.plugin or cfg.plugin_command
    if args.workdir:
        cfg.workdir = Path(args.workdir)
    if args.output:
        cfg.output = Path(args.output)
    paths = _output_paths(cfg)
    cfg.output.mkdir(parents=True, exist_ok=True)
    cfg.workdir.mkdir(parents=True, exist_ok=True)

    audit = AuditLog(paths["audit"])
    space = cfg.space
    total = space.size

    meta = {
        "skill": "multi-dim-manager",
        "version": __version__,
        "dimensions": [
            {"name": d.name, "values": list(d.values)} for d in space.dimensions
        ],
        "critical_paths": list(cfg.critical_paths),
        "plugin_command": cfg.plugin_command,
        "total_rounds": total,
        "started_at": _now(),
    }
    write_metadata(paths["meta"], meta)

    last_good: Optional[RoundRecord] = None
    any_failed = False

    for i, params in enumerate(space.combinations(), start=1):
        pre = snapshot(cfg.workdir, cfg.critical_paths, paths["store"], i, "pre")
        result = run_plugin(
            i, params, cfg.plugin_command, cfg.workdir, cfg.output, cfg.timeout
        )
        post = snapshot(cfg.workdir, cfg.critical_paths, paths["store"], i, "post")
        rec = RoundRecord(
            round_no=i,
            status=result.status,
            params=params,
            input_hash=result.input_hash,
            output_hash=result.output_hash,
            timestamp=now_iso(),
            plugin_exit=result.exit_code,
            out_file=str(result.out_file),
            snapshot_pre=pre.to_dict()["files"],
            snapshot_post=post.to_dict()["files"],
        )
        audit.record(rec)

        if result.status == "success":
            last_good = rec
        else:
            any_failed = True
            if cfg.auto_rollback and last_good is not None:
                manifest = Manifest(
                    round_no=last_good.round_no, phase="post",
                    files=last_good.snapshot_post, store_dir=paths["store"],
                )
                restore(manifest, cfg.workdir)
                audit.record(
                    RoundRecord(
                        round_no=last_good.round_no,
                        status="rolledback",
                        timestamp=now_iso(),
                        params=last_good.params,
                        note=f"auto-rollback: recovered baseline from round "
                        f"{last_good.round_no} after round {i} failed",
                    )
                )

    _summarize(cfg, audit)
    return 1 if any_failed else 0


def cmd_dryrun(args) -> int:
    cfg = load_config(args.config)
    cfg.plugin_command = args.plugin or cfg.plugin_command
    space = cfg.space
    print(f"multi-dim-manager dry-run (version {__version__})")
    print(f"Total rounds: {space.size}")
    print("Plan:")
    for i, params in enumerate(space.combinations(), start=1):
        print(f"  round {i:>4}: {params}")
    print(f"Plugin: {cfg.plugin_command}")
    print(f"Critical paths: {cfg.critical_paths}")
    return 0


def cmd_rollback(args) -> int:
    cfg = load_config(args.config)
    if args.output:
        cfg.output = Path(args.output)
    paths = _output_paths(cfg)
    audit = AuditLog(paths["audit"])
    try:
        restored = rollback_to(
            audit, args.round, cfg.workdir, paths["store"], force=args.force
        )
    except RollbackError as exc:
        print(f"rollback failed: {exc}", file=sys.stderr)
        return 2
    print(f"rolled back round {args.round} -> {restored}")
    return 0


def cmd_summary(args) -> int:
    cfg = load_config(args.config)
    if args.output:
        cfg.output = Path(args.output)
    paths = _output_paths(cfg)
    audit = AuditLog(paths["audit"])
    _summarize(cfg, audit)
    print(f"summary written: {paths['csv']} / {paths['md']} / {paths['draft']}")
    return 0


def cmd_verify(args) -> int:
    cfg = load_config(args.config)
    if args.output:
        cfg.output = Path(args.output)
    paths = _output_paths(cfg)
    audit = AuditLog(paths["audit"])
    rec = audit.get(args.round)
    if rec is None:
        print(f"round {args.round} not found in audit log", file=sys.stderr)
        return 2
    res = verify_round(rec, golden=args.golden)
    print(f"round {res.round_no}: passed={res.passed} ({res.detail})")
    return 0 if res.passed else 1


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="State manager for multi-dimensional experiments.",
    )
    parser.add_argument(
        "--version", action="version", version=f"multi-dim-manager {__version__}"
    )
    sub = parser.add_subparsers(dest="action")

    def _add_config(p, require=True):
        p.add_argument("--config", required=require, help="experiment config file")
        p.add_argument("--plugin", default=None, help="override plugin command")
        p.add_argument("--workdir", default=None, help="override working directory")
        p.add_argument("--output", default=None, help="override output directory")

    p_run = sub.add_parser("run", help="execute the full sweep")
    _add_config(p_run)
    p_dry = sub.add_parser("dryrun", help="print the plan without executing")
    _add_config(p_dry, require=True)
    p_roll = sub.add_parser("rollback", help="restore a past round")
    p_roll.add_argument("--config", required=True)
    p_roll.add_argument("--round", type=int, required=True)
    p_roll.add_argument("--force", action="store_true", help="overwrite workdir")
    p_roll.add_argument("--output", default=None)
    p_sum = sub.add_parser("summary", help="regenerate summaries")
    p_sum.add_argument("--config", required=True)
    p_sum.add_argument("--output", default=None)
    p_ver = sub.add_parser("verify", help="verify a round's outcome")
    p_ver.add_argument("--config", required=True)
    p_ver.add_argument("--round", type=int, required=True)
    p_ver.add_argument("--golden", default=None, help="expected output hash")
    p_ver.add_argument("--output", default=None)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.action is None:
        parser.print_help()
        return 2
    handlers = {
        "run": cmd_run,
        "dryrun": cmd_dryrun,
        "rollback": cmd_rollback,
        "summary": cmd_summary,
        "verify": cmd_verify,
    }
    try:
        return handlers[args.action](args)
    except ManagerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"internal error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
