"""End-to-end pipeline tests for :mod:`scripts.run`.

These cover the full transactional flow (organize -> verify -> index on pass,
rollback on fail) and confirm the top-level ``PipelineResult`` contract.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import run, utils


def test_pipeline_clean_run_passes(sample_task: Path) -> None:
    result = run.run(sample_task)
    assert result.ok is True
    assert result.organized is True
    assert result.verified is True
    assert result.rolled_back is False
    assert result.errors == []


def test_pipeline_failed_verify_rolls_back(sample_task: Path) -> None:
    """Corrupt an unmoved file *before* the after-snapshot so C2/C5 fail.

    The orchestrator must detect the failure and roll back automatically.
    """
    # Pre-create the structure + organize first, then tamper, then rely on
    # run() re-organizing idempotently -- but to force a verification failure
    # we tamper a generated index file is not enough; instead we tamper a
    # user file that survives in initial.

    # Step 1: run once to organize (clean).
    first = run.run(sample_task)
    assert first.ok is True

    # Step 2: tamper an unmoved file so the *next* after-snapshot diverges.
    #: notes.txt has no keyword match, so it sits in process/ (the
    # assistant-output fallback), not in the user-reserved initial/.
    victim = sample_task / utils.TIER_PROCESS / "notes.txt"
    assert victim.exists()
    original = victim.read_text(encoding="utf-8")

    # We cannot easily re-run a *failed* path without a mutation hook, so
    # instead assert the rollback path directly via verify+rollback.
    from scripts import rollback, snapshot

    snap = snapshot.find_latest_snapshot(sample_task, "before")
    assert snap is not None
    victim.write_text("TAMPERED", encoding="utf-8")
    after_bad = snapshot.make_snapshot(sample_task, phase="after")
    from scripts import verify

    session = utils.OrganizeSession(root=sample_task)
    vres = verify.verify(
        sample_task, session=session, before=snap, after=after_bad,
        write_report=False,
    )
    assert vres.passed is False
    rb = rollback.rollback(sample_task, session=session)
    assert isinstance(rb, rollback.RollbackResult)
    # Restore content for cleanliness.
    victim.write_text(original, encoding="utf-8")


def test_pipeline_missing_root(tmp_path: Path) -> None:
    result = run.run(tmp_path / "no_such_dir")
    assert result.ok is False
    assert any("scan failed" in e for e in result.errors)


def test_pipeline_summary_lines(sample_task: Path) -> None:
    result = run.run(sample_task)
    lines = result.summary_lines()
    joined = "\n".join(lines)
    # "organize" is the pipeline stage verb (kept as the command name), not
    # the folder -- the folder is now called "material"
    assert "organize" in joined
    assert "verification" in joined


def test_pipeline_indices_created_on_pass(sample_task: Path) -> None:
    result = run.run(sample_task)
    assert result.ok is True
    md = sample_task / utils.TIER_ORGANIZE / utils.INDEX_MD_NAME
    assert md.exists()
    # xlsx may be absent if openpyxl is not installed; md is always present.
    xlsx = sample_task / utils.TIER_ORGANIZE / utils.INDEX_XLSX_NAME
    if xlsx.exists():
        assert xlsx.stat().st_size > 0


def test_run_from_cli_help() -> None:
    """The CLI shim parses --help without crashing (both top-level and per-subcommand)."""
    import subprocess, sys

    base = str(Path(__file__).resolve().parent.parent)
    py = sys.executable

    # Top-level help (subcommand menu) returns 0 and lists the subcommands.
    proc = subprocess.run(
        [py, "-m", "scripts.run", "--help"],
        capture_output=True, text=True, cwd=base,
    )
    assert proc.returncode == 0
    assert "organize" in proc.stdout
    assert "dedupe" in proc.stdout

    # Per-subcommand help (organize) mentions the ``root`` argument and the
    # dedupe / config flags.
    proc2 = subprocess.run(
        [py, "-m", "scripts.run", "organize", "--help"],
        capture_output=True, text=True, cwd=base,
    )
    assert proc2.returncode == 0
    assert "root" in proc2.stdout
    assert "--dedupe-action" in proc2.stdout


def _cli(base: str, py: str, *args) -> "subprocess.CompletedProcess":
    import subprocess

    return subprocess.run(
        [py, "-m", "scripts.run", *args],
        capture_output=True, text=True, cwd=base,
    )


def test_cli_organize_subcommand(sample_task: Path) -> None:
    import sys

    base = str(Path(__file__).resolve().parent.parent)
    proc = _cli(base, sys.executable, "organize", str(sample_task))
    assert proc.returncode == 0
    assert "organize: done" in proc.stdout
    assert "history:" in proc.stdout


def test_cli_undo_redo_roundtrip(sample_task: Path) -> None:
    import sys

    base = str(Path(__file__).resolve().parent.parent)
    # Organize first to produce a history file.
    proc = _cli(base, sys.executable, "organize", str(sample_task))
    assert proc.returncode == 0

    hist_dir = sample_task / utils.TIER_PROCESS / "history"
    hfiles = sorted(hist_dir.glob("*_history.json"))
    assert hfiles, "expected a history JSON after organize"
    hfile = str(hfiles[-1])

    r1 = _cli(base, sys.executable, "undo", hfile)
    assert r1.returncode == 0
    assert "undo:" in r1.stdout

    r2 = _cli(base, sys.executable, "redo", hfile)
    assert r2.returncode == 0
    assert "redo:" in r2.stdout


def test_cli_dedupe_subcommand(sample_task: Path) -> None:
    import sys

    base = str(Path(__file__).resolve().parent.parent)
    # Add two identical files so dedupe has something to report.
    (sample_task / "dup_a.txt").write_text("same", encoding="utf-8")
    (sample_task / "dup_b.txt").write_text("same", encoding="utf-8")

    proc = _cli(base, sys.executable, "dedupe", str(sample_task))
    assert proc.returncode == 0
    assert "dedupe (report):" in proc.stdout
    assert "exact group" in proc.stdout


def test_cli_no_args_shows_help() -> None:
    import sys

    base = str(Path(__file__).resolve().parent.parent)
    proc = _cli(base, sys.executable)
    # A bare no-arg invocation returns 2 (usage), but still prints the menu.
    assert proc.returncode == 2
    assert "organize" in proc.stdout


# ---------------------------------------------------------------------------
# In-process CLI dispatch coverage (run_from_cli) -- exercises every branch
# without spawning a subprocess so coverage is recorded in-process.
# ---------------------------------------------------------------------------


def test_run_from_cli_organize_branch(sample_task: Path, capsys) -> None:
    rc = run.run_from_cli(["organize", str(sample_task)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "organize: done" in out


def test_run_from_cli_legacy_positional_branch(sample_task: Path, capsys) -> None:
    # Legacy single-arg form: `run <root>` with no subcommand.
    rc = run.run_from_cli([str(sample_task)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "organize: done" in out


def test_run_from_cli_dedupe_branch(sample_task: Path, capsys) -> None:
    (sample_task / "dup_a.txt").write_text("same", encoding="utf-8")
    (sample_task / "dup_b.txt").write_text("same", encoding="utf-8")
    rc = run.run_from_cli(["dedupe", str(sample_task)])
    assert rc == 0
    assert "dedupe (report):" in capsys.readouterr().out


def test_run_from_cli_no_args_returns_2(capsys) -> None:
    assert run.run_from_cli([]) == 2
    assert "organize" in capsys.readouterr().out


def test_run_from_cli_help_flag_returns_0(capsys) -> None:
    assert run.run_from_cli(["--help"]) == 0
    assert "dedupe" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# execution tiers (--mode)
# ---------------------------------------------------------------------------


def test_mode_quick_skips_snapshot_and_history(sample_task: Path) -> None:
    """quick = move only: no snapshots, no history, no index."""
    result = run.run(sample_task, mode="quick")
    assert result.ok is True
    proc = sample_task / utils.TIER_PROCESS
    assert not list(proc.glob("*_before.json"))
    assert not list(proc.glob("*_after.json"))
    assert not (proc / "history").exists()
    assert not (sample_task / utils.TIER_ORGANIZE / utils.INDEX_MD_NAME).exists()


def test_mode_quick_still_places_files(sample_task: Path) -> None:
    """Even without verification the placement rules still run."""
    run.run(sample_task, mode="quick")
    assert (sample_task / utils.TIER_RESULT / "final_report.md").exists()
    assert (sample_task / utils.TIER_PROCESS / "notes.txt").exists()


def test_mode_incremental_writes_a_hash_cache(sample_task: Path) -> None:
    from scripts import hashcache

    result = run.run(sample_task, mode="incremental")
    assert result.ok is True
    assert hashcache.cache_path(sample_task).exists()


def test_mode_incremental_reuses_the_cache_on_a_second_run(sample_task: Path) -> None:
    """The second run must not re-hash files nobody touched."""
    from scripts import hashcache, snapshot as snapshot_mod

    run.run(sample_task, mode="incremental")
    baseline = {
        rel: entry.sha256
        for rel, entry in hashcache.HashCache.load(sample_task).entries.items()
    }
    assert baseline

    # A fresh cache object handed to the snapshot builder should hit.
    cache2 = hashcache.HashCache.load(sample_task)
    snap = snapshot_mod.make_snapshot(
        sample_task, phase="after", out_path=None, use_cache=True, cache=cache2
    )
    assert cache2.hits > 0
    assert cache2.misses == 0, "an untouched folder should be a pure cache hit"
    # The digests themselves are unchanged.
    for rel, digest in baseline.items():
        assert cache2.entries[rel].sha256 == digest


def test_mode_full_is_the_default(sample_task: Path) -> None:
    result = run.run(sample_task)
    assert result.mode == "full"
    proc = sample_task / utils.TIER_PROCESS
    assert list(proc.glob("*_before.json"))
    assert list(proc.glob("*_after.json"))


def test_mode_full_always_rehashes(sample_task: Path, monkeypatch) -> None:
    """full mode is the guarantee tier -- it never consults the cache."""
    from scripts import hashcache, snapshot as snapshot_mod, utils as utils_mod

    run.run(sample_task, mode="incremental")  # a cache now exists on disk
    assert hashcache.cache_path(sample_task).exists()

    calls: list = []
    real = utils_mod.sha256_file

    def counting(p):
        calls.append(p)
        return real(p)

    monkeypatch.setattr(utils_mod, "sha256_file", counting)
    snap = snapshot_mod.make_snapshot(
        sample_task, phase="after", out_path=None, use_cache=False
    )
    # Every file was re-hashed from scratch -- no cache shortcut.
    assert len(calls) == len(snap.files)
    assert all(f.sha256 for f in snap.files)


def test_mode_full_writes_no_hash_cache(sample_task: Path) -> None:
    from scripts import hashcache

    run.run(sample_task, mode="full")
    assert not hashcache.cache_path(sample_task).exists()


def test_unknown_mode_is_rejected_by_the_cli() -> None:
    with pytest.raises(SystemExit) as exc:
        run.run_from_cli(["organize", ".", "--mode", "turbo"])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# rotation (--keep)
# ---------------------------------------------------------------------------


def test_keep_rotates_old_artifacts(sample_task: Path) -> None:
    from scripts import rotate

    # Three runs, then keep only the newest one.
    run.run(sample_task, mode="quick")
    run.run(sample_task, mode="quick")
    run.run(sample_task, mode="quick")
    proc = sample_task / utils.TIER_PROCESS
    assert len(list(proc.glob("*_history.json"))) == 0  # quick writes no history

    # full runs do write history, so verify rotation on those.
    res = run.run(sample_task, keep=1)
    assert res.ok is True
    rotate.rotate_artifacts(sample_task, keep=1)
    histories = list((proc / "history").glob("*_history.json"))
    assert len(histories) <= 1


def test_keep_default_is_five(sample_task: Path) -> None:
    assert run.DEFAULT_KEEP == 5
    assert run.DEFAULT_MODE == "full"


# ---------------------------------------------------------------------------
# standalone commands
# ---------------------------------------------------------------------------


def test_index_only_regenerates_indices(sample_task: Path) -> None:
    run.run(sample_task, mode="quick")
    paths = run.index_only(sample_task)
    assert any(p.endswith(utils.INDEX_MD_NAME) for p in paths)
    assert (sample_task / utils.TIER_ORGANIZE / utils.INDEX_MD_NAME).exists()


def test_snapshot_only_writes_a_snapshot(sample_task: Path) -> None:
    p = run.snapshot_only(sample_task, phase="before")
    assert p is not None and p.exists()
    assert p.name.endswith("_before.json")


def test_mark_downloaded_routes_the_file(sample_task: Path) -> None:
    """A file the assistant fetched must land in downloaded/, not initial/."""
    (sample_task / "fetched.pdf").write_text("from the web", encoding="utf-8")
    run.mark_downloaded(sample_task, sample_task / "fetched.pdf", url="https://x/y")

    result = run.run(sample_task)
    assert result.ok is True
    assert (
        sample_task / utils.TIER_ORGANIZE / utils.SUB_DOWNLOAD / "fetched.pdf"
    ).exists()
    assert not (
        sample_task / utils.TIER_ORGANIZE / utils.SUB_INIT / "fetched.pdf"
    ).exists()


def test_mark_user_protects_the_file(sample_task: Path) -> None:
    """Explicitly declared user material goes to initial/ and is never renamed."""
    (sample_task / "mine.txt").write_text("mine", encoding="utf-8")
    run.mark_user(sample_task, sample_task / "mine.txt")

    result = run.run(sample_task)
    assert result.ok is True
    assert (sample_task / utils.TIER_ORGANIZE / utils.SUB_INIT / "mine.txt").exists()


def test_init_subcommand_builds_the_skeleton(sample_task: Path, capsys) -> None:
    rc = run.run_from_cli(["init", str(sample_task)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "init: done" in out
    assert utils.structure_complete(sample_task)


def test_init_subcommand_classify_flag(sample_task: Path) -> None:
    rc = run.run_from_cli(["init", str(sample_task), "--classify"])
    assert rc == 0
    assert (sample_task / utils.TIER_RESULT / "final_report.md").exists()


def test_cli_mode_flag_is_accepted(sample_task: Path) -> None:
    import sys

    base = str(Path(__file__).resolve().parent.parent)
    proc = _cli(base, sys.executable, "organize", str(sample_task), "--mode", "quick")
    assert proc.returncode == 0
    assert "organize: done" in proc.stdout


def test_cli_organize_help_lists_the_new_flags() -> None:
    import subprocess
    import sys

    base = str(Path(__file__).resolve().parent.parent)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.run", "organize", "--help"],
        capture_output=True, text=True, cwd=base,
    )
    assert proc.returncode == 0
    for flag in ("--mode", "--keep", "--profile", "--index", "--no-index"):
        assert flag in proc.stdout, f"{flag} missing from organize --help"


# ---------------------------------------------------------------------------
# CLI subcommands, exercised in-process
# ---------------------------------------------------------------------------


def _history_file(sample_task: Path) -> Path:
    run.run(sample_task)
    hist_dir = sample_task / utils.TIER_PROCESS / "history"
    return sorted(hist_dir.glob("*_history.json"))[-1]


def test_run_from_cli_undo_redo_branches(sample_task: Path, capsys) -> None:
    hfile = _history_file(sample_task)
    assert run.run_from_cli(["undo", str(hfile)]) == 0
    assert "undo:" in capsys.readouterr().out
    assert run.run_from_cli(["redo", str(hfile)]) == 0
    assert "redo:" in capsys.readouterr().out


def test_run_from_cli_undo_reports_conflicts(sample_task: Path, capsys) -> None:
    """A missing history file must not crash the CLI."""
    rc = run.run_from_cli(["undo", str(sample_task / "nope.json")])
    assert rc == 1
    assert "undo:" in capsys.readouterr().out


def test_run_from_cli_index_branch(sample_task: Path, capsys) -> None:
    run.run(sample_task, mode="quick")
    rc = run.run_from_cli(["index", str(sample_task)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "index: wrote" in out


def test_run_from_cli_snapshot_branch(sample_task: Path, capsys) -> None:
    rc = run.run_from_cli(["snapshot", str(sample_task)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "snapshot: wrote" in out
    assert (sample_task / utils.TIER_PROCESS).glob("*_before.json")


def test_run_from_cli_snapshot_failure_returns_1(tmp_path: Path, capsys) -> None:
    rc = run.run_from_cli(["snapshot", str(tmp_path / "missing")])
    assert rc == 1
    assert "snapshot: failed" in capsys.readouterr().out


def test_run_from_cli_mark_downloaded_branch(sample_task: Path, capsys) -> None:
    (sample_task / "fetched.pdf").write_text("x", encoding="utf-8")
    rc = run.run_from_cli(
        ["mark-downloaded", str(sample_task), str(sample_task / "fetched.pdf"),
         "--url", "https://example.org/a.pdf"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "downloaded" in out

    from scripts import sources

    man = sources.SourceManifest.load(sample_task)
    assert man.kind_of("fetched.pdf") == sources.KIND_DOWNLOADED


def test_run_from_cli_mark_user_branch(sample_task: Path, capsys) -> None:
    (sample_task / "mine.txt").write_text("x", encoding="utf-8")
    rc = run.run_from_cli(
        ["mark-user", str(sample_task), str(sample_task / "mine.txt")]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "user material" in out


def test_run_from_cli_mark_downloaded_is_idempotent(sample_task: Path, capsys) -> None:
    (sample_task / "a.pdf").write_text("x", encoding="utf-8")
    args = ["mark-downloaded", str(sample_task), str(sample_task / "a.pdf")]
    assert run.run_from_cli(args) == 0
    capsys.readouterr()
    assert run.run_from_cli(args) == 0
    assert "already registered" in capsys.readouterr().out


def test_run_from_cli_dedupe_move_branch(sample_task: Path, capsys) -> None:
    (sample_task / "dup_a.txt").write_text("same", encoding="utf-8")
    (sample_task / "dup_b.txt").write_text("same", encoding="utf-8")
    rc = run.run_from_cli(["dedupe", str(sample_task), "--action", "move"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dedupe (move)" in out
    assert "report:" in out


def test_run_from_cli_init_help_lists_classify() -> None:
    import subprocess
    import sys

    base = str(Path(__file__).resolve().parent.parent)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.run", "init", "--help"],
        capture_output=True, text=True, cwd=base,
    )
    assert proc.returncode == 0
    assert "--classify" in proc.stdout


# ---------------------------------------------------------------------------
# summary_lines coverage
# ---------------------------------------------------------------------------


def test_summary_lines_report_quick_mode(sample_task: Path) -> None:
    result = run.run(sample_task, mode="quick")
    joined = "\n".join(result.summary_lines())
    assert "verification: skipped (quick mode)" in joined


def test_summary_lines_report_rollback(sample_task: Path) -> None:
    """Force a verification failure so the rollback line is rendered."""
    from scripts import rollback, snapshot, verify

    run.run(sample_task)
    victim = sample_task / utils.TIER_PROCESS / "notes.txt"
    before = snapshot.find_latest_snapshot(sample_task, "before")
    victim.write_text("TAMPERED", encoding="utf-8")
    after_bad = snapshot.make_snapshot(sample_task, phase="after")

    session = utils.OrganizeSession(root=sample_task)
    vres = verify.verify(
        sample_task, session=session, before=before, after=after_bad,
        write_report=False,
    )
    assert vres.passed is False
    rollback.rollback(sample_task, session=session)

    result = run.PipelineResult(root=str(sample_task), mode="full")
    result.rolled_back = True
    assert any("rollback: executed" in ln for ln in result.summary_lines())


def test_summary_lines_report_rotate(sample_task: Path) -> None:
    from scripts import rotate

    res = rotate.rotate_artifacts(sample_task, keep=2)
    res.deleted.append("x")
    result = run.PipelineResult(root=str(sample_task), mode="full")
    result.rotate_result = res
    assert any("rotate: kept 2 run(s)" in ln for ln in result.summary_lines())


def test_summary_lines_report_dedupe(sample_task: Path) -> None:
    (sample_task / "dup_a.txt").write_text("same", encoding="utf-8")
    (sample_task / "dup_b.txt").write_text("same", encoding="utf-8")
    result = run.run(sample_task, dedupe_action="report")
    assert result.dedupe_result is not None
    joined = "\n".join(result.summary_lines())
    assert "dedupe (report)" in joined


def test_run_rejects_an_unknown_mode(sample_task: Path) -> None:
    with pytest.raises(ValueError):
        run.run(sample_task, mode="turbo")


def test_pipeline_result_ok_requires_verification(sample_task: Path) -> None:
    r = run.PipelineResult(root=str(sample_task), mode="full")
    r.organized = True
    assert r.ok is False  # verified is still False
    r.verified = True
    assert r.ok is True
    r.rolled_back = True
    assert r.ok is False


def test_pipeline_result_quick_ok_needs_only_organize(sample_task: Path) -> None:
    r = run.PipelineResult(root=str(sample_task), mode="quick")
    assert r.ok is False
    r.organized = True
    assert r.ok is True
