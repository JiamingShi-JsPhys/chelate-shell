"""repro-bundler: deterministic output, and a hostile-read refusal list."""
from __future__ import annotations

import json
import os
import stat
import zipfile

import pytest

from lib.chelate_core import repro


def _workspace(tmp_path):
    (tmp_path / "process" / "gates").mkdir(parents=True)
    (tmp_path / "process" / "bands.csv").write_text("k,E\n0,1\n", encoding="utf-8")
    (tmp_path / "process" / "figure.txt").write_text("png-ish\n", encoding="utf-8")
    (tmp_path / "process" / "gates" / "data-profiler_1.json").write_text(
        json.dumps({"skill": "data-profiler", "status": "PASS"}), encoding="utf-8")
    return tmp_path


def _names(path):
    with zipfile.ZipFile(path) as archive:
        return sorted(archive.namelist())


def test_build_writes_manifest_and_files(tmp_path):
    root = _workspace(tmp_path)
    result = repro.build(str(root), "paper-x", now="2026-01-01T00:00:00Z")
    names = _names(result["path"])
    assert "manifest.json" in names
    assert "files/process/bands.csv" in names
    assert not any(name.startswith("files/process/gates/") for name in names)
    assert result["files"] == 2
    manifest = json.loads(zipfile.ZipFile(result["path"]).read("manifest.json"))
    assert manifest["bundle"] == "paper-x"
    assert manifest["created"] == "2026-01-01T00:00:00Z"
    assert manifest["gates"][0]["skill"] == "data-profiler"
    assert any(skill["name"] for skill in manifest["skills"])


def test_two_builds_of_unchanged_inputs_are_identical(tmp_path):
    root = _workspace(tmp_path)
    first = repro.build(str(root), "a", now="2026-01-01T00:00:00Z")
    second = repro.build(str(root), "a2", now="2026-01-01T00:00:00Z")
    with zipfile.ZipFile(first["path"]) as fa, \
            zipfile.ZipFile(second["path"]) as fb:
        # The name differs in the manifest, so compare the payload entries.
        payload = [n for n in fa.namelist() if n != "manifest.json"]
        assert payload == [n for n in fb.namelist() if n != "manifest.json"]
        for name in payload:
            assert fa.read(name) == fb.read(name)


def test_include_limits_the_bundle(tmp_path):
    root = _workspace(tmp_path)
    result = repro.build(str(root), "one", include=["process/bands.csv"],
                         now="2026-01-01T00:00:00Z")
    assert result["files"] == 1
    assert "files/process/bands.csv" in _names(result["path"])


def test_a_declared_file_that_is_not_there_is_refused(tmp_path):
    root = _workspace(tmp_path)
    with pytest.raises(repro.BundleError, match="not found"):
        repro.build(str(root), "x", include=["process/ghost.csv"])


def test_an_oversized_bundle_is_refused(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    monkeypatch.setattr(repro, "MAX_BUNDLE_BYTES", 1)
    with pytest.raises(repro.BundleError, match="limit"):
        repro.build(str(root), "big")


def test_verify_accepts_an_untouched_bundle(tmp_path):
    root = _workspace(tmp_path)
    built = repro.build(str(root), "ok", now="2026-01-01T00:00:00Z")
    report = repro.verify(built["path"])
    assert report["ok"] is True
    assert report["files"] == 2


def test_verify_reports_a_tampered_file(tmp_path):
    root = _workspace(tmp_path)
    built = repro.build(str(root), "bad", now="2026-01-01T00:00:00Z")
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(built["path"]) as src, \
            zipfile.ZipFile(tampered, "w") as dst:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename.endswith("bands.csv"):
                body = b"0,999\n"
            dst.writestr(info, body)
    report = repro.verify(str(tampered))
    assert report["ok"] is False
    assert report["mismatched"][0]["path"].endswith("bands.csv")


def test_verify_reports_an_unexpected_entry(tmp_path):
    root = _workspace(tmp_path)
    built = repro.build(str(root), "extra", now="2026-01-01T00:00:00Z")
    patched = tmp_path / "extra.zip"
    with zipfile.ZipFile(built["path"]) as src, \
            zipfile.ZipFile(patched, "w") as dst:
        for info in src.infolist():
            dst.writestr(info, src.read(info.filename))
        dst.writestr("files/process/surprise.txt", b"hi")
    report = repro.verify(str(patched))
    assert report["unexpected"] == ["files/process/surprise.txt"]


@pytest.mark.parametrize("entry", [
    "../escape.txt",
    "/abs/escape.txt",
    "C:/windows/escape.txt",
])
def test_an_escaping_entry_refuses_the_whole_archive(tmp_path, entry):
    path = tmp_path / "evil.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr(entry, "x")
    with pytest.raises(repro.BundleError, match="refusing"):
        repro.inspect(str(path))


def test_a_symlink_entry_is_refused(tmp_path):
    path = tmp_path / "link.zip"
    info = zipfile.ZipInfo("files/process/link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(repro.BundleError, match="symlink"):
        repro.inspect(str(path))


def test_a_file_that_is_not_a_zip_is_not_readable(tmp_path):
    path = tmp_path / "notes.zip"
    path.write_text("not a zip", encoding="utf-8")
    with pytest.raises(repro.BundleError, match="not a zip"):
        repro.inspect(str(path))
