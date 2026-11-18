"""The 1.4.0 runtime contract: five calls, two backends, no silent fallback."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from contracts.action_manifest import ActionManifest
from core import router, runtime


def _manifest(root, **overrides):
    fields = {
        "workspace": str(root),
        "outputs": [{"path": "process/report.md", "sha256": "a" * 64}],
        "nonce": "n-1",
    }
    fields.update(overrides)
    return ActionManifest(**fields)


# -- ActionManifest -------------------------------------------------------

def test_manifest_accepts_a_plain_publish(workspace):
    assert _manifest(workspace).problems() == []


def test_manifest_round_trips_through_dict(workspace):
    original = _manifest(workspace, snapshot_id="0123456789abcdef",
                         inputs=[{"path": "inbox/a.csv", "sha256": "b" * 64}])
    again = ActionManifest.from_dict(original.to_dict())
    assert again.to_dict() == original.to_dict()


def test_manifest_refuses_unknown_action(workspace):
    assert any("unknown action" in p
               for p in _manifest(workspace, action="rm -rf").problems())


def test_manifest_refuses_relative_workspace():
    problems = _manifest("relative/ws").problems()
    assert any("absolute" in p for p in problems)


def test_manifest_refuses_absolute_output_path(workspace):
    manifest = _manifest(workspace, outputs=[
        {"path": "/etc/passwd", "sha256": "a" * 64}])
    assert any("absolute" in p for p in manifest.problems())


def test_manifest_refuses_parent_escape(workspace):
    manifest = _manifest(workspace, outputs=[
        {"path": "../outside.txt", "sha256": "a" * 64}])
    assert any("escapes" in p for p in manifest.problems())


def test_manifest_refuses_bad_digest(workspace):
    manifest = _manifest(workspace, outputs=[{"path": "x.md", "sha256": "abc"}])
    assert any("sha256" in p for p in manifest.problems())


def test_manifest_refuses_empty_outputs(workspace):
    assert any("no outputs" in p for p in _manifest(workspace, outputs=[]).problems())


def test_manifest_refuses_expired(workspace):
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert any("expired" in p
               for p in _manifest(workspace, expires_at=past).problems())


def test_manifest_refuses_unparseable_expiry(workspace):
    assert any("ISO-8601" in p
               for p in _manifest(workspace, expires_at="tomorrow").problems())


def test_manifest_refuses_empty_nonce(workspace):
    assert any("nonce" in p for p in _manifest(workspace, nonce="").problems())


def test_manifest_refuses_malformed_snapshot_id(workspace):
    manifest = _manifest(workspace, snapshot_id="not-a-snapshot")
    assert any("snapshot_id" in p for p in manifest.problems())


def test_manifest_refuses_symlinked_workspace(workspace, tmp_path_factory):
    link = tmp_path_factory.mktemp("links") / "ws-link"
    try:
        os.symlink(workspace, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    manifest = _manifest(workspace)
    manifest.workspace = str(link)
    assert any("real path" in p for p in manifest.problems())


def test_manifest_digest_changes_with_content(workspace):
    first = _manifest(workspace, nonce="a").digest()
    second = _manifest(workspace, nonce="b").digest()
    assert first != second


# -- runtime selection ----------------------------------------------------

def test_default_runtime_is_policy(monkeypatch):
    monkeypatch.delenv(runtime.RUNTIME_ENV, raising=False)
    backend = runtime.select()
    assert isinstance(backend, runtime.PolicyRuntime)
    assert backend.containment == "policy-only"


def test_env_selects_broker_and_it_fails_closed(monkeypatch):
    monkeypatch.setenv(runtime.RUNTIME_ENV, "broker")
    backend = runtime.select()
    assert isinstance(backend, runtime.BrokerRuntime)
    with pytest.raises(runtime.RuntimeUnavailable):
        backend.run_skill("C:/ws", "data-profiler")


def test_unknown_runtime_is_refused_not_defaulted(monkeypatch):
    monkeypatch.setenv(runtime.RUNTIME_ENV, "polciy")
    with pytest.raises(runtime.RuntimeConfigError):
        runtime.select()


def test_broker_refuses_all_five_calls():
    backend = runtime.BrokerRuntime()
    calls = [
        lambda: backend.status("C:/ws"),
        lambda: backend.run_skill("C:/ws", "data-profiler"),
        lambda: backend.start_recipe("C:/ws", "review"),
        lambda: backend.submit("C:/ws", {}),
        lambda: backend.audit("C:/ws"),
    ]
    for call in calls:
        with pytest.raises(runtime.RuntimeUnavailable):
            call()


def test_policy_refuses_a_manifest_it_cannot_read():
    backend = runtime.PolicyRuntime()
    with pytest.raises(runtime.RuntimeConfigError):
        backend.submit("C:/ws", None)


def test_policy_refuses_recipe_arguments(workspace):
    with pytest.raises(runtime.RuntimeUnsupported):
        runtime.PolicyRuntime().start_recipe(str(workspace), "review",
                                             args=["--x"])


# -- PolicyRuntime behaviour ---------------------------------------------

def test_run_skill_selects_exactly_that_skill(monkeypatch, workspace):
    seen = {}

    def fake_run(root, **options):
        seen.update(options)
        return {"status": "ok"}

    monkeypatch.setattr(router, "run", fake_run)
    result = runtime.PolicyRuntime().run_skill(
        str(workspace), "data-profiler", args=["--verbose"])
    assert result == {"status": "ok"}
    assert seen["selected"] == ["data-profiler"]
    assert seen["extra_args"] == ["--verbose"]


def test_run_skill_refuses_to_override_the_selection(workspace):
    with pytest.raises(runtime.RuntimeConfigError):
        runtime.PolicyRuntime().run_skill(
            str(workspace), "data-profiler", selected=["other"])


def test_status_reports_containment_and_freshness(workspace):
    report = runtime.PolicyRuntime().status(str(workspace))
    assert report["runtime"] == "policy"
    assert report["containment"] == "policy-only"
    assert "freshness" in report
    assert report["workspace"] == os.path.abspath(str(workspace))


def test_audit_of_an_empty_workspace_is_clean(workspace):
    report = runtime.PolicyRuntime().audit(str(workspace))
    assert report["ok"] is True
    assert report["unapproved"] == []


def test_publish_false_never_reaches_results(workspace, monkeypatch):
    """A recipe step produces into process/; publication stays a separate act."""
    def fake_skill(rec, root, action, args, timeout=600, debug=False):
        return {"skill": rec.name, "stage": rec.stage, "status": "PASS",
                "evidence_level": "EXACT", "reason": "stub",
                "artifacts": [], "gate": None, "seconds": 0.0}

    monkeypatch.setattr(router, "run_skill", fake_skill)
    result = router.run(str(workspace), mode="c", selected=["data-profiler"],
                        publish=False)
    assert result["promotion"] == "skipped"
    assert result["promoted"] is False
    promoted = [name for name in os.listdir(os.path.join(str(workspace), "results"))
                if name.startswith("promoted_")]
    assert promoted == []


def test_egress_is_reported_as_declared_not_controlled(workspace):
    """The status must not turn a manifest boolean into a security claim."""
    report = runtime.PolicyRuntime().status(str(workspace))
    egress = report["egress"]
    assert egress["controlled"] is False
    assert egress["enforced_by"] is None
    assert egress["declaring_network"] == ["literature-retriever",
                                           "reference-auditor"]


# -- PolicyRuntime.submit: the manifest decides what is published ----------

def _ready_workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / "process").mkdir(parents=True)
    (ws / "process" / "keep.md").write_text("keep\n", encoding="utf-8")
    (ws / "process" / "extra.md").write_text("extra\n", encoding="utf-8")
    return ws


def _manifest_for(ws, **overrides):
    return ActionManifest.from_workspace(str(ws), runtime="policy",
                                         ttl_seconds=600, **overrides)


def _bind(ws, manifest, params):
    from core import approval
    return approval.mint(str(ws), "promote", params,
                         manifest_sha256=manifest.digest(),
                         nonce=manifest.nonce)


def test_policy_submit_publishes_only_the_declared_files(tmp_path):
    ws = _ready_workspace(tmp_path)
    manifest = _manifest_for(ws)
    manifest.outputs = [item for item in manifest.outputs
                        if item["path"] == "process/keep.md"]
    _bind(ws, manifest, {})
    result = runtime.PolicyRuntime().submit(str(ws), manifest, params={})
    promoted = result["promoted"]
    assert os.path.isfile(os.path.join(promoted, "keep.md"))
    assert not os.path.exists(os.path.join(promoted, "extra.md"))


def test_policy_submit_refuses_a_token_without_a_manifest_binding(tmp_path):
    ws = _ready_workspace(tmp_path)
    manifest = _manifest_for(ws)
    from core import approval
    approval.mint(str(ws), "promote", {}, nonce=manifest.nonce)
    with pytest.raises(runtime.RuntimeRefused) as exc:
        runtime.PolicyRuntime().submit(str(ws), manifest, params={})
    assert "manifest binding" in str(exc.value)


def test_policy_submit_hashes_the_bytes_it_copies(tmp_path):
    ws = _ready_workspace(tmp_path)
    manifest = _manifest_for(ws)
    _bind(ws, manifest, {})
    (ws / "process" / "keep.md").write_text("edited\n", encoding="utf-8")
    with pytest.raises(runtime.RuntimeRefused) as exc:
        runtime.PolicyRuntime().submit(str(ws), manifest, params={})
    assert "changed between approval and publication" in str(exc.value)


def test_policy_submit_refuses_a_manifest_rebuilt_after_approval(tmp_path):
    ws = _ready_workspace(tmp_path)
    manifest = _manifest_for(ws)
    _bind(ws, manifest, {})
    rebuilt = _manifest_for(ws)  # same files, new nonce, new digest
    with pytest.raises(runtime.RuntimeRefused) as exc:
        runtime.PolicyRuntime().submit(str(ws), rebuilt, params={})
    assert "different manifest" in str(exc.value).lower()


@pytest.mark.parametrize("path", ["process/report.md:evil", "process/NUL",
                                  "process/con.txt"])
def test_manifest_refuses_a_windows_stream_or_device(workspace, path):
    """':' is a stream separator and 'NUL' is a device, not a file."""
    manifest = _manifest(workspace,
                         outputs=[{"path": path, "sha256": "a" * 64}])
    reasons = manifest.problems()
    assert any("Windows" in p or "stream" in p for p in reasons), reasons


def test_promotion_refuses_a_device_name_even_without_validation(tmp_path):
    """promote() checks again: it is the code that opens the file."""
    ws = _ready_workspace(tmp_path)
    with pytest.raises(router.PromotionLocked):
        router.promote(str(ws), "20260101T000000Z", files=[
            {"path": "process/NUL", "sha256": "0" * 64}])
