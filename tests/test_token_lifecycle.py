"""Tokens have a life: issued, spent once, revocable, invalidated by rotation.

Three properties, each written as a command a person would actually run when
something has gone wrong:

* a token that leaked can be deleted before anyone spends it (``revoke``);
* a key that may have been read can be replaced, and the replacement stops
  every token issued under the old one (``rotate-key``);
* a rotation must not retroactively turn the promotion log into "tampered",
  or the audit becomes useless exactly when it matters.

Plus one property nobody should have to think about: two consumers racing for
the same token produce one promotion, not two.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT
from core import approval, router

STAMP = "20260101T000000Z"


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "process" / "gates").mkdir(parents=True)
    (ws / "process" / "profile.json").write_text('{"rows": 3}', encoding="utf-8")
    return ws


def _params(**over) -> dict:
    base = {"mode": "a", "input_kind": "", "selected": [], "inputs": []}
    base.update(over)
    return approval.pipeline_params(base["mode"], base["input_kind"],
                                    base["inputs"], base["selected"])


@pytest.fixture(autouse=True)
def human(monkeypatch):
    monkeypatch.setattr(approval, "_human_channel",
                        lambda action="promote": True)


# ------------------------------------------------------------------ revoke

def test_revoke_deletes_a_token_that_has_not_been_spent(tmp_path):
    ws = _ws(tmp_path)
    token = approval.issue(str(ws), "promote", _params())
    assert token.is_file()

    assert approval.revoke(str(ws)) == 1
    assert not token.exists()
    with pytest.raises(approval.ApprovalRequired):
        approval.consume(str(ws), "promote", _params())


def test_revoke_leaves_consumed_tokens_alone_because_they_are_gone(tmp_path):
    ws = _ws(tmp_path)
    approval.issue(str(ws), "promote", _params())
    approval.consume(str(ws), "promote", _params())
    # Nothing left to revoke, and that is not an error.
    assert approval.revoke(str(ws)) == 0


def test_revoke_can_target_one_action(tmp_path):
    ws = _ws(tmp_path)
    approval.issue(str(ws), "promote", _params())
    assert approval.revoke(str(ws), "something-else") == 0
    assert len(list((ws / ".chelate" / "approvals").glob("promote-*.json"))) == 1


# ------------------------------------------------------------------ rotate

def test_rotation_invalidates_tokens_issued_before_it(tmp_path):
    ws = _ws(tmp_path)
    approval.issue(str(ws), "promote", _params())

    report = approval.rotate(str(ws))
    assert report["rotated"] is True
    assert report["tokens_invalidated"] >= 1

    # The old token is gone; even if it were still on disk its MAC would not
    # verify under the new key.
    with pytest.raises(approval.ApprovalRequired):
        approval.consume(str(ws), "promote", _params())


def test_a_token_issued_after_rotation_works(tmp_path):
    ws = _ws(tmp_path)
    approval.issue(str(ws), "promote", _params())
    approval.rotate(str(ws))
    approval.issue(str(ws), "promote", _params())
    token = approval.consume(str(ws), "promote", _params())
    assert token.get("nonce")


def test_rotation_does_not_retroactively_tamper_the_promotion_log(tmp_path):
    """Audit still believes yesterday's promotion after a key rotation."""
    ws = _ws(tmp_path)
    # A scripted run mints the key, so the record is signed from the start.
    router.promote(str(ws), STAMP, {"source": "scripted-run"})
    assert router.audit_results(str(ws))["ok"] is True

    approval.rotate(str(ws))

    report = router.audit_results(str(ws))
    assert report["tampered"] == []
    assert report["ok"] is True


def test_rotation_needs_a_human_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(approval, "_human_channel",
                        lambda action="promote": False)
    monkeypatch.delenv(approval.UNSAFE_AUTO_ENV, raising=False)
    monkeypatch.delenv("CHELATE_HUMAN", raising=False)
    with pytest.raises(approval.HumanRequired):
        approval.rotate(str(_ws(tmp_path)))


# ------------------------------------------------------------- concurrency

_CONSUMER = """
import sys
sys.path.insert(0, r"{repo}")
from core import approval
params = {params!r}
try:
    approval.consume(r"{ws}", "promote", params)
except Exception:
    raise SystemExit(1)
raise SystemExit(0)
"""


def test_twenty_consumers_race_one_token_and_exactly_one_wins(tmp_path):
    """The O_CREAT|O_EXCL claim is what makes a token single-use under load."""
    ws = _ws(tmp_path)
    approval.issue(str(ws), "promote", _params())
    script = _CONSUMER.format(repo=str(REPO_ROOT), ws=str(ws),
                              params=_params())
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    procs = [subprocess.Popen([sys.executable, "-c", script], env=env,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
             for _ in range(20)]
    codes = [p.wait(timeout=120) for p in procs]

    assert codes.count(0) == 1, f"winners: {codes.count(0)}"
    assert codes.count(1) == 19
    assert not list((ws / ".chelate" / "approvals").glob("promote-*.json"))
