"""CLI smoke tests for the longitudinal-analysis entry point.

Exercises the argument parsing / dispatch without running the full R stack:
``--version``, ``validate``, ``init``, ``list-steps``, and the R-skip path of
``run``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
import pytest

from src import cli
from src.cli import build_parser, main


def test_build_parser_subcommands() -> None:
    """The parser must expose all documented subcommands."""
    parser = build_parser()
    # Use the registered subparsers' help strings.
    subparsers_action = next(
        a for a in parser._actions
        if isinstance(a, argparse._SubParsersAction)
    )
    cmds = set(subparsers_action.choices.keys())
    assert {"run", "validate", "init", "export", "list-steps"} <= cmds


def test_main_no_args_returns_zero(capsys) -> None:
    """A bare invocation must print help and return 0."""
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "jla" in out or "usage" in out.lower()


def test_main_validate(capsys, tmp_path, pipeline_config: dict, fixture_panel_csv: Path) -> None:
    """`validate` must load the config, validate, and exit 0."""
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(pipeline_config), encoding="utf-8")
    rc = main(["validate", "--config", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "config OK" in out


def test_main_init_creates_dirs(capsys, tmp_path, pipeline_config: dict, fixture_panel_csv: Path) -> None:
    """`init` must create the output directories."""
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(pipeline_config), encoding="utf-8")
    rc = main(["init", "--config", str(p)])
    assert rc == 0
    for key in ("tables", "figures", "logs"):
        assert Path(pipeline_config["outputs"][key]).exists()


def test_main_list_steps(capsys, tmp_path, pipeline_config: dict, fixture_panel_csv: Path) -> None:
    """`list-steps` must print each configured step."""
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(pipeline_config), encoding="utf-8")
    rc = main(["list-steps", "--config", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "descriptive" in out


def test_main_run_r_step_skips(capsys, tmp_path, pipeline_config: dict, fixture_panel_csv: Path) -> None:
    """`run --step lmm` must skip gracefully when Rscript is missing."""
    cfg = dict(pipeline_config)
    cfg["steps"] = [
        {"name": "lmm", "type": "lmm",
         "config": {"formula": "willingness ~ session", "reml": True}},
    ]
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    rc = main(["run", "--config", str(p), "--step", "lmm", "--data", str(fixture_panel_csv)])
    assert rc == 0
    out = capsys.readouterr().out
    summary = json.loads(out)
    # Rscript is not installed in the sandbox -> step skipped, not crashed.
    assert summary["steps"][0]["status"] in ("skipped", "success")


def test_main_run_unknown_step_errors(tmp_path, pipeline_config: dict, fixture_panel_csv: Path) -> None:
    """`run --step <unknown>` must raise KeyError."""
    cfg = dict(pipeline_config)
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(KeyError):
        main(["run", "--config", str(p), "--step", "not-a-step", "--data", str(fixture_panel_csv)])
