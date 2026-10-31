"""Output-path contract: every skill writes inside the workspace only.

Regression guard for the v1.1.1 fix: when the skills run as a Claude Code
plugin, the legacy code's own defaults (`_reports/`, `work/`, `output/`)
are anchored to the skill directory — which in a plugin install is the
host's cache directory, and writing there gets the run flagged as an
out-of-scope write. The adapter layer now guarantees:

  * `--root <workspace>` is required; without it an adapter exits 2 and
    writes nothing;
  * the legacy CLI runs with cwd = the workspace root, so relative
    defaults land inside the workspace;
  * `output_dirs` injects `--flag <root>/<subdir>` before the user's own
    arguments (explicit flags still win);
  * formula-validator's module-level `REPORT_DIR` is re-anchored to
    `<root>/process/reports/` before the legacy CLI writes anything.

These tests assert the *observable* contract — skill directories and the
repository root stay byte-identical across runs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import ROUTED_SKILLS, REPO_ROOT, SKILLS_DIR, run_path_of  # noqa: E402
from lib.chelate_core import adapter  # noqa: E402

PYTHON = sys.executable


def _snapshot(path: str):
    """Set of (relative path, size) for every file under *path*."""
    out = set()
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            p = os.path.join(root, f)
            try:
                out.add((os.path.relpath(p, path), os.path.getsize(p)))
            except OSError:
                pass
    return out


# ------------------------------------------------------- flag splitting


def test_split_legacy_argv_keeps_flag_value_pairs_together():
    """argparse REMAINDER reorders unknown options; the hand-rolled split
    must keep "--expr value" adjacent (the v1.1.1 regression)."""
    argv = ["--root", "/ws", "--action", "validate", "--expr", "v = d/t",
            "--units", "v=m/s"]
    own, rest, debug_on, help_on = adapter.split_legacy_argv(argv)
    assert own["--root"] == "/ws"
    assert own["--action"] == "validate"
    assert not debug_on and not help_on
    assert rest == ["--expr", "v = d/t", "--units", "v=m/s"]


def test_split_legacy_argv_equals_form_and_flags():
    own, rest, debug_on, help_on = adapter.split_legacy_argv(
        ["--root=/ws", "--action=check", "--debug", "--expr", "x"])
    assert own["--root"] == "/ws" and own["--action"] == "check"
    assert debug_on and rest == ["--expr", "x"]
    assert adapter.split_legacy_argv(["--help"])[3] is True
    assert adapter.split_legacy_argv(["-h"])[3] is True


# ------------------------------------------------------- output_dirs


def test_inject_output_dirs_prepends_and_respects_explicit_flags():
    call = ["validate", "--expr", "x"]
    out = adapter._inject_output_dirs(call, "/ws", {"--report": "process/r"})
    assert len(out) == 5 and out[0] == "--report"
    assert os.path.normpath(out[1]) == os.path.normpath("/ws/process/r")
    assert out[2:] == ["validate", "--expr", "x"]
    # an explicit flag on the command line is never duplicated/overridden
    explicit = ["validate", "--report", "/mine.md"]
    out = adapter._inject_output_dirs(explicit, "/ws",
                                      {"--report": "process/r"})
    assert out == explicit


def test_resolve_output_dirs_scopes_flags_per_action():
    actions = {"run": ("m", "f", "sub"), "verify": ("m", "f", "sub")}
    spec = {"--output": "process/out",
            "run": {"--workdir": "process/work"}}
    assert adapter._resolve_output_dirs(spec, actions, "verify") == \
        {"--output": "process/out"}
    assert adapter._resolve_output_dirs(spec, actions, "run") == \
        {"--output": "process/out", "--workdir": "process/work"}
    assert adapter._resolve_output_dirs(None, actions, "run") == {}


# ------------------------------------------------------- --root required


@pytest.mark.parametrize("skill", ROUTED_SKILLS)
def test_adapter_refuses_to_run_without_root(skill):
    """No --root -> exit 2, nothing written anywhere."""
    proc = subprocess.run(
        [PYTHON, str(run_path_of(skill)), "--action", "gate"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2, f"{skill}: {proc.stdout[-200:]}"
    assert "--root" in proc.stderr


@pytest.mark.parametrize("skill", ROUTED_SKILLS)
def test_adapter_writes_nothing_outside_the_workspace(skill, tmp_path):
    """The whole point of v1.1.1: a real adapter run must leave the skill
    directory and the repository root byte-identical, with all gates
    inside <workspace>/process/gates/."""
    ws = tmp_path / "ws"
    ws.mkdir()
    skill_dir = SKILLS_DIR / skill
    before_skill = _snapshot(str(skill_dir))
    before_repo = _snapshot(str(REPO_ROOT))

    proc = subprocess.run(
        [PYTHON, str(run_path_of(skill)), "--root", str(ws),
         "--action", "gate"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"{skill}: {proc.stdout[-300:]}"

    after_skill = _snapshot(str(skill_dir))
    after_repo = _snapshot(str(REPO_ROOT))
    assert after_skill == before_skill, \
        f"{skill} wrote into its own directory: " \
        f"{sorted(set(after_skill) - set(before_skill))[:5]}"
    new_repo = set(after_repo) - set(before_repo)
    assert not new_repo, \
        f"{skill} polluted the repo root: {sorted(new_repo)[:5]}"

    gates = sorted((ws / "process" / "gates").glob(f"{skill}_*.json"))
    assert gates, f"{skill} wrote no gate into the workspace: {proc.stdout}"
    gate = json.loads(gates[-1].read_text(encoding="utf-8"))
    assert gate["skill"] == skill
    assert gate["status"] in {"PASS", "FAIL", "UNVERIFIED"}


# ------------------------------------------------------- formula-validator


def test_formula_validator_dimensional_error_lands_in_workspace(tmp_path):
    """The user's exact Claude Code scenario: a dimensional error is
    intercepted (FAIL/SYMBOLIC) and the Markdown report is written to
    <workspace>/process/reports/ — never the skill's _reports/."""
    ws = tmp_path / "ws"
    ws.mkdir()
    skill_dir = SKILLS_DIR / "formula-validator"
    before = _snapshot(str(skill_dir))

    proc = subprocess.run(
        [PYTHON, str(skill_dir / "run.py"), "--root", str(ws),
         "--action", "validate", "--expr", "v = d/t",
         "--units", "v=m", "--units", "d=m", "--units", "t=s"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-300:]
    gate = json.loads(proc.stdout.strip().splitlines()[-1])
    assert gate["status"] == "FAIL"
    assert gate["evidence_level"] == "SYMBOLIC"

    reports = sorted((ws / "process" / "reports").glob("*.md"))
    assert reports, "no report inside the workspace"
    assert (ws / "process" / "reports" / "latest.md").is_file()
    # the report path reported in the gate must be the workspace one
    assert gate["artifacts"]
    for art in gate["artifacts"]:
        assert str(ws.resolve()) in os.path.abspath(art)
    # skill directory untouched (no _reports/ re-created)
    assert _snapshot(str(skill_dir)) == before


def test_formula_validator_units_action_requires_expr(tmp_path):
    """units action without --expr -> FAIL gate, no report written."""
    ws = tmp_path / "ws"
    ws.mkdir()
    proc = subprocess.run(
        [PYTHON, str(SKILLS_DIR / "formula-validator" / "run.py"),
         "--root", str(ws), "--action", "units"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0
    gate = json.loads(proc.stdout.strip().splitlines()[-1])
    assert gate["status"] == "FAIL"
    assert not list((ws / "process" / "reports").glob("*.md"))


def test_explicit_output_flag_wins_over_injected_default(tmp_path):
    """--skill-arg "--report /my.md" must beat the adapter's injection."""
    ws = tmp_path / "ws"
    ws.mkdir()
    mine = tmp_path / "my-report.md"
    proc = subprocess.run(
        [PYTHON, str(SKILLS_DIR / "formula-validator" / "run.py"),
         "--root", str(ws), "--action", "validate", "--expr", "v = d/t",
         "--units", "v=m/s", "--units", "d=m", "--units", "t=s",
         "--report", str(mine)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0
    assert mine.is_file(), "explicit --report was not honoured"
