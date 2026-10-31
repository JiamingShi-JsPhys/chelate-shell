"""CLI smoke tests + contract tests for conflict-detector.

Contract tests lock the version three-way, the CRLF CHANGELOG, and the
zero-CJK invariant on README.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from src.cli import build_parser, main

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"
CHANGELOG_MD = SKILL_DIR / "CHANGELOG.md"
README_MD = SKILL_DIR / "README.md"


def _frontmatter_value(text: str, key: str) -> str | None:
    m = re.search(rf"^\s{{0,2}}{re.escape(key)}:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip().strip('"') if m else None


def test_version_consistency() -> None:
    from src import __version__

    assert _frontmatter_value(SKILL_MD.read_text(encoding="utf-8"), "version") == __version__
    assert __version__ == "1.2.0"


def test_changelog_is_crlf() -> None:
    raw = CHANGELOG_MD.read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b""), "CHANGELOG.md must be CRLF"
    assert b"\r\n" in raw


def test_readme_md_is_pure_english() -> None:
    text = README_MD.read_text(encoding="utf-8")
    body = text.replace("[中文说明](README_zh.md)", "")
    cjk = [ch for ch in body if "\u4e00" <= ch <= "\u9fff"]
    assert not cjk, f"README.md contains CJK: {cjk[:5]}"


def test_changelog_has_version_entry() -> None:
    assert "## [1.0.0]" in CHANGELOG_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# cli.py
# ---------------------------------------------------------------------------

def test_build_parser_subcommands() -> None:
    import argparse

    parser = build_parser()
    subparsers_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    cmds = set(subparsers_action.choices.keys())
    assert {"run", "validate", "list-docs"} <= cmds


def test_cli_validate(tmp_path) -> None:
    cfg = {
        "version": "1.0.0",
        "run_id": "c1",
        "documents": [
            {"id": "a", "kind": "text", "value": '{"x": 1}'},
            {"id": "b", "kind": "text", "value": '{"x": 2}'},
        ],
        "levels": ["entity"],
    }
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    rc = main(["validate", "--config", str(p)])
    assert rc == 0


def test_cli_run_and_write_report(tmp_path) -> None:
    cfg = {
        "version": "1.0.0",
        "run_id": "run1",
        "documents": [
            {"id": "a", "kind": "text", "value": '{"x": 1, "active": true}'},
            {"id": "b", "kind": "text", "value": '{"x": 9, "active": false}'},
        ],
        "levels": ["entity", "clause"],
        "output_dir": str(tmp_path / "out"),
    }
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    rc = main(["run", "--config", str(p), "--format", "json,csv,md"])
    assert rc == 0
    out = tmp_path / "out"
    data = json.loads((out / "conflicts_run1.json").read_text())
    kinds = {c["kind"] for c in data}
    assert "numeric_mismatch" in kinds
    assert "boolean" in kinds
    assert (out / "conflicts_run1.csv").exists()
    assert (out / "conflicts_run1.md").exists()
