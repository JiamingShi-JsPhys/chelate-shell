"""The update check: is the copy that is running the one that was published?

A host installs a plugin into a cache of its own, so a fixed bypass keeps
running until that cache is refreshed. These tests pin the two halves that
make that visible: the comparison itself, and the single line a run prints
when the copy has drifted. Nothing here touches the network.
"""
from __future__ import annotations

import json

from core import update as update_mod


def _serve(monkeypatch, files):
    """Answer ``_fetch`` from *files*; anything else is unreachable."""
    calls = []

    def fake_fetch(path, timeout=0):  # noqa: ARG001
        calls.append(path)
        return files.get(path)

    monkeypatch.setattr(update_mod, "_fetch", fake_fetch)
    return calls


def _local_bytes(rel):
    return (update_mod.local_root() / rel).read_bytes()


def test_an_identical_copy_is_not_a_difference(monkeypatch, tmp_path):
    _serve(monkeypatch, {rel: _local_bytes(rel)
                         for rel in update_mod.TRACKED})
    monkeypatch.setenv("CHELATE_KEY_ROOT", str(tmp_path / "keys"))

    result = update_mod.check(force=True)
    assert result["reachable"] is True
    assert result["different"] is False
    assert result["files"] == []


def test_a_changed_file_is_named(monkeypatch, tmp_path):
    served = {rel: _local_bytes(rel) for rel in update_mod.TRACKED}
    served["core/router.py"] = b"# a different pipeline\n"
    _serve(monkeypatch, served)
    monkeypatch.setenv("CHELATE_KEY_ROOT", str(tmp_path / "keys"))

    result = update_mod.check(force=True)
    assert result["different"] is True
    assert result["files"] == ["core/router.py"]


def test_line_endings_are_not_a_difference(monkeypatch, tmp_path):
    served = {rel: _local_bytes(rel).replace(b"\n", b"\r\n")
              for rel in update_mod.TRACKED}
    _serve(monkeypatch, served)
    monkeypatch.setenv("CHELATE_KEY_ROOT", str(tmp_path / "keys"))

    assert update_mod.check(force=True)["different"] is False


def test_the_answer_is_cached_for_a_day(monkeypatch, tmp_path):
    calls = _serve(monkeypatch, {rel: _local_bytes(rel)
                                 for rel in update_mod.TRACKED})
    monkeypatch.setenv("CHELATE_KEY_ROOT", str(tmp_path / "keys"))

    first = update_mod.check(force=True)
    assert first["cached"] is False
    seen = len(calls)

    second = update_mod.check()
    assert second["cached"] is True
    assert len(calls) == seen, "a cached answer must not refetch"

    assert update_mod.check(force=True)["cached"] is False
    assert len(calls) > seen


def test_an_unreachable_repository_is_unknown_not_an_error(monkeypatch,
                                                           tmp_path):
    _serve(monkeypatch, {})
    monkeypatch.setenv("CHELATE_KEY_ROOT", str(tmp_path / "keys"))

    result = update_mod.check(force=True)
    assert result["reachable"] is False
    assert result["different"] is False

    # The "could not reach it" answer is kept for a short while, so a machine
    # with no route does not pay the timeout on every single run.
    again = update_mod.check()
    assert again["cached"] is True
    assert again["reachable"] is False

    stored = json.loads(update_mod.cache_path().read_text(encoding="utf-8"))
    stored["checked_at"] = 0  # older than the short TTL
    update_mod.cache_path().write_text(json.dumps(stored), encoding="utf-8")
    assert update_mod.check()["cached"] is False


def test_the_notice_is_one_line_and_can_be_switched_off(monkeypatch,
                                                        tmp_path):
    served = {rel: _local_bytes(rel) for rel in update_mod.TRACKED}
    served["core/router.py"] = b"# newer than this copy\n"
    _serve(monkeypatch, served)
    monkeypatch.setenv("CHELATE_KEY_ROOT", str(tmp_path / "keys"))
    monkeypatch.delenv("CHELATE_UPDATE_OFF", raising=False)

    line = update_mod.notice()
    assert line and "update --apply" in line

    monkeypatch.setenv("CHELATE_UPDATE_OFF", "1")
    assert update_mod.notice() is None


def test_each_host_gets_its_own_update_verb():
    zcode = update_mod.update_commands(
        {"host": "zcode", "plugin": "chelate-shell@mp", "marketplace": "mp"})
    assert zcode == [
        ["zcode", "plugins", "marketplace", "update", "mp"],
        ["zcode", "plugins", "update", "chelate-shell@mp"],
    ]
    assert update_mod.update_commands(
        {"host": "claude", "plugin": "chelate-shell", "marketplace": ""}
    ) == [["claude", "plugin", "update", "chelate-shell"]]
    assert update_mod.update_commands({"host": "other", "plugin": "x",
                                       "marketplace": ""}) == []


def test_apply_stops_after_a_failed_step(monkeypatch):
    calls = []

    class _Done:
        def __init__(self, code):
            self.returncode = code
            self.stdout = "ok" if code == 0 else ""
            self.stderr = "" if code == 0 else "boom"

    def fake_run(argv, **kwargs):  # noqa: ARG001
        calls.append(argv)
        return _Done(1)  # the first command fails

    monkeypatch.setattr(update_mod.subprocess, "run", fake_run)
    results = update_mod.apply(hosts=[{"host": "zcode",
                                       "plugin": "chelate-shell@mp",
                                       "marketplace": "mp"}])

    assert len(calls) == 1, "the dependent command must not run"
    assert results[0]["returncode"] == 1
    assert results[0]["error"] == "boom"


def _fake_hosts(monkeypatch, listings):
    """Pretend both CLIs exist and answer from *listings* (argv[0] -> text)."""

    class _Done:
        def __init__(self, out):
            self.stdout = out
            self.stderr = ""
            self.returncode = 0

    monkeypatch.setattr(update_mod.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(update_mod.subprocess, "run",
                        lambda argv, **kw: _Done(
                            listings.get(argv[0].replace("\\", "/").split("/")[-1], "")))


def test_a_host_is_found_only_when_this_plugin_is_installed(monkeypatch):
    _fake_hosts(monkeypatch, {
        "zcode": chr(10).join(["Plugins (2)",
                              "- chelate-shell-canto@mp [disabled]",
                              "- chelate-shell@mp [enabled]", ""]),
        "claude": chr(10).join(["Installed plugins:", "",
                               "  ❯ chelate-shell-canto@mp",
                               "    Status: ✘ disabled", ""]),
    })

    hosts = update_mod.installed_hosts()
    assert hosts == [{"host": "zcode", "plugin": "chelate-shell@mp",
                      "marketplace": "mp"}], hosts


def test_a_disabled_plugin_is_not_updated(monkeypatch):
    _fake_hosts(monkeypatch, {"zcode": "- chelate-shell@mp [disabled]" + chr(10)})
    assert update_mod.installed_hosts() == []
