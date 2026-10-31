"""Tests for :mod:`scripts.init` -- the cheap skeleton entry point.



``init`` is deliberately the *lightweight* stage: it must build the

structure and lift pre-existing content into ``material/initial/`` without

taking a single snapshot or running verification.

"""

from __future__ import annotations



from pathlib import Path



import pytest



from scripts import init as init_mod, sources, utils





# ---------------------------------------------------------------------------

# skeleton

# ---------------------------------------------------------------------------





def test_init_creates_the_three_tier_skeleton(tmp_path: Path) -> None:

    res = init_mod.init_folder(tmp_path)

    assert res.ok is True

    assert utils.structure_complete(tmp_path)

    assert (tmp_path / utils.TIER_ORGANIZE / utils.SUB_INIT).is_dir()

    assert (tmp_path / utils.TIER_ORGANIZE / utils.SUB_DOWNLOAD).is_dir()

    assert (tmp_path / utils.TIER_PROCESS).is_dir()

    assert (tmp_path / utils.TIER_RESULT).is_dir()

    # E: init now builds an immediate _broadcast/ index so the folder
    # carries a navigable map from the very start of the task; the
    # index files (INDEX.md + index.json) are written even when
    # there is no content to digest yet.
    bdir = tmp_path / utils.BROADCAST_DIRNAME
    assert bdir.is_dir()
    assert (bdir / "INDEX.md").is_file()
    assert (bdir / "index.json").is_file()





def test_init_does_not_report_broadcast_dir_as_empty_skipped(tmp_path: Path) -> None:

    # an empty _broadcast/ must not show up as "empty folder, not organized"

    (tmp_path / "junk.txt").write_text("x", encoding="utf-8")

    res = init_mod.init_folder(tmp_path)

    assert res.ok is True

    assert all("_broadcast" not in reason for _, reason in res.skipped)





def test_init_is_idempotent(tmp_path: Path) -> None:

    init_mod.init_folder(tmp_path)

    res2 = init_mod.init_folder(tmp_path)

    assert res2.ok is True

    assert res2.created_dirs == []  # nothing new to build

    assert utils.structure_complete(tmp_path)





def test_init_creates_a_missing_root(tmp_path: Path) -> None:

    target = tmp_path / "brand" / "new"

    res = init_mod.init_folder(target)

    assert res.ok is True

    assert utils.structure_complete(target)





def test_init_writes_no_snapshot_and_no_verification(tmp_path: Path) -> None:

    """The whole point of init: no SHA-256 pass, no C1-C8, no rollback."""

    (tmp_path / "notes.txt").write_text("hi", encoding="utf-8")

    init_mod.init_folder(tmp_path)

    proc = tmp_path / utils.TIER_PROCESS

    json_files = [p for p in proc.iterdir() if p.suffix == ".json"]

    # Only the (tiny, name-only) provenance manifest is written.

    assert [p.name for p in json_files] == [sources.MANIFEST_NAME]





def test_init_writes_no_per_day_log_file(tmp_path: Path) -> None:

    init_mod.init_folder(tmp_path)

    assert not (tmp_path / utils.TIER_PROCESS / utils.LOG_DIRNAME).exists()





# ---------------------------------------------------------------------------

# lifting pre-existing content

# ---------------------------------------------------------------------------





def test_init_lifts_loose_files_into_initial(tmp_path: Path) -> None:

    (tmp_path / "notes.txt").write_text("a", encoding="utf-8")

    (tmp_path / "paper.pdf").write_text("b", encoding="utf-8")

    res = init_mod.init_folder(tmp_path)

    assert res.ok is True

    initial = tmp_path / utils.TIER_ORGANIZE / utils.SUB_INIT

    assert (initial / "notes.txt").read_text(encoding="utf-8") == "a"

    assert (initial / "paper.pdf").read_text(encoding="utf-8") == "b"

    # Nothing is left scattered at the root.

    assert not (tmp_path / "notes.txt").exists()





def test_init_lifts_subfolders_whole(tmp_path: Path) -> None:

    (tmp_path / "papers" / "a.txt").parent.mkdir(parents=True)

    (tmp_path / "papers" / "a.txt").write_text("a", encoding="utf-8")

    (tmp_path / "papers" / "deep" / "b.txt").parent.mkdir(parents=True)

    (tmp_path / "papers" / "deep" / "b.txt").write_text("b", encoding="utf-8")



    init_mod.init_folder(tmp_path)

    moved = tmp_path / utils.TIER_ORGANIZE / utils.SUB_INIT / "papers"

    # Structure is preserved exactly, never flattened.

    assert (moved / "a.txt").read_text(encoding="utf-8") == "a"

    assert (moved / "deep" / "b.txt").read_text(encoding="utf-8") == "b"

    assert not (tmp_path / "papers").exists()





def test_init_skips_hidden_files_and_symlinks(tmp_path: Path) -> None:

    (tmp_path / ".hidden.md").write_text("secret", encoding="utf-8")

    (tmp_path / "real.txt").write_text("real", encoding="utf-8")

    link = tmp_path / "link.txt"

    try:

        link.symlink_to(tmp_path / "real.txt")

    except (OSError, NotImplementedError):  # pragma: no cover - no symlink perm

        pytest.skip("symlinks unavailable on this platform")

    # On Windows without developer-mode symlinks, symlink_to can
    # "succeed" but produce a plain copy rather than a real link; only a
    # true symlink exercises the "skip symlinks" branch, so bail out
    # otherwise.
    if not link.is_symlink():
        pytest.skip("symlink creation did not produce a real link here")



    init_mod.init_folder(tmp_path)

    assert (tmp_path / ".hidden.md").exists()

    # The symlink itself is never moved nor followed.

    assert link.is_symlink()

    assert not (tmp_path / utils.TIER_ORGANIZE / utils.SUB_INIT / "link.txt").exists()

    # ...but its target is lifted as ordinary user material.

    assert (tmp_path / utils.TIER_ORGANIZE / utils.SUB_INIT / "real.txt").exists()





def test_init_collision_leaves_the_file_in_place(tmp_path: Path) -> None:

    """User material is never renamed, so a clash is reported, not resolved."""

    initial = tmp_path / utils.TIER_ORGANIZE / utils.SUB_INIT

    initial.mkdir(parents=True)

    (initial / "notes.txt").write_text("already here", encoding="utf-8")

    (tmp_path / "notes.txt").write_text("mine", encoding="utf-8")



    res = init_mod.init_folder(tmp_path)

    assert res.ok is True

    # The pre-existing file is untouched and the new one stays put.

    assert (initial / "notes.txt").read_text(encoding="utf-8") == "already here"

    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "mine"

    assert res.skipped_count == 1





def test_init_empty_folder_is_not_moved(tmp_path: Path) -> None:

    (tmp_path / "empty_dir").mkdir()

    init_mod.init_folder(tmp_path)

    # Empty folders are reported as skipped, never relocated.

    assert (tmp_path / "empty_dir").is_dir()





def test_init_classify_applies_keyword_rules(tmp_path: Path) -> None:

    (tmp_path / "final_report.md").write_text("done", encoding="utf-8")

    (tmp_path / "draft.txt").write_text("wip", encoding="utf-8")

    res = init_mod.init_folder(tmp_path, classify=True)

    assert (tmp_path / utils.TIER_RESULT / "final_report.md").exists()

    assert (tmp_path / utils.TIER_PROCESS / "draft.txt").exists()

    assert res.moved_count == 2





def test_init_classify_still_registers_user_material(tmp_path: Path) -> None:

    """Even in --classify mode the files are the user's: never renamed."""

    (tmp_path / "final_report.md").write_text("done", encoding="utf-8")

    init_mod.init_folder(tmp_path, classify=True)

    man = sources.SourceManifest.load(tmp_path)

    assert man.kind_of("final_report.md") == sources.KIND_USER





def test_init_registers_material_in_the_manifest(tmp_path: Path) -> None:

    (tmp_path / "my_notes.txt").write_text("a", encoding="utf-8")

    (tmp_path / "papers").mkdir()

    (tmp_path / "papers" / "a.txt").write_text("a", encoding="utf-8")

    init_mod.init_folder(tmp_path)



    man = sources.SourceManifest.load(tmp_path)

    assert man.is_verbatim("my_notes.txt") is True

    # Nested files inside a relocated folder are covered too.

    assert man.is_verbatim("a.txt") is True





def test_init_manifest_is_path_whitelisted(tmp_path: Path) -> None:

    (tmp_path / "notes.txt").write_text("a", encoding="utf-8")

    init_mod.init_folder(tmp_path)

    assert utils.is_allowed_new_file(

        f"{utils.TIER_PROCESS}/{sources.MANIFEST_NAME}"

    )





# ---------------------------------------------------------------------------

# config template

# ---------------------------------------------------------------------------





def test_init_writes_the_config_template(tmp_path: Path) -> None:

    res = init_mod.init_folder(tmp_path)

    cfg = tmp_path / init_mod.CONFIG_TEMPLATE_NAME

    assert res.config_path == cfg

    assert cfg.exists()

    # Everything is commented out -- the built-ins stay in charge.

    assert all(

        line.startswith("#") or not line.strip()

        for line in cfg.read_text(encoding="utf-8").splitlines()

    )





def test_init_never_overwrites_an_existing_config(tmp_path: Path) -> None:

    cfg = tmp_path / init_mod.CONFIG_TEMPLATE_NAME

    cfg.write_text("# my own rules\n", encoding="utf-8")

    res = init_mod.init_folder(tmp_path)

    assert res.config_path is None

    assert cfg.read_text(encoding="utf-8") == "# my own rules\n"





def test_init_no_config_flag(tmp_path: Path) -> None:

    res = init_mod.init_folder(tmp_path, write_config=False)

    assert res.config_path is None

    assert not (tmp_path / init_mod.CONFIG_TEMPLATE_NAME).exists()





# ---------------------------------------------------------------------------

# result reporting

# ---------------------------------------------------------------------------





def test_summary_lines_describe_the_run(tmp_path: Path) -> None:

    (tmp_path / "notes.txt").write_text("a", encoding="utf-8")

    res = init_mod.init_folder(tmp_path)

    joined = "\n".join(res.summary_lines())

    assert "init: done" in joined

    assert "material/initial/" in joined





def test_moved_count_and_skipped_count(tmp_path: Path) -> None:

    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    (tmp_path / "empty_dir").mkdir()

    res = init_mod.init_folder(tmp_path)

    assert res.moved_count == 2

    assert res.skipped_count == 1  # the empty folder





def test_init_writes_an_audit_log(tmp_path: Path) -> None:

    (tmp_path / "notes.txt").write_text("a", encoding="utf-8")

    res = init_mod.init_folder(tmp_path)

    assert res.log_path is not None

    assert res.log_path.exists()

    assert "init" in res.log_path.read_text(encoding="utf-8")

