"""CLI tests: --inputs parsing, workspace resolution and fail-fast behavior."""
from __future__ import annotations

import os

import cli


def test_pipeline_parser_accepts_one_or_more_inputs():
    args = cli.build_parser().parse_args(
        ["pipeline", "--root", ".", "--inputs", "draft.md"])
    assert args.inputs == ["draft.md"]
    args = cli.build_parser().parse_args(
        ["pipeline", "--root", ".", "--inputs", "a.md", "b.csv", "c.pdf"])
    assert args.inputs == ["a.md", "b.csv", "c.pdf"]


def test_pipeline_without_inputs_defaults_to_empty():
    args = cli.build_parser().parse_args(["pipeline", "--root", "."])
    assert args.inputs == []


def test_missing_input_fails_fast_before_running(tmp_path, monkeypatch,
                                                 capsys):
    def boom(*a, **k):
        raise AssertionError("router must not run when an input is missing")
    monkeypatch.setattr(cli, "router_run", boom)
    args = cli.build_parser().parse_args(
        ["pipeline", "--root", str(tmp_path), "--inputs", "ghost.md"])
    assert cli.cmd_pipeline(args) == 2
    err = capsys.readouterr().err
    assert "ghost.md" in err and "not found" in err


def test_pipeline_forwards_resolved_inputs_to_router(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "data.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    captured = {}

    def fake_run(root, **kwargs):
        captured["root"] = root
        captured.update(kwargs)
        return {"terminated_by": None}

    monkeypatch.setattr(cli, "router_run", fake_run)
    args = cli.build_parser().parse_args(
        ["pipeline", "--root", str(ws), "--mode", "c",
         "--selected", "data-profiler", "--inputs", "data.csv"])
    assert cli.cmd_pipeline(args) == 0
    assert captured["inputs"] == [os.path.abspath(str(ws / "data.csv"))]
    assert captured["mode"] == "c"
    assert captured["selected"] == ["data-profiler"]
