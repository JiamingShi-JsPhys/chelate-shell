"""CLI tests: --inputs parsing, workspace resolution and fail-fast behavior."""
from __future__ import annotations

import json
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
    # Publication is a separate step (tests/test_runtime.py covers it); this
    # test is about what the router is handed.
    monkeypatch.setattr(cli, "_publish_or_hold", lambda *a, **k: None)
    args = cli.build_parser().parse_args(
        ["pipeline", "--root", str(ws), "--mode", "c",
         "--selected", "data-profiler", "--inputs", "data.csv"])
    assert cli.cmd_pipeline(args) == 0
    assert captured["inputs"] == [os.path.abspath(str(ws / "data.csv"))]
    assert captured["mode"] == "c"
    assert captured["selected"] == ["data-profiler"]


def test_status_reports_the_active_runtime(tmp_path, capsys):
    args = cli.build_parser().parse_args(["status", "--root", str(tmp_path)])
    assert cli.cmd_status(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["runtime"] == "policy"
    assert report["containment"] == "policy-only"
    assert report["ok"] is True


def test_status_fails_closed_when_the_broker_is_missing(tmp_path, monkeypatch,
                                                       capsys):
    monkeypatch.setenv("CHELATE_RUNTIME", "broker")
    args = cli.build_parser().parse_args(["status", "--root", str(tmp_path)])
    assert cli.cmd_status(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert "broker" in report["error"]


def test_recipe_dry_run_prints_the_plan(tmp_path, capsys):
    folder = tmp_path / "recipes"
    folder.mkdir()
    (folder / "review.json").write_text(json.dumps({
        "name": "review",
        "steps": [{"skill": "data-profiler", "args": []}],
    }), encoding="utf-8")
    args = cli.build_parser().parse_args(
        ["recipe", "--root", str(tmp_path), "--name", "review", "--dry-run"])
    assert cli.cmd_recipe(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan"][0]["skill"] == "data-profiler"


def test_recipe_with_an_unknown_name_exits_2(tmp_path, capsys):
    args = cli.build_parser().parse_args(
        ["recipe", "--root", str(tmp_path), "--name", "nope", "--dry-run"])
    assert cli.cmd_recipe(args) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False



def test_pipeline_summary_prints_a_tally_not_the_record(tmp_path, monkeypatch,
                                                        capsys):
    def fake_run(root, **kwargs):
        return {"terminated_by": None, "blocked": None, "promoted": False,
                "decisions": [{"skill": "data-profiler", "status": "PASS",
                               "reason": "5 rows"}],
                "planned": None}

    monkeypatch.setattr(cli, "router_run", fake_run)
    monkeypatch.setattr(cli, "_publish_or_hold", lambda *a, **k: None)
    args = cli.build_parser().parse_args(
        ["pipeline", "--root", str(tmp_path), "--summary"])
    assert cli.cmd_pipeline(args) == 0
    out = capsys.readouterr().out
    assert "summary: 1 skill run(s)" in out
    assert "PASS 1" in out
    assert "{" not in out


def test_pipeline_approve_publish_publishes_the_declared_bytes(
        tmp_path, monkeypatch):
    """The three steps that now make up publication, end to end.

    pipeline produces and stops (blocked: approval); approve names those
    bytes; publish submits the same manifest. Nothing is published before
    the token exists, and what lands in results/ is exactly what the
    manifest declared.
    """
    ws = tmp_path / "ws"
    (ws / "process").mkdir(parents=True)

    def fake_run(root, **kwargs):
        (ws / "process" / "report.md").write_text("result\n", encoding="utf-8")
        return {"terminated_by": None, "decisions": [], "planned": None}

    monkeypatch.setattr(cli, "router_run", fake_run)
    monkeypatch.setenv(cli.approval.UNSAFE_AUTO_ENV, "1")

    args = cli.build_parser().parse_args(
        ["pipeline", "--root", str(ws), "--mode", "c",
         "--selected", "data-profiler"])
    assert cli.cmd_pipeline(args) == 1          # withheld: no approval yet
    pending = ws / ".chelate" / "pending" / "manifest.json"
    assert pending.is_file()
    assert not (ws / "results").exists()

    args = cli.build_parser().parse_args(["approve", "--root", str(ws)])
    assert cli.cmd_approve(args) == 0

    args = cli.build_parser().parse_args(["publish", "--root", str(ws)])
    assert cli.cmd_publish(args) == 0
    promoted = list((ws / "results").glob("promoted_*"))
    assert len(promoted) == 1
    assert (promoted[0] / "report.md").read_text(encoding="utf-8") == "result\n"


def test_approve_then_edit_then_publish_is_refused(tmp_path, monkeypatch):
    """An approval names bytes; changing them voids it."""
    ws = tmp_path / "ws"
    (ws / "process").mkdir(parents=True)

    def fake_run(root, **kwargs):
        (ws / "process" / "report.md").write_text("first\n", encoding="utf-8")
        return {"terminated_by": None, "decisions": [], "planned": None}

    monkeypatch.setattr(cli, "router_run", fake_run)
    monkeypatch.setenv(cli.approval.UNSAFE_AUTO_ENV, "1")
    args = cli.build_parser().parse_args(["pipeline", "--root", str(ws)])
    assert cli.cmd_pipeline(args) == 1
    args = cli.build_parser().parse_args(["approve", "--root", str(ws)])
    assert cli.cmd_approve(args) == 0

    (ws / "process" / "report.md").write_text("second\n", encoding="utf-8")
    args = cli.build_parser().parse_args(["publish", "--root", str(ws)])
    assert cli.cmd_publish(args) == 1
    assert not (ws / "results").exists()
