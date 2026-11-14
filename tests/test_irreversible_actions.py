"""Adversarial tests for irreversible actions.

Every case is written as "the agent tries X, the shell must not do it", and
each one asserts the observable result rather than an internal flag: no copy
under results/, no child process, an error naming the reason.

The approval layer is a policy boundary, not an OS sandbox (see
core/approval.py); these tests pin the policy, not containment.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import REPO_ROOT
from core import approval, router
from lib.chelate_core import paths

# The real channel probe prompts for input, which pytest cannot supply; keep a
# handle on it so the probe itself can still be tested below.
_REAL_HUMAN_CHANNEL = approval._human_channel


# ----------------------------------------------------------------- stubs

class _Rec:
    def __init__(self, name, stage="gates"):
        self.name = name
        self.stage = stage
        self.entrypoint = "run.py"
        self.run_path = f"skills/{name}/run.py"
        self.dependencies = []
        self.sandbox_required = False
        self.input_types = []


class _Reg:
    def __init__(self):
        self.errors = []
        self._all = [_Rec("fulltext-extractor", "ingest"),
                     _Rec("reference-auditor", "gates")]

    def all(self):
        return list(self._all)

    def by_stage(self, stage):
        return [r for r in self._all if r.stage == stage]

    def by_input(self, kind, stage=None):
        return [r for r in self._all if r.name == "fulltext-extractor"]

    def get(self, name):
        return next((r for r in self._all if r.name == name), None)

    def names(self):
        return [r.name for r in self._all]

    def __len__(self):
        return len(self._all)


def _pass(rec, root, action, extra, timeout=600, debug=False):
    return {"skill": rec.name, "stage": rec.stage, "action": action,
            "status": "PASS", "evidence_level": "UNVERIFIED",
            "reason": "stub", "artifacts": [], "seconds": 0.0}


@pytest.fixture
def stub_pipeline(monkeypatch):
    monkeypatch.setattr(router, "load_default_registry", lambda: _Reg())
    monkeypatch.setattr(router, "run_skill", _pass)


@pytest.fixture(autouse=True)
def human_at_the_keyboard(monkeypatch):
    """Stand in for a person at the terminal.

    Tests that assert the *absence* of a human re-patch this to False;
    monkeypatch applies later patches last.  ``_REAL_HUMAN_CHANNEL`` above is
    what the probe itself is exercised through.
    """
    monkeypatch.setattr(approval, "_human_channel", lambda action="promote": True)
    monkeypatch.delenv(approval._HUMAN_ENV, raising=False)


def _params(**over):
    base = {"mode": "c", "input_kind": "", "selected": ["reference-auditor"],
            "inputs": []}
    base.update(over)
    return approval.pipeline_params(base["mode"], base["input_kind"],
                                    base["inputs"], base["selected"])


# --------------------------------------------------- 1. the pipeline gate

def test_promotion_is_withheld_without_an_approval(workspace, stub_pipeline,
                                                   capsys):
    result = router.run(str(workspace), mode="c",
                        selected=["reference-auditor"])
    assert result["promoted"] is False
    assert result["blocked"] == "approval"
    assert not list((workspace / "results").glob("promoted_*"))
    assert "PROMOTION WITHHELD" in capsys.readouterr().err


def test_promotion_runs_with_a_fresh_approval(workspace, stub_pipeline):
    approval.issue(str(workspace), "promote", _params())
    result = router.run(str(workspace), mode="c",
                        selected=["reference-auditor"])
    assert result["promoted"] is True
    assert result["blocked"] is None
    assert len(list((workspace / "results").glob("promoted_*"))) == 1


def test_approval_cannot_be_replayed(workspace, stub_pipeline):
    approval.issue(str(workspace), "promote", _params())
    first = router.run(str(workspace), mode="c", selected=["reference-auditor"])
    second = router.run(str(workspace), mode="c", selected=["reference-auditor"])
    assert first["promoted"] is True
    assert second["promoted"] is False
    assert second["blocked"] == "approval"


def test_no_approval_flag_still_needs_a_human_channel(workspace, stub_pipeline,
                                                      monkeypatch, capsys):
    """`--no-approval` skips the token, not the human.

    An agent subprocess has neither a TTY nor CHELATE_HUMAN=1, so the flag
    must not be a second way past the gate.
    """
    monkeypatch.setattr(approval, "_human_channel", lambda action="promote": False)
    result = router.run(str(workspace), mode="c",
                        selected=["reference-auditor"],
                        require_approval=False)
    assert result["promoted"] is False
    assert result["blocked"] == "approval"
    assert not list((workspace / "results").glob("promoted_*"))
    assert "PROMOTION WITHHELD" in capsys.readouterr().err


def test_issue_refuses_without_a_human_channel(workspace, monkeypatch):
    """Reading the key and calling issue() is the first bypass an agent finds.

    The key is outside the workspace and issue() needs a human, so the
    library call fails exactly where `cli.py approve` would.
    """
    monkeypatch.setattr(approval, "_human_channel", lambda action="promote": False)
    with pytest.raises(approval.HumanRequired, match="human at the keyboard"):
        approval.issue(str(workspace), "promote", _params())
    assert not approval._key_path(str(workspace)).exists()


def test_human_channel_needs_a_typed_answer_not_just_a_terminal(monkeypatch):
    """A TTY an agent inherited is not evidence of a person.

    The probe asks the person to type `approve promote`; EOF or any other
    answer refuses.  CHELATE_HUMAN=1 is the declared scripted hatch.
    """
    monkeypatch.delenv(approval._HUMAN_ENV, raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input",
                        lambda: (_ for _ in ()).throw(EOFError()))
    assert _REAL_HUMAN_CHANNEL("promote") is False
    monkeypatch.setattr("builtins.input", lambda: "yes please")
    assert _REAL_HUMAN_CHANNEL("promote") is False
    monkeypatch.setattr("builtins.input", lambda: "approve promote")
    assert _REAL_HUMAN_CHANNEL("promote") is True
    monkeypatch.setenv(approval._HUMAN_ENV, "1")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    assert _REAL_HUMAN_CHANNEL("promote") is True


def test_the_signing_key_never_lands_in_the_workspace(workspace):
    """The workspace is what the agent may write; the key must not be in it."""
    approval.issue(str(workspace), "promote", _params())
    key = approval._key_path(str(workspace))
    assert key.is_file()
    assert os.path.commonpath([str(key.resolve()),
                               str(workspace.resolve())]) != \
        str(workspace.resolve())
    assert not (workspace / ".chelate" / "approval.key").exists()


def test_a_different_plan_cannot_spend_the_token(workspace, stub_pipeline):
    approval.issue(str(workspace), "promote", _params(selected=["reference-auditor"]))
    result = router.run(str(workspace), mode="a", input_kind="pdf")
    assert result["promoted"] is False
    assert result["blocked"] == "approval"


# ------------------------------------------------ 2. token format attacks

def test_token_is_spent_exactly_once(workspace):
    approval.issue(str(workspace), "promote", _params())
    approval.consume(str(workspace), "promote", _params())
    with pytest.raises(approval.ApprovalRequired):
        approval.consume(str(workspace), "promote", _params())


def test_expired_token_is_refused(workspace, monkeypatch):
    approval.issue(str(workspace), "promote", _params(), ttl=60)
    later = time.time() + 3600
    monkeypatch.setattr(approval.time, "time", lambda: later)
    with pytest.raises(approval.ApprovalRequired, match="expired"):
        approval.consume(str(workspace), "promote", _params())


def test_tampered_mac_is_refused(workspace):
    path = approval.issue(str(workspace), "promote", _params())
    token = json.loads(path.read_text(encoding="utf-8"))
    token["expires"] += 10_000          # keep it alive, break the signature
    path.write_text(json.dumps(token), encoding="utf-8")
    with pytest.raises(approval.ApprovalRequired, match="signature"):
        approval.consume(str(workspace), "promote", _params())


def test_token_for_another_workspace_is_refused(workspace, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    approval.issue(str(workspace), "promote", _params())
    # copy the key to the other workspace's key slot so the signature itself
    # still verifies — the workspace binding in the payload must reject it
    other_key = approval._key_path(str(other))
    other_key.parent.mkdir(parents=True, exist_ok=True)
    other_key.write_bytes(approval._key_path(str(workspace)).read_bytes())
    for token in (workspace / ".chelate" / "approvals").glob("*.json"):
        (other / ".chelate" / "approvals").mkdir(parents=True, exist_ok=True)
        (other / ".chelate" / "approvals" / token.name).write_bytes(
            token.read_bytes())
    with pytest.raises(approval.ApprovalRequired, match="different workspace"):
        approval.consume(str(other), "promote", _params())


def test_changed_input_content_invalidates_the_token(workspace):
    csv = workspace / "data.csv"
    csv.write_text("x,y\n1,2\n", encoding="utf-8")
    approval.issue(str(workspace), "promote",
                   _params(inputs=[str(csv)]))
    csv.write_text("x,y\n9,9\n", encoding="utf-8")   # agent swaps the data
    with pytest.raises(approval.ApprovalRequired):
        approval.consume(str(workspace), "promote",
                         _params(inputs=[str(csv)]))


def test_corrupt_token_is_ignored_not_crashed(workspace):
    folder = approval._approvals_dir(str(workspace))
    (folder / "promote-deadbeef.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(approval.ApprovalRequired):
        approval.consume(str(workspace), "promote", _params())


def test_consumed_token_file_is_removed(workspace):
    path = approval.issue(str(workspace), "promote", _params())
    approval.consume(str(workspace), "promote", _params())
    assert not path.exists()


def test_unknown_action_and_bad_ttl_are_rejected(workspace):
    with pytest.raises(ValueError):
        approval.issue(str(workspace), "delete", {})
    with pytest.raises(ValueError):
        approval.issue(str(workspace), "promote", {}, ttl=0)


@pytest.mark.skipif(os.name == "nt",
                    reason="Windows ignores POSIX mode bits")
def test_token_and_key_are_owner_only(workspace):
    path = approval.issue(str(workspace), "promote", _params())
    for p in (path, approval._key_path(str(workspace))):
        assert p.stat().st_mode & 0o077 == 0


# ------------------------------------------------- 3. path containment

def test_ensure_within_accepts_a_child(workspace):
    child = workspace / "process" / "gates" / "x.json"
    assert paths.ensure_within(str(workspace), str(child))


def test_ensure_within_rejects_parent_traversal(workspace):
    with pytest.raises(paths.WorkspaceEscape):
        paths.ensure_within(str(workspace), str(workspace / ".." / "outside"))


def test_workspace_helper_refuses_to_create_outside(workspace):
    with pytest.raises(paths.WorkspaceEscape):
        paths.workspace(str(workspace), "..", "escaped")


def test_promote_target_cannot_escape(workspace):
    (workspace / "process").mkdir(exist_ok=True)
    stamp = os.path.join("..", "..", "..", "..", "..", "evil")
    with pytest.raises(paths.WorkspaceEscape):
        router.promote(str(workspace), stamp)


def test_symlink_inside_the_workspace_cannot_redirect_a_write(workspace):
    outside = workspace.parent / "outside-target"
    outside.mkdir(exist_ok=True)
    link = workspace / "link"
    try:
        os.symlink(str(outside), str(link), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not permitted in this environment")
    with pytest.raises(paths.WorkspaceEscape):
        paths.ensure_within(str(workspace), str(link / "x.json"))


# --------------------------------------------- 4. sandbox workspace root

def test_sandboxed_skill_receives_the_workspace_not_the_repo(tmp_path,
                                                             monkeypatch):
    """Regression: run_skill_sandboxed was called with _REPO_ROOT, so a
    sandboxed skill wrote its gates into the repository instead of the
    workspace the user named."""
    seen = {}

    def fake(rec, root, action, extra, timeout=600, debug=False):
        seen["root"] = root
        return {"status": "PASS", "evidence_level": "UNVERIFIED",
                "reason": "", "artifacts": [], "missing": [], "timeout": False,
                "returncode": 0, "seconds": 0.0}

    import core.sandbox as sandbox_mod
    monkeypatch.setattr(sandbox_mod, "run_skill_sandboxed", fake)
    rec = _Rec("ml-auditor")
    rec.sandbox_required = True
    router.run_skill(rec, str(tmp_path), "gate", [], timeout=5)
    assert seen["root"] == str(tmp_path)
    assert seen["root"] != str(REPO_ROOT)


# -------------------------------------------------------- 5. CLI wiring

def test_cli_approve_issues_a_token_the_pipeline_accepts(workspace):
    # A subprocess has no TTY, so this stands in for the supervised-script
    # path: CHELATE_HUMAN=1 is the declared hatch, and it is what CI uses.
    env = dict(os.environ, **{approval._HUMAN_ENV: "1"})
    proc = subprocess.run(
        [sys.executable, "cli.py", "approve", "--root", str(workspace),
         "--mode", "c", "--selected", "reference-auditor"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
        env=env, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout[proc.stdout.find("{"):])
    assert Path(payload["token"]).is_file()
    approval.consume(str(workspace), "promote",
                     _params(selected=["reference-auditor"]))


def test_cli_approve_refuses_a_subprocess_without_the_hatch(workspace):
    env = {k: v for k, v in os.environ.items()
           if k != approval._HUMAN_ENV}
    proc = subprocess.run(
        [sys.executable, "cli.py", "approve", "--root", str(workspace),
         "--mode", "c", "--selected", "reference-auditor"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
        env=env, stdin=subprocess.DEVNULL)
    assert proc.returncode == 2
    assert "human at the keyboard" in proc.stderr
    assert not approval._key_path(str(workspace)).exists()
