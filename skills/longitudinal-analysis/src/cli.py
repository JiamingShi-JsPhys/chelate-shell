"""Command-line entry point for the longitudinal-analysis pipeline.

Usage::

    python -m src.cli run --config config/examples/behavior_2x2x2.yaml
    python -m src.cli run --config ... --step lmm
    python -m src.cli validate --config ...
    python -m src.cli export --format docx

The subcommand ``run`` always goes through :mod:`pipeline` so R-unavailable
steps degrade to skips instead of aborting the whole run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import AnalysisConfig, load_config
from .pipeline import run_pipeline

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jla",
        description="Longitudinal analysis pipeline (LMM / mediation / sensitivity).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Run the configured pipeline")
    p_run.add_argument("--config", required=True, help="Path to a YAML/JSON config")
    p_run.add_argument("--step", default=None, help="Run only this named step")
    p_run.add_argument("--data", default=None, help="Override cfg.data_input")

    p_validate = sub.add_parser("validate", help="Validate a config and exit")
    p_validate.add_argument("--config", required=True)

    p_init = sub.add_parser("init", help="Create the default output directories")
    p_init.add_argument("--config", required=True)

    p_export = sub.add_parser("export", help="Export tables to docx/csv")
    p_export.add_argument("--config", required=True)
    p_export.add_argument("--format", default="csv", choices=["csv", "docx"])

    p_list = sub.add_parser("list-steps", help="List the configured steps")
    p_list.add_argument("--config", required=True)

    return parser


def _only_step(cfg: AnalysisConfig, name: str) -> None:
    """Reduce ``cfg.steps`` to a single enabled step for --step runs."""
    target = [s for s in cfg.steps if s.name == name]
    if not target:
        raise KeyError(f"no step named '{name}' in config")
    cfg.steps = target
    target[0].enabled = True
    for s in cfg.steps:
        if s.name != name:
            s.enabled = False


def main(argv=None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd in (None,):
        parser.print_help()
        return 0

    cfg = load_config(args.config)

    if args.cmd == "validate":
        cfg.validate()
        print(f"config OK: {len(cfg.steps)} steps, data={cfg.data_input}")
        return 0

    if args.cmd == "init":
        for key in ("tables", "figures", "logs"):
            Path(cfg.outputs[key]).mkdir(parents=True, exist_ok=True)
        print(f"initialised output dirs under {cfg.analysis_id}")
        return 0

    if args.cmd == "list-steps":
        for s in cfg.steps:
            state = "enabled" if s.enabled else "disabled"
            print(f"  - {s.name} [{s.type}] ({state})")
        return 0

    if args.cmd == "run":
        if args.step:
            _only_step(cfg, args.step)
        summary = run_pipeline(cfg, data_input=args.data)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "export":
        import pandas as pd

        tables_dir = Path(cfg.outputs["tables"])
        out_dir = tables_dir.parent / "export"
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(tables_dir.glob("*.csv")) if tables_dir.exists() else []:
            df = pd.read_csv(f)
            if args.format == "csv":
                out_dir.joinpath(f.name).write_text(df.to_csv(index=False), encoding="utf-8")
            else:  # docx
                if "docx" not in sys.modules:
                    from docx import Document  # type: ignore[import-not-found]
                doc = Document()
                doc.add_heading(f.name, level=1)
                tbl = doc.add_table(rows=1, cols=len(df.columns))
                for i, col in enumerate(df.columns):
                    tbl.rows[0].cells[i].text = str(col)
                for _, row in df.iterrows():
                    cells = tbl.add_row().cells
                    for i, val in enumerate(row):
                        cells[i].text = str(val)
                doc.save(out_dir / f"{f.stem}.docx")
        print(f"exported {args.format} -> {out_dir}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
