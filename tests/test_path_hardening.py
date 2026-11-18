"""Links, special files and look-alike names at the promotion boundary.

Promotion copies ``process/`` into ``results/``. Every case here is a way that
copy could move bytes the workspace never held, or turn one deliverable into
another — and what the shell does about it:

* a symlink pointing out of the workspace is followed by ``copytree``, so the
  target's content would land in ``results/``; it is refused instead;
* a hardlink has no target to resolve — the same inode is simply reachable
  under a second, innocent-looking name; also refused;
* a pre-existing ``results/promoted_<stamp>`` that is itself a symlink would
  redirect the atomic rename; ``ensure_within`` catches it first;
* a FIFO is not a file, and a copy of one is meaningless; the copy fails and
  nothing is published.

Symlinks that stay inside the workspace are allowed and preserved.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from core import router

STAMP = "20260101T000000Z"


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "process" / "gates").mkdir(parents=True)
    (ws / "process" / "profile.json").write_text('{"rows": 3}', encoding="utf-8")
    return ws


def test_a_symlink_leaving_the_workspace_is_refused(tmp_path):
    ws = _ws(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("not the agent's to publish", encoding="utf-8")
    link = ws / "process" / "leak.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need a privilege this platform does not grant")

    with pytest.raises(router.PromotionLocked) as exc:
        router.promote(str(ws), STAMP)
    assert "symlink leaves the workspace" in str(exc.value)
    assert not list((ws / "results").glob("promoted_*"))


def test_a_symlink_inside_the_workspace_is_kept(tmp_path):
    ws = _ws(tmp_path)
    target = ws / "process" / "real.json"
    target.write_text('{"ok": true}', encoding="utf-8")
    link = ws / "process" / "alias.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need a privilege this platform does not grant")

    dst = Path(router.promote(str(ws), STAMP))
    assert (dst / "real.json").is_file()


def test_a_hardlinked_file_is_refused(tmp_path):
    """Two names, one inode: the copy would publish bytes from elsewhere."""
    ws = _ws(tmp_path)
    outside = tmp_path / "outside.bin"
    outside.write_text("elsewhere", encoding="utf-8")
    linked = ws / "process" / "inside.bin"
    try:
        os.link(outside, linked)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("hard links are not available here")

    with pytest.raises(router.PromotionLocked) as exc:
        router.promote(str(ws), STAMP)
    assert "hardlinked file" in str(exc.value)
    assert not list((ws / "results").glob("promoted_*"))


def test_a_preexisting_symlink_at_the_target_is_refused(tmp_path):
    """results/promoted_<stamp> already a link to elsewhere: rename must not follow."""
    ws = _ws(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (ws / "results").mkdir()
    target = ws / "results" / f"promoted_{STAMP}"
    try:
        target.symlink_to(elsewhere, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need a privilege this platform does not grant")

    with pytest.raises(Exception):
        router.promote(str(ws), STAMP)
    assert not list(elsewhere.iterdir())


@pytest.mark.skipif(os.name == "nt", reason="mkfifo is POSIX-only")
def test_a_special_file_stops_the_copy_without_publishing(tmp_path):
    ws = _ws(tmp_path)
    os.mkfifo(ws / "process" / "pipe")

    with pytest.raises(Exception):
        router.promote(str(ws), STAMP)
    assert not list((ws / "results").glob("promoted_*"))
    # The next promotion starts from a clean staging tree.
    (ws / "process" / "pipe").unlink()
    assert router.promote(str(ws), STAMP) is not None


def test_two_inputs_with_the_same_basename_do_not_overwrite_each_other(
        tmp_path):
    from core import snapshot

    ws = _ws(tmp_path)
    a = ws / "process" / "a" / "data.csv"
    b = ws / "process" / "b" / "data.csv"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text("x\n1\n", encoding="utf-8")
    b.write_text("y\n2\n", encoding="utf-8")

    frozen = snapshot.materialise(str(ws), [str(a), str(b)])
    names = {Path(p).name for p in frozen["files"].values()}
    assert len(names) == 2, "one snapshot file would have replaced the other"
    assert Path(frozen["files"][str(a.resolve())]).read_text(
        encoding="utf-8").startswith("x")
    assert Path(frozen["files"][str(b.resolve())]).read_text(
        encoding="utf-8").startswith("y")
