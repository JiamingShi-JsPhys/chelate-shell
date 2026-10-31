"""Router tests: plan building, dry-run, FAIL hard-block, promotion lock."""
from __future__ import annotations

import os

import pytest

from core import router
from core.registry import Registry


@pytest.fixture()
def reg():
    from conftest import SKILLS_DIR
    return Registry().scan(str(SKILLS_DIR))


def _record(status, skill="reference-auditor", stage="gates"):
    return {"skill": skill, "stage": stage, "action": "gate",
            "status": status, "evidence_level": "EXACT" if status == "FAIL"
            else "UNVERIFIED", "reason": f"stub {status}", "artifacts": []}


def test_build_plan_modes(reg):
    plan_a = router.build_plan(reg, "a", "pdf", None)
    # a PDF matches both capstone-labmate (.cap + pdf) and fulltext-extractor
    ingest_names = [r.name for r in plan_a["ingest"]]
    assert ingest_names == ["capstone-labmate", "fulltext-extractor"]
    assert len(plan_a["gates"]) == 7
    assert [r.name for r in plan_a["processors"]] == [
        "ai-trace-remover", "figure-generator", "latex-exporter"]

    plan_b = router.build_plan(reg, "b", "pdf", None)
    assert [r.name for r in plan_b["ingest"]] == ["capstone-labmate",
                                                  "fulltext-extractor"]
    assert plan_b["gates"] == [] and plan_b["processors"] == []

    plan_c = router.build_plan(reg, "c", "",
                               ["formula-validator", "reference-auditor"])
    assert [r.name for r in plan_c["gates"]] == ["formula-validator",
                                                 "reference-auditor"]


def test_build_plan_mode_a_runs_all_gates(reg):
    plan = router.build_plan(reg, "a", "", None)
    assert len(plan["gates"]) == 7
    assert {r.name for r in plan["gates"]} == {
        "formula-validator", "longitudinal-analysis", "conflict-detector",
        "reference-auditor", "data-profiler",
        "ml-auditor", "quantitative-validator"}


def test_stage_order_is_canonical():
    assert router.STAGE_ORDER == ("workspace", "ingest", "gates",
                                  "processors")
    assert router.STAGE_ACTION["gates"] == "gate"


def test_dry_run_lists_plan_without_executing(reg, workspace, monkeypatch,
                                              capsys):
    def boom(*a, **k):
        raise AssertionError("dry-run must not execute skills")
    monkeypatch.setattr(router, "run_skill", boom)
    result = router.run(str(workspace), mode="a", input_kind="pdf",
                        dry_run=True)
    planned = [p["skill"] for p in result["planned"]]
    assert planned[0] == "capstone-labmate"  # pdf matches capstone first
    assert "fulltext-extractor" in planned
    assert "reference-auditor" in planned
    assert planned[-1] == "latex-exporter"
    assert not list((workspace / "results").glob("promoted_*"))
    assert "DRY RUN" in capsys.readouterr().out


def test_gate_fail_terminates_pipeline_and_locks_process(workspace,
                                                         monkeypatch):
    """First FAIL gate stops the run; nothing is promoted to results/."""
    calls = []

    def fake_run_skill(rec, root, action, extra_args, timeout=600, debug=False):
        calls.append(rec.name)
        if rec.name == "reference-auditor":
            return _record("FAIL")
        return _record("PASS", skill=rec.name)

    monkeypatch.setattr(router, "load_default_registry",
                        lambda: _FakeRegistry())
    monkeypatch.setattr(router, "run_skill", fake_run_skill)
    result = router.run(str(workspace), mode="a", input_kind="pdf")
    assert result["terminated_by"] == "reference-auditor"
    assert result["promoted"] is False
    # skills after the failing gate never ran
    assert calls == ["fulltext-extractor", "formula-validator",
                     "reference-auditor"]
    assert not list((workspace / "results").glob("promoted_*"))
    # intermediate products stay in process/
    assert (workspace / "process" / "gates").is_dir()
    # report + broadcast still written for audit
    assert os.path.isfile(result["report"])
    assert os.path.isfile(result["broadcast"])


def test_full_pass_promotes_process_to_results(workspace, monkeypatch):
    monkeypatch.setattr(router, "load_default_registry",
                        lambda: _FakeRegistry())
    monkeypatch.setattr(router, "run_skill",
                        lambda rec, root, action, extra, timeout=600, debug=False:
                        _record("PASS", skill=rec.name))
    result = router.run(str(workspace), mode="a", input_kind="pdf")
    assert result["terminated_by"] is None
    assert result["promoted"] is True
    promoted = list((workspace / "results").glob("promoted_*"))
    assert len(promoted) == 1
    assert (promoted[0] / "gates").is_dir()


def test_red_fail_output(workspace, monkeypatch, capsys):
    monkeypatch.setattr(router, "load_default_registry",
                        lambda: _FakeRegistry())
    monkeypatch.setattr(router, "run_skill",
                        lambda rec, root, action, extra, timeout=600, debug=False:
                        _record("FAIL", skill=rec.name))
    # `_color()` honours NO_COLOR before it looks at CHELATE_FORCE_COLOR, so a
    # developer shell that exports NO_COLOR (the standard "no ANSI in pipes"
    # convention) would otherwise fail this test on a correct implementation.
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CHELATE_FORCE_COLOR", "1")
    router.run(str(workspace), mode="a", input_kind="pdf")
    out = capsys.readouterr()
    combined = out.out + out.err
    assert "\033[31m" in combined, "FAIL must print in red"
    assert "FAIL" in combined


class _FakeRecord:
    def __init__(self, name, stage):
        self.name, self.stage = name, stage
        self.entrypoint = "run.py"
        self.run_path = f"skills/{name}/run.py"
        self.dependencies = []


class _TypedRecord:
    """Fake SkillRecord with manifest input_types for --inputs wiring."""

    def __init__(self, name, stage, input_types):
        self.name, self.stage = name, stage
        self.input_types = input_types
        self.entrypoint = "run.py"
        self.run_path = f"skills/{name}/run.py"
        self.dependencies = []


# ------------------------------------------------------- --inputs auto-wiring

def test_auto_input_wiring_follows_manifest_types():
    flat = [("gates", _TypedRecord("data-profiler", "gates",
                                   ["csv", "dataset"])),
            ("gates", _TypedRecord("reference-auditor", "gates",
                                   ["markdown"]))]
    auto, warnings = router._auto_input_args(
        flat, ["/ws/data.csv"], probe=lambda rec: True)
    assert auto == {"data-profiler": ["--input", "/ws/data.csv"]}
    assert warnings == []


def test_auto_input_wiring_skips_adapters_without_input_flag():
    flat = [("gates", _TypedRecord("formula-validator", "gates",
                                   ["plain_text"])),
            ("gates", _TypedRecord("reference-auditor", "gates",
                                   ["markdown"]))]
    auto, warnings = router._auto_input_args(
        flat, ["/ws/draft.md"],
        probe=lambda rec: rec.name == "reference-auditor")
    assert auto == {"reference-auditor": ["--input", "/ws/draft.md"]}
    assert warnings == []


def test_auto_input_wiring_warns_when_no_skill_accepts_input():
    flat = [("gates", _TypedRecord("data-profiler", "gates", ["csv"]))]
    # photo.xyz declares no manifest type (reported by run(), not here);
    # data.csv matches the type but the probe rejects the adapter
    auto, warnings = router._auto_input_args(
        flat, ["/ws/photo.xyz", "/ws/a.csv"], probe=lambda rec: False)
    assert auto == {}
    assert len(warnings) == 1 and "csv" in warnings[0]


def test_auto_input_wiring_keeps_first_file_per_skill():
    flat = [("gates", _TypedRecord("data-profiler", "gates", ["csv"]))]
    auto, warnings = router._auto_input_args(
        flat, ["/ws/a.csv", "/ws/b.csv"], probe=lambda rec: True)
    assert auto == {"data-profiler": ["--input", "/ws/a.csv"]}
    assert any("single --input" in w for w in warnings)


def test_input_type_by_ext_covers_documented_inputs():
    assert router.INPUT_TYPE_BY_EXT["md"] == "markdown"
    assert router.INPUT_TYPE_BY_EXT["csv"] == "csv"
    assert router.INPUT_TYPE_BY_EXT["pdf"] == "pdf"
    assert router.INPUT_TYPE_BY_EXT["bib"] == "bib"


def test_adapter_probe_detects_input_flag_on_real_adapters():
    from conftest import SKILLS_DIR
    reg = Registry().scan(str(SKILLS_DIR))
    assert router._adapter_accepts_input(reg.get("data-profiler")) is True
    assert router._adapter_accepts_input(reg.get("task-organizer")) is False


def test_dry_run_shows_auto_wired_inputs(workspace, capsys):
    csv = workspace / "data.csv"
    csv.write_text("x,y\n1,2\n", encoding="utf-8")
    result = router.run(str(workspace), mode="c",
                        selected=["data-profiler"], dry_run=True,
                        inputs=[str(csv)])
    entry = result["planned"][0]
    assert entry["skill"] == "data-profiler"
    assert entry["input"] == str(csv)
    assert "--input" in capsys.readouterr().out


def test_inputs_auto_wired_end_to_end(workspace, tmp_path):
    """--inputs data.csv must reach data-profiler without --skill-arg."""
    csv = tmp_path / "data.csv"
    csv.write_text("x,y\n1,2\n3,4\n5,6\n", encoding="utf-8")
    result = router.run(str(workspace), mode="c",
                        selected=["data-profiler"], inputs=[str(csv)])
    assert result["terminated_by"] is None
    assert result["promoted"] is True
    assert result["auto_inputs"] == {"data-profiler": str(csv)}
    decision = result["decisions"][0]
    assert decision["status"] == "PASS"
    assert "--input" in decision["command"]
    assert str(csv) in decision["command"]


def test_run_skill_routes_sandbox_required_to_multiprocessing(tmp_path):
    """A record with sandbox_required=True must be dispatched through the
    multiprocessing sandbox and report UNVERIFIED (not crash) when the
    child cannot start (run.py missing)."""
    class _SandboxRec:
        name = "demo-sandbox-skill"
        stage = "gates"
        run_path = "skills/__nonexistent__/run.py"
        dependencies = []
        sandbox_required = True

    rec = _SandboxRec()
    record = router.run_skill(rec, str(tmp_path), "gate", [], timeout=10,
                             debug=False)
    assert record["status"] == "UNVERIFIED"
    assert record["sandbox"] is False  # it failed fast, not by timeout
    assert "sandbox child" in record["reason"]


def test_run_skill_routes_non_sandbox_via_subprocess(monkeypatch):
    """A record without sandbox_required keeps using the v1.1.x subprocess
    path (verified by faking the sandbox module function and ensuring it is
    NOT called)."""
    called = []

    def _fake_sandboxed(*a, **k):
        called.append(True)
        return {"status": "PASS"}

    import core.sandbox as sandbox_mod
    monkeypatch.setattr(sandbox_mod, "run_skill_sandboxed", _fake_sandboxed)

    class _PlainRec:
        name = "demo-plain-skill"
        stage = "gates"
        run_path = "skills/__nonexistent__/run.py"
        dependencies = []
        sandbox_required = False

    router.run_skill(_PlainRec(), "/tmp/x", "gate", [], timeout=10)
    assert not called, "sandbox path must NOT be used for sandbox_required=false"


class _FakeRegistry:
    """Minimal 4-skill pipeline: pdf ingest -> 2 gates -> processor."""

    def __init__(self):
        self.errors = []
        self._all = [_FakeRecord("fulltext-extractor", "ingest"),
                     _FakeRecord("formula-validator", "gates"),
                     _FakeRecord("reference-auditor", "gates"),
                     _FakeRecord("ai-trace-remover", "processors")]

    def all(self):
        return list(self._all)

    def by_stage(self, stage):
        return [r for r in self._all if r.stage == stage]

    def by_input(self, kind, stage=None):
        pool = self.by_stage(stage) if stage else self._all
        return [r for r in pool if r.name == "fulltext-extractor"]

    def get(self, name):
        return next((r for r in self._all if r.name == name), None)

    def names(self):
        return [r.name for r in self._all]

    def __len__(self):
        return len(self._all)


def test_inputs_narrow_the_plan_to_matching_skills(workspace, capsys):
    csv = workspace / "data.csv"
    csv.write_text("x,y\n1,2\n", encoding="utf-8")
    result = router.run(str(workspace), mode="a", inputs=[str(csv)],
                        dry_run=True)
    names = [p["skill"] for p in result["planned"]]
    # only csv-accepting skills survive the filter; pdf/bib/markdown/
    # video/query consumers drop out instead of crashing on missing args.
    # (ml-auditor declares the csv input type, so it joins the plan now that
    # it has graduated from a skeleton.)
    assert set(names) == {"conflict-detector", "data-profiler",
                          "longitudinal-analysis", "ml-auditor",
                          "figure-generator"}
    entry = next(p for p in result["planned"] if p["skill"] == "data-profiler")
    assert entry["input"] == str(csv)


def test_selected_skills_are_not_filtered_by_inputs(workspace, monkeypatch):
    md = workspace / "draft.md"
    md.write_text("text", encoding="utf-8")
    monkeypatch.setattr(router, "run_skill",
                        lambda rec, root, action, extra, timeout=600,
                        debug=False: _record("PASS", skill=rec.name))
    # formula-validator does not declare markdown, but --selected is
    # explicit intent and must win over the --inputs narrowing
    result = router.run(str(workspace), mode="c",
                        selected=["formula-validator"], inputs=[str(md)])
    assert [d["skill"] for d in result["decisions"]] == ["formula-validator"]


def test_unknown_input_type_yields_empty_plan_with_warning(workspace, capsys):
    xyz = workspace / "photo.xyz"
    xyz.write_text("x", encoding="utf-8")
    result = router.run(str(workspace), mode="a", inputs=[str(xyz)],
                        dry_run=True)
    assert result.get("note") == "no skills matched the requested pipeline"
    out = capsys.readouterr().out
    assert "[INPUT]" in out and "xyz" in out


def test_legacy_usage_error_degrades_to_unverified(tmp_path):
    """An argparse usage error is 'not verified', never a data FAIL.

    conflict-detector's legacy CLI requires --config; invoked without it
    (as the Router does when no input was wired) it must emit UNVERIFIED
    so an incomplete invocation cannot hard-block the pipeline.
    """
    import json
    import subprocess
    import sys
    from conftest import REPO_ROOT

    ws = tmp_path / "ws"
    (ws / "process" / "gates").mkdir(parents=True)
    proc = subprocess.run(
        [sys.executable, "skills/conflict-detector/run.py",
         "--root", str(ws), "--action", "gate"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0
    gates = sorted((ws / "process" / "gates").glob("conflict-detector_*.json"))
    assert gates, proc.stdout + proc.stderr
    gate = json.loads(gates[-1].read_text(encoding="utf-8"))
    assert gate["status"] == "UNVERIFIED"
    assert "invocation incomplete" in gate["reason"]
