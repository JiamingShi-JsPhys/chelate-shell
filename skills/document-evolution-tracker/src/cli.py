"""Command-line entry point for the document-evolution-tracker.

Usage::

    python -m src.cli run --config config/examples/family.json
    python -m src.cli run --config ... --concepts "Term A,Term B"
    python -m src.cli versions --config ...
    python -m src.cli validate --config ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .tracker import run_config
from .versioning import discover_versions

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="det",
        description="Document evolution tracker (version alignment + concept lineage).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Run the evolution tracker")
    p_run.add_argument("--config", required=True)
    p_run.add_argument("--concepts", default=None, help="Comma-separated concept phrases")

    p_versions = sub.add_parser("versions", help="List the discovered version files")
    p_versions.add_argument("--config", required=True)

    p_validate = sub.add_parser("validate", help="Validate a config and exit")
    p_validate.add_argument("--config", required=True)

    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.cmd:
        parser.print_help()
        return 0

    if args.cmd == "validate":
        cfg = load_config(args.config)
        print(f"config OK: tracking_id={cfg.tracking_id}, granularity={cfg.granularity}")
        return 0

    if args.cmd == "versions":
        cfg = load_config(args.config)
        versions = discover_versions(cfg.versions_dir, cfg.version_naming)
        for v in versions:
            print(f"  - {v.version_id}")
        if not versions:
            print("  (no version files found)")
        return 0

    if args.cmd == "run":
        cfg = load_config(args.config)
        concepts = [c.strip() for c in args.concepts.split(",")] if args.concepts else None
        result = run_config(cfg, concepts=concepts)
        print(json.dumps(result.summary(), indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
