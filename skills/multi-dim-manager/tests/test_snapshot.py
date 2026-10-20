"""Tests for content-addressed snapshot and restore."""

import pytest

from scripts.errors import ManagerError
from scripts.snapshot import Manifest, restore, snapshot


def _seed(workdir):
    (workdir / "data").mkdir(parents=True, exist_ok=True)
    (workdir / "data" / "clean.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (workdir / "results").mkdir(parents=True, exist_ok=True)
    (workdir / "results" / "lmm.json").write_text('{"x":1}', encoding="utf-8")


def test_snapshot_stores_content_addressed(tmp_path):
    work = tmp_path / "work"
    _seed(work)
    store = tmp_path / "store"
    m = snapshot(work, ["data/clean.csv", "results/lmm.json"], store, 1, "post")
    assert set(m.files.keys()) == {"data/clean.csv", "results/lmm.json"}
    # content-addressed: store holds exactly the two distinct contents
    assert len(list(store.iterdir())) == 2


def test_snapshot_skips_missing_paths(tmp_path):
    work = tmp_path / "work"
    (work / "data").mkdir(parents=True)
    (work / "data" / "clean.csv").write_text("x", encoding="utf-8")
    store = tmp_path / "store"
    m = snapshot(work, ["data/clean.csv", "results/missing.json"], store, 1, "post")
    assert m.files == {"data/clean.csv": m.files["data/clean.csv"]}


def test_identical_content_shared_hash(tmp_path):
    work = tmp_path / "work"
    _seed(work)
    store = tmp_path / "store"
    m1 = snapshot(work, ["data/clean.csv"], store, 1, "pre")
    m2 = snapshot(work, ["data/clean.csv"], store, 2, "post")
    assert m1.files["data/clean.csv"] == m2.files["data/clean.csv"]
    # only one stored blob despite two snapshots
    assert len(list(store.iterdir())) == 1


def test_restore_into_new_dir(tmp_path):
    work = tmp_path / "work"
    _seed(work)
    store = tmp_path / "store"
    m = snapshot(work, ["data/clean.csv", "results/lmm.json"], store, 1, "post")
    target = tmp_path / "restored"
    restore(m, target)
    assert (target / "data" / "clean.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert (target / "results" / "lmm.json").read_text(encoding="utf-8") == '{"x":1}'


def test_restore_is_additive(tmp_path):
    work = tmp_path / "work"
    _seed(work)
    store = tmp_path / "store"
    m = snapshot(work, ["data/clean.csv"], store, 1, "post")
    target = tmp_path / "restored"
    target.mkdir()
    (target / "untouched.txt").write_text("keep", encoding="utf-8")
    restore(m, target)
    # restore must not delete unrelated files
    assert (target / "untouched.txt").read_text(encoding="utf-8") == "keep"


def test_manifest_roundtrip(tmp_path):
    work = tmp_path / "work"
    _seed(work)
    store = tmp_path / "store"
    m = snapshot(work, ["data/clean.csv"], store, 3, "post")
    d = m.to_dict()
    m2 = Manifest.from_dict(d, store)
    assert m2.round_no == 3 and m2.phase == "post"
    assert m2.files == m.files


def test_restore_missing_content_raises(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    m = Manifest(round_no=1, phase="post", files={"data/x.json": "deadbeef"}, store_dir=store)
    with pytest.raises(ManagerError):
        restore(m, tmp_path / "restored")
