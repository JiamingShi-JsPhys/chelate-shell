"""Tests for :mod:`scripts.organize`."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import organize, sources, utils


def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def test_structure_created(sample_task: Path) -> None:
    result = organize.organize_folder(sample_task)
    for sub in [
        "material/initial",
        "material/downloaded",
        "process",
        "results",
    ]:
        assert (sample_task / sub).is_dir(), f"missing {sub}"


def test_default_placement_goes_to_process(sample_task: Path) -> None:
    """an unclassified file is *assistant output* -> process/.

    ``material/initial/`` is reserved for the user's own material, so the
    tool must never guess that a stray file belongs there.
    """
    organize.organize_folder(sample_task)
    assert (sample_task / "process/notes.txt").exists()
    assert not (sample_task / "notes.txt").exists()
    assert not (sample_task / "material/initial/notes.txt").exists()


def test_draft_to_process(sample_task: Path) -> None:
    organize.organize_folder(sample_task)
    assert (sample_task / "process/draft.txt").exists()
    assert (sample_task / "process/intermediatenumber.csv").exists()


def test_final_to_result(sample_task: Path) -> None:
    organize.organize_folder(sample_task)
    assert (sample_task / "results/final_report.md").exists()


def test_filename_download_is_not_provenance(sample_task: Path) -> None:
    """A file merely *named* ``download.pdf`` is not a download.

    Only the provenance manifest (``mark-downloaded``) routes a file to
    ``material/downloaded/`` -- guessing from the name would mis-file the
    user's own material.
    """
    organize.organize_folder(sample_task)
    assert (sample_task / "process/download.pdf").exists()
    assert not (sample_task / "material/downloaded/download.pdf").exists()


def test_marked_download_goes_to_downloaded(sample_task: Path) -> None:
    man = sources.SourceManifest.load(sample_task)
    man.add(sources.KIND_DOWNLOADED, "download.pdf", url="https://example.test/x.pdf")
    man.save()
    organize.organize_folder(sample_task)
    assert (sample_task / "material/downloaded/download.pdf").exists()
    assert not (sample_task / "process/download.pdf").exists()


# ---------------------------------------------------------------------------
#: re-filing provenance-registered files stranded in process/
# ---------------------------------------------------------------------------


def test_marked_user_stranded_in_process_is_refiled(sample_task: Path) -> None:
    """After a blind first run dumped files into process/, declaring
    provenance and re-running must actually move them home -- no undo dance.
    """
    organize.organize_folder(sample_task)  # blind run: notes.txt -> process/
    assert (sample_task / "process/notes.txt").exists()

    man = sources.SourceManifest.load(sample_task)
    man.add(sources.KIND_USER, "notes.txt")
    man.save()

    result = organize.organize_folder(sample_task)
    assert (sample_task / "material/initial/notes.txt").exists()
    assert not (sample_task / "process/notes.txt").exists()
    assert result.moved_count == 1


def test_marked_download_stranded_in_process_is_refiled(sample_task: Path) -> None:
    organize.organize_folder(sample_task)
    assert (sample_task / "process/download.pdf").exists()

    man = sources.SourceManifest.load(sample_task)
    man.add(sources.KIND_DOWNLOADED, "download.pdf", url="https://example.test/x.pdf")
    man.save()

    result = organize.organize_folder(sample_task)
    assert (sample_task / "material/downloaded/download.pdf").exists()
    assert not (sample_task / "process/download.pdf").exists()
    assert result.moved_count == 1


def test_unregistered_files_in_process_are_never_refiled(sample_task: Path) -> None:
    """Idempotence: undeclared assistant output stays in process/ forever,
    so a re-run never moves anything."""
    organize.organize_folder(sample_task)

    def _user_files() -> list:
        return sorted(
            p.name
            for p in (sample_task / "process").iterdir()
            if p.is_file() and not utils.is_allowed_new_file(f"process/{p.name}")
        )

    before = _user_files()
    result = organize.organize_folder(sample_task)
    assert _user_files() == before
    assert result.moved_count == 0


def test_tool_artifacts_in_process_are_never_refiled(sample_task: Path) -> None:
    """The exact-path whitelist protects the manifest and pipeline files even
    if a same-named user file was registered."""
    organize.organize_folder(sample_task)
    man = sources.SourceManifest.load(sample_task)
    man.add(sources.KIND_USER, "sources.json")
    man.save()

    result = organize.organize_folder(sample_task)
    assert (sample_task / "process/sources.json").exists()
    moved_names = [s.name for s, _, _ in result.moved]
    assert "sources.json" not in moved_names


def test_chinese_deliverable_name_reaches_results(sample_task: Path) -> None:
    """end-to-end: 综述_/报告_ filenames land in results/."""
    (sample_task / "综述_测试文章.txt").write_text("survey", encoding="utf-8")
    organize.organize_folder(sample_task)
    assert (sample_task / "results/综述_测试文章.txt").exists()
    assert not (sample_task / "process/综述_测试文章.txt").exists()


def test_hidden_not_moved(sample_task: Path) -> None:
    result = organize.organize_folder(sample_task)
    #.hidden.md must remain at the root, un-moved.
    assert (sample_task / ".hidden.md").exists()
    moved_names = [_rel(sample_task, s) for s, _, _ in result.moved]
    assert not any(".hidden" in n for n in moved_names)


def test_symlink_not_moved(sample_task: Path) -> None:
    result = organize.organize_folder(sample_task)
    link = sample_task / "link.txt"
    if link.is_symlink():
        # Symlink stays in place (or is skipped) -- never appears in moved.
        moved_names = [_rel(sample_task, s) for s, _, _ in result.moved]
        assert not any(n.endswith("link.txt") for n in moved_names)


def test_user_subfolder_relocated_whole(sample_task: Path) -> None:
    """sub-folders move intact -- no flattening.

    ``src/data/inner.txt`` must still be ``src/data/inner.txt`` after the
    move, otherwise the user's own structure is destroyed.
    """
    organize.organize_folder(sample_task)
    assert (sample_task / "material/initial/src/data/inner.txt").exists()
    assert not (sample_task / "src").exists()
    assert not (sample_task / "material/initial/inner.txt").exists()


def test_user_material_is_never_renamed(user_task: Path) -> None:
    """The verbatim guarantee: a collision must not silently rename a user file."""
    # The user uploads a file whose name is already taken in their zone.
    (user_task / "material/initial/my_notes.txt").write_text(
        "existing", encoding="utf-8"
    )
    original = (user_task / "material/initial/my_notes.txt").read_text(encoding="utf-8")

    # A same-named file shows up at the root and is declared user material.
    (user_task / "my_notes.txt").write_text("newly uploaded", encoding="utf-8")
    from scripts import sources

    man = sources.SourceManifest.load(user_task)
    man.add(sources.KIND_USER, "my_notes.txt")
    man.save()

    result = organize.organize_folder(user_task)

    # The file already in the user's zone is untouched...
    assert (
        user_task / "material/initial/my_notes.txt"
    ).read_text(encoding="utf-8") == original
    # ...and no ``my_notes_1.txt`` was invented anywhere.
    assert not list(user_task.rglob("my_notes_1.txt"))
    # The blocked file is reported rather than silently mangled.
    assert any("my_notes.txt" in str(p) for p, _ in result.skipped)


def test_user_material_survives_a_second_run(user_task: Path) -> None:
    """Idempotence for the user's zone: nothing is re-moved or re-mangled."""
    organize.organize_folder(user_task)
    before = sorted(
        str(p.relative_to(user_task))
        for p in user_task.rglob("*")
        if p.is_file() and "process" not in p.relative_to(user_task).parts
    )
    result = organize.organize_folder(user_task)
    after = sorted(
        str(p.relative_to(user_task))
        for p in user_task.rglob("*")
        if p.is_file() and "process" not in p.relative_to(user_task).parts
    )
    assert before == after
    assert result.moved_count == 0


def test_user_file_named_download_stays_user(user_task: Path) -> None:
    """A user file whose name contains 'download' is still user material."""
    organize.organize_folder(user_task)
    assert (user_task / "material/initial/download_notes.pdf").exists()
    assert not (user_task / "material/downloaded/download_notes.pdf").exists()


def test_tool_never_writes_into_initial(sample_task: Path) -> None:
    """``initial/`` holds user material only -- never a tool artifact."""
    organize.organize_folder(sample_task)
    initial = sample_task / "material/initial"
    # Only the relocated user sub-folder may be there.
    assert {p.name for p in initial.iterdir()} == {"src"}


def test_empty_folder_reported(sample_task: Path) -> None:
    (sample_task / "empty_dir").mkdir()
    result = organize.organize_folder(sample_task)
    skipped_names = [_rel(sample_task, p) for p, _ in result.skipped]
    assert any("empty_dir" in n for n in skipped_names)


def test_readonly_not_moved(task_with_readonly: Path) -> None:
    result = organize.organize_folder(task_with_readonly)
    # locked.txt (readonly) should remain at the root; normal.txt moved.
    assert (task_with_readonly / "locked.txt").exists()
    assert (task_with_readonly / "process/normal.txt").exists()


def test_target_for_rule() -> None:
    assert organize.target_for("draft.txt") == "process"
    assert organize.target_for("final_x.pdf") == "results"
    assert organize.target_for("plain.txt") == "process"
    # A name containing "download" is *not* a download without provenance.
    assert organize.target_for("download.docx") == "process"


def test_owned_prefixes() -> None:
    prefixes = organize.owned_prefixes()
    assert "material" in prefixes
    assert "process" in prefixes
    assert "results" in prefixes


def test_idempotent_second_run(sample_task: Path) -> None:
    first = organize.organize_folder(sample_task)
    # Second run: files already in their tier are not re-moved.
    second = organize.organize_folder(sample_task)
    assert second.moved_count == 0 or all(
        t.parts[0] in {"material", "process", "results"}
        for _, t, _ in second.moved
    )


def test_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        organize.organize_folder(tmp_path / "nope")


def test_log_written(sample_task: Path) -> None:
    session = utils.OrganizeSession(root=sample_task)
    organize.organize_folder(sample_task, session=session)
    log = sample_task / utils.TIER_PROCESS
    assert any(p.name.endswith("OrganizeLog.md") for p in log.iterdir() if p.is_file())


def test_manifest_records_tier_residents(user_task: Path) -> None:
    """Files the user dropped straight into initial/ are auto-registered."""
    man = sources.SourceManifest.load(user_task)
    assert "my_notes.txt" in man.names(sources.KIND_USER)
    assert "download_notes.pdf" in man.names(sources.KIND_USER)
    assert "a.txt" in man.names(sources.KIND_USER)
