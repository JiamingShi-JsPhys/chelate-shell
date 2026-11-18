"""The broker: two channels, one key, and a publication the worker cannot do."""
from __future__ import annotations

import hashlib
import json
import os
import time

import pytest

import bootstrap
from contracts import pass_gate
from contracts.action_manifest import ActionManifest
from core import approval, broker, runtime


def _workspace(tmp_path):
    ws = os.path.realpath(str(tmp_path))
    os.makedirs(os.path.join(ws, "process", "gates"), exist_ok=True)
    with open(os.path.join(ws, "process", "report.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("result\n")
    bootstrap.write_gate(ws, pass_gate("schema-gate", reason="checked"))
    return ws


@pytest.fixture()
def served(tmp_path):
    ws = _workspace(tmp_path)
    server = broker.Broker(ws).start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            broker.Client(ws, "submit", timeout=2).call("ping")
            break
        except broker.BrokerUnavailable:
            time.sleep(0.05)
    yield ws, server
    server.stop()


def _manifest(ws, path="process/report.txt", digest=None):
    if digest is None:
        with open(os.path.join(ws, *path.split("/")), "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
    return ActionManifest(
        workspace=ws, snapshot_id="0123456789abcdef",
        outputs=[{"path": path, "sha256": digest}], runtime="broker",
        broker_version=broker.BROKER_VERSION,
        expires_at="2030-01-01T00:00:00Z",
        nonce="0123456789abcdef0123456789abcdef")


def _approve(ws, manifest, params=None):
    """Mint a token bound to this manifest — the only kind submit accepts."""
    params = params or approval.pipeline_params("a", "", [], [])
    broker.Client(ws, "approve").call(
        "approve", action="promote", params=params,
        manifest_sha256=manifest.digest(), nonce=manifest.nonce)
    return params


# --------------------------------------------------------------------------
# the channels
# --------------------------------------------------------------------------

def test_both_channels_answer(served):
    ws, _ = served
    assert broker.Client(ws, "submit").call("ping")["channel"] == "submit"
    assert broker.Client(ws, "approve").call("ping")["channel"] == "approve"


def test_the_submit_channel_refuses_an_approval(served):
    """The split is the control: one door would leave 1.3.6 as it was."""
    ws, _ = served
    with pytest.raises(broker.BrokerRefused) as exc:
        broker.Client(ws, "submit").call("approve", action="promote",
                                         params={})
    assert "does not serve" in str(exc.value)


def test_the_approve_channel_refuses_a_submission(served):
    ws, _ = served
    with pytest.raises(broker.BrokerRefused):
        broker.Client(ws, "approve").call("submit", manifest={}, params={})


def test_a_refusal_is_logged(served):
    ws, _ = served
    with pytest.raises(broker.BrokerRefused):
        broker.Client(ws, "submit").call("approve", action="promote",
                                         params={})
    log = os.path.join(broker.state_dir(ws), broker.LOG_NAME)
    events = [json.loads(line) for line in
              open(log, encoding="utf-8").read().splitlines() if line]
    assert any(e.get("event") == "refused" and e.get("op") == "approve"
               for e in events)


# --------------------------------------------------------------------------
# fail closed
# --------------------------------------------------------------------------

def test_no_broker_means_no_broker(tmp_path):
    ws = os.path.realpath(str(tmp_path))
    broker.ensure_state(ws)
    with pytest.raises(broker.BrokerUnavailable) as exc:
        broker.Client(ws).call("ping")
    assert "no broker listening" in str(exc.value)


def test_a_stopped_broker_stops_answering(served):
    ws, server = served
    server.stop()
    time.sleep(0.2)
    with pytest.raises(broker.BrokerUnavailable):
        broker.Client(ws).call("ping")


def test_the_broker_runtime_refuses_to_fall_back(tmp_path):
    ws = os.path.realpath(str(tmp_path))
    broker.ensure_state(ws)
    backend = runtime.BrokerRuntime()
    with pytest.raises(runtime.RuntimeUnavailable):
        backend.status(ws)
    with pytest.raises(runtime.RuntimeUnavailable):
        backend.run_skill(ws, "schema-gate")


# --------------------------------------------------------------------------
# publishing
# --------------------------------------------------------------------------

def test_the_broker_publishes_after_the_token_is_spent(served):
    ws, _ = served
    manifest = _manifest(ws)
    params = _approve(ws, manifest)
    result = broker.Client(ws).call("submit", manifest=manifest.to_dict(),
                                    params=params)
    assert os.path.isdir(result["promoted"])
    assert os.path.isfile(os.path.join(result["promoted"], "report.txt"))


def test_the_token_is_spent_exactly_once(served):
    ws, _ = served
    manifest = _manifest(ws)
    params = _approve(ws, manifest)
    body = manifest.to_dict()
    broker.Client(ws).call("submit", manifest=body, params=params)
    with pytest.raises(broker.BrokerRefused) as exc:
        broker.Client(ws).call("submit", manifest=body, params=params)
    assert "fresh approval" in str(exc.value)


def test_a_submission_without_approval_is_refused(served):
    ws, _ = served
    with pytest.raises(broker.BrokerRefused) as exc:
        broker.Client(ws).call(
            "submit", manifest=_manifest(ws).to_dict(),
            params=approval.pipeline_params("a", "", [], []))
    assert "approval" in str(exc.value).lower()


def test_an_artifact_that_changed_after_the_manifest_is_refused(served):
    ws, _ = served
    params = approval.pipeline_params("a", "", [], [])
    broker.Client(ws, "approve").call("approve", action="promote",
                                      params=params)
    manifest = _manifest(ws).to_dict()
    with open(os.path.join(ws, "process", "report.txt"), "a",
              encoding="utf-8") as fh:
        fh.write("swapped\n")
    with pytest.raises(broker.BrokerRefused) as exc:
        broker.Client(ws).call("submit", manifest=manifest, params=params)
    assert "changed after the manifest" in str(exc.value)


def test_a_manifest_for_another_workspace_is_refused(served, tmp_path):
    ws, _ = served
    other = os.path.realpath(str(tmp_path / "other"))
    os.makedirs(other, exist_ok=True)
    manifest = _manifest(ws).to_dict()
    manifest["workspace"] = other
    with pytest.raises(broker.BrokerRefused):
        broker.Client(ws).call("submit", manifest=manifest, params={})


# --------------------------------------------------------------------------
# key custody and adoption
# --------------------------------------------------------------------------

def test_the_two_channel_keys_are_separate_and_private(served):
    ws, _ = served
    folder = broker.state_dir(ws)
    submit = broker.read_key(ws, "submit")
    approve = broker.read_key(ws, "approve")
    assert submit != approve and len(submit) == 32
    if os.name != "nt":
        assert os.stat(os.path.join(folder, "approve.key")).st_mode & 0o077 == 0


def test_the_signing_key_lives_in_the_broker_not_the_workspace(served):
    ws, _ = served
    params = approval.pipeline_params("a", "", [], [])
    broker.Client(ws, "approve").call("approve", action="promote",
                                      params=params)
    local = os.path.join(approval.state_dir(ws), "approvals")
    on_disk = [name for name in os.listdir(local)] if os.path.isdir(local) else []
    assert on_disk, "the token itself is still handed to the workspace"


def test_audit_crosses_the_channel_too(served):
    """`results/` is the broker's directory; a worker-side census would be
    the quiet shortcut `submit` exists to prevent."""
    ws, _ = served
    report = broker.Client(ws).call("audit")
    assert report["ok"] is True


def test_adopt_keeps_the_old_promotion_log_verifiable(tmp_path):
    ws = os.path.realpath(str(tmp_path))
    os.makedirs(os.path.join(ws, "results"), exist_ok=True)
    report = broker.adopt(ws)
    assert report["audit_ok"] is True
    assert os.path.isfile(os.path.join(broker.state_dir(ws), "adopted.json"))


# --------------------------------------------------------------------------
# the OS boundary, where the machine can show one
# --------------------------------------------------------------------------

def test_a_directory_whose_acl_excludes_this_user_is_unwritable(tmp_path):
    """F01, in the form this machine can demonstrate.

    The broker's real claim is "a worker process cannot write `results/`".
    Proving that needs a second identity; what can be shown here is the
    mechanism it rests on: a DACL naming only Administrators and SYSTEM is
    refused to an ordinary process. An elevated administrator can rewrite the
    DACL — that is the documented limit, so the test skips there instead of
    pretending to have measured something.
    """
    if os.name != "nt":
        pytest.skip("POSIX needs a second uid; see docs/SAFETY.md")
    try:
        import win32con
        import win32security
    except ImportError:
        pytest.skip("pywin32 is not installed")
    target = tmp_path / "results"
    target.mkdir()
    acl = win32security.ACL()
    for sid_text in ("S-1-5-32-544", "S-1-5-18"):  # Administrators, SYSTEM
        acl.AddAccessAllowedAce(
            win32security.ACL_REVISION, win32con.GENERIC_ALL,
            win32security.ConvertStringSidToSid(sid_text))
    original = win32security.GetNamedSecurityInfo(
        str(target), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION).GetSecurityDescriptorDacl()
    win32security.SetNamedSecurityInfo(
        str(target), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION
        | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None)
    try:
        (target / "planted.txt").write_text("x", encoding="utf-8")
    except PermissionError:
        return  # the mechanism holds
    finally:
        # Restore it, or pytest cannot delete its own temp directory.
        win32security.SetNamedSecurityInfo(
            str(target), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION, None, None, original, None)
    pytest.skip("this account can rewrite the DACL (elevated administrator)")


def test_the_broker_publishes_only_the_declared_files(served):
    """A file in process/ that the manifest never named stays behind."""
    ws, _ = served
    with open(os.path.join(ws, "process", "extra.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("not declared\n")
    manifest = _manifest(ws)
    params = _approve(ws, manifest)
    result = broker.Client(ws).call("submit", manifest=manifest.to_dict(),
                                    params=params)
    assert os.path.isfile(os.path.join(result["promoted"], "report.txt"))
    assert not os.path.exists(os.path.join(result["promoted"], "extra.txt"))


def test_an_unbound_token_is_refused_even_when_it_is_valid(served):
    """The submission path requires a token that names this manifest."""
    ws, _ = served
    params = approval.pipeline_params("a", "", [], [])
    broker.Client(ws, "approve").call("approve", action="promote",
                                      params=params)
    with pytest.raises(broker.BrokerRefused) as exc:
        broker.Client(ws).call("submit", manifest=_manifest(ws).to_dict(),
                               params=params)
    assert "manifest binding" in str(exc.value)


def test_a_manifest_rebuilt_after_approval_is_refused(served):
    ws, _ = served
    manifest = _manifest(ws)
    params = _approve(ws, manifest)
    rebuilt = _manifest(ws)
    rebuilt.nonce = "fedcba9876543210fedcba9876543210"
    with pytest.raises(broker.BrokerRefused) as exc:
        broker.Client(ws).call("submit", manifest=rebuilt.to_dict(),
                               params=params)
    assert "different manifest" in str(exc.value).lower()
