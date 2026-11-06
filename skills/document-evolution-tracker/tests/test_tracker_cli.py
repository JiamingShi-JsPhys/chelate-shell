"""Tests for the tracker orchestrator, report rendering, and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
import pytest

from src.config import load_config
from src.report import render_timeline_json, render_timeline_markdown, write_timeline
from src.tracker import run_config, track_evolution


# ---------------------------------------------------------------------------
# tracker.py
# ---------------------------------------------------------------------------

def test_track_evolution_end_to_end(tmp_path: Path) -> None:
    family = tmp_path / "family"
    family.mkdir()
    (family / "v1.md").write_text("# Intro\n\nAlpha baseline", encoding="utf-8")
    (family / "v2.md").write_text("# Intro\n\nAlpha learned\n\n# New\n\nBeta", encoding="utf-8")

    result = track_evolution(family, naming="sequential", granularity="line", concepts=["Alpha", "Beta"])
    assert result["versions"] == ["v1.md", "v2.md"]
    assert len(result["diffs"]) == 1
    assert "Alpha" in result["lineage"]
    assert "Beta" in result["lineage"]


def test_run_config_writes_reports(tmp_path: Path) -> None:
    family = tmp_path / "family"
    family.mkdir()
    (family / "v1.md").write_text("one", encoding="utf-8")
    (family / "v2.md").write_text("two", encoding="utf-8")

    out_dir = tmp_path / "out"
    cfg = {
        "version": "1.0.0",
        "tracking_id": "t1",
        "versions_dir": str(family),
        "version_naming": "sequential",
        "granularity": "line",
        "out_dir": str(out_dir),
    }
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    result = run_config(cfg_path, concepts=["one", "two"])
    assert result.versions == ["v1.md", "v2.md"]
    md = out_dir / "evolution_t1.md"
    js = out_dir / "evolution_t1.json"
    assert md.exists() and js.exists()
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["versions"] == ["v1.md", "v2.md"]
    assert "one" in data["lineage"]


def test_track_evolution_single_version(tmp_path: Path) -> None:
    family = tmp_path / "family"
    family.mkdir()
    (family / "v1.md").write_text("only", encoding="utf-8")
    result = track_evolution(family, "sequential", "line", concepts=["only"])
    assert result["versions"] == ["v1.md"]
    assert result["diffs"] == []


# ---------------------------------------------------------------------------
# report.py
# ---------------------------------------------------------------------------

def test_render_markdown_has_lineage_table(tmp_path: Path) -> None:
    from src.versioning import Version

    class V:
        def __init__(self, vid):
            self.version_id = vid

    versions = [V("v1.md"), V("v2.md")]
    from src.diff_blocks import diff_blocks

    diffs = [diff_blocks("a", "b", "line", "v1.md", "v2.md")]
    from src.lineage import build_lineage

    texts = {"v1.md": "Alpha x", "v2.md": "Alpha y"}
    lineage = build_lineage(
        [Version("v1.md", Path("v1.md")), Version("v2.md", Path("v2.md"))],
        texts,
        concepts=["Alpha"],
    )
    md = render_timeline_markdown(["v1.md", "v2.md"], diffs, lineage, "r")
    assert "# Document Evolution Timeline" in md
    assert "Concept Lineage" in md
    assert "Alpha" in md


def test_render_json_roundtrip(tmp_path: Path) -> None:
    from src.diff_blocks import diff_blocks

    diffs = [diff_blocks("a", "b")]
    from src.lineage import LineageNode

    lineage = {"c": [LineageNode("v1", "introduced"), LineageNode("v2", "retained")]}
    payload = json.loads(render_timeline_json(["v1", "v2"], diffs, lineage))
    assert payload["versions"] == ["v1", "v2"]
    assert payload["lineage"]["c"][0]["state"] == "introduced"


def test_write_timeline_returns_paths(tmp_path: Path) -> None:
    from src.diff_blocks import diff_blocks

    diffs = [diff_blocks("a", "b")]
    paths = write_timeline(["v1", "v2"], diffs, {}, tmp_path / "out", "id1")
    assert len(paths) == 2
    assert all(p.exists() for p in paths)


# ---------------------------------------------------------------------------
# cli.py
# ---------------------------------------------------------------------------

def test_cli_validate(capsys, tmp_path: Path) -> None:
    from src.cli import main

    family = tmp_path / "f"
    family.mkdir()
    (family / "v1.md").write_text("x", encoding="utf-8")
    cfg = {
        "tracking_id": "t",
        "versions_dir": str(family),
        "version_naming": "sequential",
        "granularity": "line",
        "out_dir": str(tmp_path / "o"),
    }
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    rc = main(["validate", "--config", str(p)])
    assert rc == 0
    assert "config OK" in capsys.readouterr().out


def test_cli_versions_lists_files(capsys, tmp_path: Path) -> None:
    from src.cli import main

    family = tmp_path / "f"
    family.mkdir()
    (family / "v1.md").write_text("x", encoding="utf-8")
    (family / "v2.md").write_text("y", encoding="utf-8")
    cfg = {
        "tracking_id": "t",
        "versions_dir": str(family),
        "version_naming": "sequential",
        "granularity": "line",
        "out_dir": str(tmp_path / "o"),
    }
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    rc = main(["versions", "--config", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "v1.md" in out and "v2.md" in out


def test_cli_run_end_to_end(capsys, tmp_path: Path) -> None:
    from src.cli import main

    family = tmp_path / "f"
    family.mkdir()
    (family / "v1.md").write_text("Alpha one", encoding="utf-8")
    (family / "v2.md").write_text("Alpha two Beta", encoding="utf-8")
    cfg = {
        "tracking_id": "t",
        "versions_dir": str(family),
        "version_naming": "sequential",
        "granularity": "line",
        "out_dir": str(tmp_path / "o"),
    }
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    rc = main(["run", "--config", str(p), "--concepts", "Alpha,Beta"])
    assert rc == 0
    out = capsys.readouterr().out
    summary = json.loads(out)
    assert summary["diff_count"] == 1
    assert "Alpha" in summary["concepts"]
