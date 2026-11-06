"""In-process CLI tests (call run.main directly, no subprocess)."""

import json
import sys
from pathlib import Path

from scripts import run as run_mod
from scripts.run import main


def _seed_workdir(work):
    (work / "data").mkdir(parents=True, exist_ok=True)
    (work / "data" / "clean.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (work / "results").mkdir(parents=True, exist_ok=True)
    (work / "results" / "lmm.json").write_text('{"x":1}', encoding="utf-8")


def test_dryrun_prints_plan(tmp_path, capsys):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({
        "param_space": {"dimensions": [{"name": "a", "values": [1, 2]}]},
        "critical_paths": ["data/clean.csv"],
        "plugin": {"command": "true {OUT}"},
    }))
    rc = main(["dryrun", "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Total rounds: 2" in out
    assert "round    1" in out


def test_run_full_sweep_writes_outputs(tmp_path):
    work = tmp_path / "work"
    out = tmp_path / "output"
    _seed_workdir(work)
    cmd = f"{sys.executable} {tmp_path / 'bin' / 'p.py'} {{PARAMS}} {{OUT}}"
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "p.py").write_text(
        "import sys, json\n"
        "from pathlib import Path\n"
        "Path(sys.argv[2]).write_text(json.dumps({'ok': True}))\n"
        "raise SystemExit(0)\n"
    )
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({
        "param_space": {"dimensions": [
            {"name": "a", "values": [1, 2]}, {"name": "b", "values": ["x", "y"]}]},
        "critical_paths": ["data/clean.csv", "results/lmm.json"],
        "plugin": {"command": cmd},
        "workdir": str(work), "output": str(out),
    }))
    rc = main(["run", "--config", str(cfg)])
    assert rc == 0
    audit = out / "audit_log.jsonl"
    lines = audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4  # 4 rounds
    assert (out / "results_summary.csv").exists()
    assert (out / "results_summary.md").exists()
    assert (out / "report_draft.md").exists()
    assert (out / "run_metadata.json").exists()
    # content-addressed store captured the two critical files
    assert len(list((out / "snapshots" / "store").iterdir())) == 2


def test_run_with_failure_triggers_auto_rollback(tmp_path):
    work = tmp_path / "work"
    out = tmp_path / "output"
    _seed_workdir(work)
    # plugin fails when b == "y"
    script = tmp_path / "bin" / "p.py"
    (tmp_path / "bin").mkdir(exist_ok=True)
    script.write_text(
        "import sys, json\n"
        "from pathlib import Path\n"
        "params = json.loads(Path(sys.argv[1]).read_text())\n"
        "Path(sys.argv[2]).write_text(json.dumps({'ok': True}))\n"
        "raise SystemExit(1 if params.get('b') == 'y' else 0)\n"
    )
    cmd = f"{sys.executable} {script} {{PARAMS}} {{OUT}}"
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({
        "param_space": {"dimensions": [
            {"name": "a", "values": [1, 2]}, {"name": "b", "values": ["x", "y"]}]},
        "critical_paths": ["data/clean.csv"],
        "plugin": {"command": cmd}, "workdir": str(work), "output": str(out),
    }))
    rc = main(["run", "--config", str(cfg)])
    assert rc == 1  # at least one round failed
    lines = (out / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    statuses = [json.loads(l)["status"] for l in lines]
    assert "rolledback" in statuses  # auto-rollback was recorded


def test_rollback_subcommand(tmp_path):
    work = tmp_path / "work"
    out = tmp_path / "output"
    _seed_workdir(work)
    cmd = f"{sys.executable} {tmp_path / 'bin' / 'p.py'} {{PARAMS}} {{OUT}}"
    (tmp_path / "bin").mkdir(exist_ok=True)
    (tmp_path / "bin" / "p.py").write_text(
        "import sys, json\nfrom pathlib import Path\n"
        "Path(sys.argv[2]).write_text(json.dumps({'ok': True}))\nraise SystemExit(0)\n")
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({
        "param_space": {"dimensions": [{"name": "a", "values": [1, 2]}]},
        "critical_paths": ["data/clean.csv", "results/lmm.json"],
        "plugin": {"command": cmd}, "workdir": str(work), "output": str(out),
    }))
    assert main(["run", "--config", str(cfg)]) == 0
    rc = main(["rollback", "--config", str(cfg), "--round", "1"])
    assert rc == 0
    assert (work.parent / "work.rollback_0001").exists()


def test_verify_and_summary_subcommands(tmp_path):
    work = tmp_path / "work"
    out = tmp_path / "output"
    _seed_workdir(work)
    cmd = f"{sys.executable} {tmp_path / 'bin' / 'p.py'} {{PARAMS}} {{OUT}}"
    (tmp_path / "bin").mkdir(exist_ok=True)
    (tmp_path / "bin" / "p.py").write_text(
        "import sys, json\nfrom pathlib import Path\n"
        "Path(sys.argv[2]).write_text(json.dumps({'ok': True}))\nraise SystemExit(0)\n")
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({
        "param_space": {"dimensions": [{"name": "a", "values": [1, 2]}]},
        "critical_paths": ["data/clean.csv"],
        "plugin": {"command": cmd}, "workdir": str(work), "output": str(out),
    }))
    assert main(["run", "--config", str(cfg)]) == 0
    assert main(["verify", "--config", str(cfg), "--round", "1"]) == 0
    assert main(["summary", "--config", str(cfg)]) == 0


def test_missing_config_exits_usage(tmp_path):
    rc = main(["run", "--config", str(tmp_path / "nope.json")])
    assert rc == 2


def test_no_action_prints_help():
    rc = main([])
    assert rc == 2


def _write_plugin(tmp_path, body):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "p.py"
    script.write_text(body, encoding="utf-8")
    return f"{sys.executable} {script} {{PARAMS}} {{OUT}}"


def test_run_overrides_workdir_and_output(tmp_path):
    work = tmp_path / "work"
    out = tmp_path / "output"
    _seed_workdir(work)
    cmd = _write_plugin(tmp_path,
        "import sys, json\nfrom pathlib import Path\n"
        "Path(sys.argv[2]).write_text(json.dumps({'ok': True}))\nraise SystemExit(0)\n")
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({
        "param_space": {"dimensions": [{"name": "a", "values": [1, 2]}]},
        "critical_paths": ["data/clean.csv"],
        "plugin": {"command": cmd},
    }))
    rc = main(["run", "--config", str(cfg),
               "--workdir", str(work), "--output", str(out)])
    assert rc == 0
    assert (out / "audit_log.jsonl").exists()
    # the override paths were actually used
    assert (out / "results_summary.csv").exists()


def test_rollback_unknown_round_exits(tmp_path):
    work = tmp_path / "work"
    out = tmp_path / "output"
    _seed_workdir(work)
    cmd = _write_plugin(tmp_path,
        "import sys, json\nfrom pathlib import Path\n"
        "Path(sys.argv[2]).write_text(json.dumps({'ok': True}))\nraise SystemExit(0)\n")
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({
        "param_space": {"dimensions": [{"name": "a", "values": [1]}]},
        "critical_paths": ["data/clean.csv"],
        "plugin": {"command": cmd}, "workdir": str(work), "output": str(out),
    }))
    assert main(["run", "--config", str(cfg)]) == 0
    rc = main(["rollback", "--config", str(cfg), "--round", "99"])
    assert rc == 2  # round 99 was never recorded


def test_verify_unknown_round_exits(tmp_path):
    work = tmp_path / "work"
    out = tmp_path / "output"
    _seed_workdir(work)
    cmd = _write_plugin(tmp_path,
        "import sys, json\nfrom pathlib import Path\n"
        "Path(sys.argv[2]).write_text(json.dumps({'ok': True}))\nraise SystemExit(0)\n")
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({
        "param_space": {"dimensions": [{"name": "a", "values": [1]}]},
        "critical_paths": ["data/clean.csv"],
        "plugin": {"command": cmd}, "workdir": str(work), "output": str(out),
    }))
    assert main(["run", "--config", str(cfg)]) == 0
    rc = main(["verify", "--config", str(cfg), "--round", "99"])
    assert rc == 2


def test_subcommands_honor_output_override(tmp_path):
    work = tmp_path / "work"
    out = tmp_path / "output"
    alt = tmp_path / "alt_output"
    _seed_workdir(work)
    cmd = _write_plugin(tmp_path,
        "import sys, json\nfrom pathlib import Path\n"
        "Path(sys.argv[2]).write_text(json.dumps({'ok': True}))\nraise SystemExit(0)\n")
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({
        "param_space": {"dimensions": [{"name": "a", "values": [1]}]},
        "critical_paths": ["data/clean.csv"],
        "plugin": {"command": cmd}, "workdir": str(work), "output": str(out),
    }))
    assert main(["run", "--config", str(cfg)]) == 0
    # rollback/verify read the audit log from --output, so point at the run dir.
    assert main(["rollback", "--config", str(cfg), "--round", "1",
                 "--output", str(out)]) == 0
    assert main(["verify", "--config", str(cfg), "--round", "1",
                 "--output", str(out)]) == 0
    # summary regenerates the tables into an alternate directory.
    assert main(["summary", "--config", str(cfg), "--output", str(alt)]) == 0
    assert (alt / "results_summary.csv").exists()
