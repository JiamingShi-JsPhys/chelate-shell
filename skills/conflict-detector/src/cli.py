"""Command-line entry point for the conflict-detector.

Usage::

    python -m src.cli run --config config/examples/two_docs.yaml
    python -m src.cli run --config ... --format md,csv
    python -m src.cli validate --config ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .detector import run_config

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cd",
        description="Cross-document conflict detector (entity / clause / argument).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Run a detection from a config")
    p_run.add_argument("--config", required=True)
    p_run.add_argument("--format", default="json", help="json, csv, md, or comma-separated")

    p_validate = sub.add_parser("validate", help="Validate a config and exit")
    p_validate.add_argument("--config", required=True)

    p_list = sub.add_parser("list-docs", help="List the document sources in a config")
    p_list.add_argument("--config", required=True)

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
        print(f"config OK: {len(cfg.documents)} docs, levels={cfg.levels}")
        return 0

    if args.cmd == "list-docs":
        cfg = load_config(args.config)
        for s in cfg.documents:
            print(f"  - {s.id} [{s.kind}]")
        return 0

    if args.cmd == "run":
        cfg = load_config(args.config)
        result = run_config(cfg, fmt=args.format)
        print(json.dumps(result.to_summary(), indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
