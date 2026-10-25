"""run.py -- end-to-end pipeline orchestrator.

This is the single entry point that wires the whole tool together. It is the
function the SKILL's execution steps call; running it reproduces the exact
order documented in SKILL.md:

    scan -> snapshot(before) -> organize -> snapshot(after)
           -> verify (mandatory)
           -> [on fail] rollback, [on pass] index + seal log

Execution tiers
------------------------
``--mode`` selects how much work a run does. **``full`` is the default and
stays the guarantee tier** -- the safety framework is never weakened, the
tiers are an explicit opt-in:

===============  =======  ===========  ==========  ========  =========
Mode             Snapshots SHA-256     C1-C8       Rollback  History
===============  =======  ===========  ==========  ========  =========
``full``         yes      yes          yes         yes       yes
``incremental``  yes      cached*      yes         yes       yes
``quick``        **no**   **no**       **no**      **no**    **no**
===============  =======  ===========  ==========  ========  =========

\\* ``incremental`` reuses a digest for every file whose ``size`` **and**
``mtime`` are unchanged since the last snapshot (see :mod:`hashcache`), so a
weekly cleanup of a large folder costs a handful of stat calls instead of a
full hash sweep. Files that moved are always re-hashed.

``quick`` is for the everyday "tidy my downloads" case: classify and move,
nothing else. It writes the Markdown log (so it stays auditable) but no
snapshots and no verification.

Public API
----------
- ``run`` -- orchestrates everything; returns a :class:`PipelineResult`.
- ``init_folder`` / ``index_only`` / ``snapshot_only`` -- the standalone
  sub-commands.
- ``run_from_cli`` -- thin wrapper used by ``python -m scripts.run``.

The orchestrator is *transactional*: if verification fails, it triggers the
rollback and reports the cancelled state, so a user never ends up in a
half-organized folder that cannot be audited.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from scripts import (
    broadcast as broadcast_mod,
    dedupe,
    history,
    index_md,
    index_xlsx,
    init as init_mod,
    organize,
    rollback,
    rotate,
    rules,
    scan,
    snapshot,
    sources as sources_mod,
    utils,
    verify,
)
from scripts.utils import logger

#: Valid ``--mode`` values.
MODES = ("quick", "incremental", "full")

#: Default execution tier. ``full`` keeps the v1.x guarantee.
DEFAULT_MODE = "full"

#: Default number of runs' artifacts to keep under ``process/``.
DEFAULT_KEEP = rotate.DEFAULT_KEEP


@dataclass
class PipelineResult:
    """Aggregated outcome of a full ``run`` invocation."""

    root: str
    mode: str = DEFAULT_MODE
    organized: bool = False
    verified: bool = False
    rolled_back: bool = False
    errors: List[str] = field(default_factory=list)
    scan_result: Optional[scan.ScanResult] = None
    verify_result: Optional[verify.VerifyResult] = None
    rollback_result: Optional[rollback.RollbackResult] = None
    history_path: Optional[Path] = None
    dedupe_result: Optional[dedupe.DedupeResult] = None
    rotate_result: Optional[rotate.RotateResult] = None

    @property
    def ok(self) -> bool:
        """True when the run finished cleanly.

        ``quick`` mode has no verification stage, so "organized and nothing
        rolled back" is its success condition; every other tier must also
        have passed C1-C8.
        """
        if self.rolled_back:
            return False
        if self.mode == "quick":
            return self.organized
        return self.organized and self.verified

    def summary_lines(self) -> List[str]:
        lines = [f"Root: {self.root}"]
        lines.append(f"mode: {self.mode}")
        lines.append(f"organize: {'done' if self.organized else 'not done'}")
        if self.mode == "quick":
            lines.append("verification: skipped (quick mode)")
        else:
            lines.append(f"verification: {'passed' if self.verified else 'failed'}")
        if self.rolled_back:
            lines.append("rollback: executed (verification failed, before state restored)")
        if self.history_path is not None:
            lines.append(f"history: wrote {self.history_path.name}")
        if self.dedupe_result is not None:
            dr = self.dedupe_result
            lines.append(
                f"dedupe ({dr.action}): {dr.exact_groups} exact group(s), "
                f"{dr.similar_pairs} similar pair(s)"
                + (f", moved {dr.moved_count}" if dr.action == "move" else "")
            )
        if self.rotate_result is not None and self.rotate_result.deleted_count:
            lines.append(
                f"rotate: kept {self.rotate_result.keep} run(s), "
                f"removed {self.rotate_result.deleted_count} expired artifact(s)"
            )
        if self.errors:
            lines.append("errors:")
            lines.extend(f"  - {e}" for e in self.errors)
        return lines


def run(
    root: Path,
    rules_config: Optional[Path] = None,
    dedupe_action: str = "off",
    verbose: bool = False,
    quiet: bool = False,
    mode: str = DEFAULT_MODE,
    keep: int = DEFAULT_KEEP,
    profile: Optional[str] = None,
    generate_index: Optional[bool] = None,
) -> PipelineResult:
    """Run the organize pipeline at the requested tier.

    Parameters
    ----------
    root:
        The task folder (or a parent folder) to organize.
    rules_config:
        Optional path to a ``.task-organizer.yml`` overrides file. When
        omitted, :func:`scripts.rules.load_rules` falls back to the project
        root config, then the home config, then the built-in table.
    dedupe_action:
        ``"off"`` (default), ``"report"`` (scan and write
        ``process/duplicate_report.md``), or ``"move"`` (report plus
        quarantine exact duplicates into ``material/duplicates/``).
        ``move`` runs in the mutate phase so it is covered by the forced
        verification; a failure triggers the same automatic rollback.
        In ``quick`` mode ``move`` is **downgraded to ``report``** -- there
        is no verification layer to protect a destructive move.
    verbose / quiet:
        Console log level switches; key operations are also mirrored into
        ``process/logs/YYYYMMDD.log`` at INFO level (not in quick mode).
    mode:
        ``"full"`` (default), ``"incremental"`` or ``"quick"`` -- see the
        module docstring. ``full`` keeps the mandatory snapshot + C1-C8 +
        rollback guarantee.
    keep:
        How many runs' artifacts to retain under ``process/`` before older
        ones are rotated away (see :mod:`scripts.rotate`).
    profile:
        Name of a ``profiles:`` entry in the config (see
        :func:`scripts.rules.load_rules`).
    generate_index:
        Whether to build ``Index.md`` / ``Index.xlsx``. ``None`` (default)
        means "auto": on for ``full`` / ``incremental``, off for ``quick``.

    Returns
    -------
    PipelineResult:
        Describes every stage; ``ok`` is the top-level success flag.

    Notes
    -----
    - Hidden files, symlinks, readonly files and empty folders are never
      modified (see :mod:`organize` / :mod:`scan`).
    - When verification fails, the rollback is triggered *inside* this call
      so the caller only sees a finished, consistent state.
    - After a successful run, an operation-history JSON is written to
      ``process/history/`` so the user can later ``undo`` / ``redo`` the
      move decisions (skipped in quick mode).
    - Artifact rotation runs last, and always preserves the newest before
      and after snapshot regardless of *keep*.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")

    root = Path(root).resolve()
    result = PipelineResult(root=str(root), mode=mode)

    # quick mode never opens a log file; every other tier does.
    logger.setup_logging(
        root, verbose=verbose, quiet=quiet, file_log=(mode != "quick")
    )

    if generate_index is None:
        generate_index = mode != "quick"

    # ---- 0a. Placement rules (config override, profile, or built-ins). ----
    try:
        ruleset = rules.load_rules(root=root, extra_path=rules_config, profile=profile)
    except Exception as exc:  # noqa: BLE001 - rules must never crash the pipeline
        result.errors.append(f"rules load failed: {exc}")
        ruleset = rules.builtin_rules()

    # ---- 1. Scan (informational baseline). ----
    try:
        result.scan_result = scan.scan(root)
    except FileNotFoundError as exc:
        result.errors.append(f"scan failed: {exc}")
        return result

    # ---- quick tier: classify + move, nothing else. ----
    if mode == "quick":
        session = utils.OrganizeSession(root=root)
        try:
            organize.organize_folder(root, session=session, rules=ruleset)
            result.organized = True
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"organize failed: {exc}")
            return result

        # A destructive move with no verification behind it is not something
        # this tool will do silently -- report only.
        effective_dedupe = "report" if dedupe_action == "move" else dedupe_action
        if effective_dedupe in ("report", "move"):
            try:
                result.dedupe_result = dedupe.run_dedupe(
                    root, action=effective_dedupe, session=session
                )
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"dedupe failed: {exc}")
            if dedupe_action == "move":
                result.errors.append(
                    "quick mode: dedupe 'move' downgraded to 'report' "
                    "(no verification layer to protect a destructive move)"
                )

        _rotate(root, result, keep)
        return result

    # ---- full / incremental tiers: snapshot -> organize -> verify. ----
    use_cache = mode == "incremental"

    # ---- 2. Before snapshot. ----
    try:
        before = snapshot.make_snapshot(root, phase="before", use_cache=use_cache)
    except Exception as exc:  # noqa: BLE001 - pipeline must not crash
        result.errors.append(f"before snapshot failed: {exc}")
        return result

    # ---- 3. Organize (mutates the folder). ----
    session = utils.OrganizeSession(root=root)
    try:
        organize.organize_folder(root, session=session, rules=ruleset)
        result.organized = True
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"organize failed: {exc}")
        # An organize failure is unrecoverable in-place; do not proceed.
        return result

    # ---- 3a. Optional dedupe in the mutate phase (covers the forced verify). ----
    if dedupe_action in ("report", "move"):
        try:
            dr = dedupe.run_dedupe(root, action=dedupe_action, session=session)
            result.dedupe_result = dr
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"dedupe failed: {exc}")
            # Dedupe failure is non-fatal; the rest of the pipeline proceeds.

    # ---- 4. After snapshot. ----
    try:
        after = snapshot.make_snapshot(root, phase="after", use_cache=use_cache)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"after snapshot failed: {exc}")
        return result

    # ---- 5. Mandatory verification. ----
    try:
        vres = verify.verify(root, session=session, before=before, after=after)
        result.verify_result = vres
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"verify failed: {exc}")
        return result

    if not vres.passed:
        # ---- 5a. Verification failed -> rollback to before-state. ----
        result.verified = False
        try:
            rb = rollback.rollback(root, session=session)
            result.rollback_result = rb
            result.rolled_back = True
            result.errors.append(
                f"verification failed; rolled back "
                f"({rb.restored_count} files restored)"
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"rollback failed: {exc}")
        _rotate(root, result, keep)
        return result

    # ---- 5b. Verification passed -> build indexes, seal log, record history. ----
    result.verified = True
    if generate_index:
        try:
            index_md.write_index_md(root)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"markdown index failed: {exc}")

        try:
            xres = index_xlsx.write_index_xlsx(root)
            if not xres.success and "not installed" not in xres.message:
                result.errors.append(f"xlsx index: {xres.message}")
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"xlsx index failed: {exc}")

    # Record the operation history so the user can undo/redo later.
    try:
        result.history_path = history.write_history(root, session, before, after)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"history write failed: {exc}")

    # Append a closing section to the organize log for the audit trail.
    try:
        utils.append_log(
            session,
            "Pipeline finished",
            [
                f"- verification: passed (errors {vres.error_count}, warnings {vres.warning_count})",
                "- indexes: Index.md / Index.xlsx generated"
                if generate_index
                else "- indexes: skipped",
                f"- history: {result.history_path.name}" if result.history_path else "",
                "- this state is the final deliverable.",
            ],
        )
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"final log failed: {exc}")

    _rotate(root, result, keep)
    return result


def _rotate(root: Path, result: PipelineResult, keep: int) -> None:
    """Rotate ``process/`` artifacts, recording the outcome on *result*.

    Rotation is best-effort and never fatal: a failure is reported as an
    error line but must not turn a successful organize into a failed one.
    """
    try:
        result.rotate_result = rotate.rotate_artifacts(root, keep=keep)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"rotate failed: {exc}")


# ---------------------------------------------------------------------------
# Standalone sub-commands
# ---------------------------------------------------------------------------


def init_folder(
    root: Path,
    rules_config: Optional[Path] = None,
    write_config: bool = True,
    classify: bool = False,
    profile: Optional[str] = None,
    verbose: bool = False,
    quiet: bool = False,
) -> init_mod.InitResult:
    """Create the three-tier skeleton and lift existing content into it.

    Cheap by design: no snapshots, no hashing, no C1-C8. See
    :mod:`scripts.init`.
    """
    try:
        ruleset = rules.load_rules(root=root, extra_path=rules_config, profile=profile)
    except Exception:  # noqa: BLE001 - init must never crash on a bad config
        ruleset = rules.builtin_rules()
    return init_mod.init_folder(
        root,
        rules=ruleset,
        write_config=write_config,
        classify=classify,
        verbose=verbose,
        quiet=quiet,
    )


def index_only(root: Path, verbose: bool = False, quiet: bool = False) -> List[str]:
    """Generate ``Index.md`` + ``Index.xlsx`` for an already-tidy folder.

    This is the hand-off / reporting step: it reads the current layout and
    writes the two indexes without moving or verifying anything. Returns the
    list of written paths (empty when both failed).
    """
    root = Path(root).resolve()
    logger.setup_logging(root, verbose=verbose, quiet=quiet)
    written: List[str] = []
    if not root.is_dir():
        # A mistyped path must fail loudly rather than silently materialise a
        # brand-new folder tree somewhere on disk.
        logger.error(f"index: root is not a directory: {root}")
        return written
    try:
        written.append(str(index_md.write_index_md(root)))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"index: markdown failed: {exc}")
    try:
        xres = index_xlsx.write_index_xlsx(root)
        if xres.success:
            written.append(str(xres.path))
        elif "not installed" not in xres.message:
            logger.error(f"index: xlsx failed: {xres.message}")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"index: xlsx failed: {exc}")
    return written


def snapshot_only(
    root: Path,
    phase: str = "before",
    verbose: bool = False,
    quiet: bool = False,
) -> Optional[Path]:
    """Take a standalone snapshot -- the safety airbag.

    Run this **before** a risky batch rename / data-cleaning script so there
    is a known-good state to fall back on. Returns the written path.
    """
    root = Path(root).resolve()
    logger.setup_logging(root, verbose=verbose, quiet=quiet)
    if not root.is_dir():
        # The "safety airbag" is useless -- and dangerous -- if a typo makes
        # it create a fresh empty tree instead of snapshotting the real one.
        logger.error(f"snapshot: root is not a directory: {root}")
        return None
    try:
        snap = snapshot.make_snapshot(root, phase=phase)
        logger.info(
            f"snapshot: wrote {snap.file_count} file(s) -> "
            f"{utils.snapshot_filename(phase)}"
        )
        return root / utils.TIER_PROCESS / utils.snapshot_filename(phase)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"snapshot: failed: {exc}")
        return None


def mark_downloaded(
    root: Path, target: Path, url: str = "", verbose: bool = False, quiet: bool = False
) -> bool:
    """Register *target* as assistant-downloaded so it lands in ``downloaded/``.

    The assistant calls this right after fetching a file into the task
    folder; the next ``organize`` then routes it to
    ``material/downloaded/`` instead of guessing from its name.
    """
    root = Path(root).resolve()
    logger.setup_logging(root, verbose=verbose, quiet=quiet)
    man = sources_mod.SourceManifest.load(root)
    changed = man.add(sources_mod.KIND_DOWNLOADED, Path(target).name, url=url)
    man.save()
    if changed:
        logger.info(f"sources: registered {Path(target).name} as downloaded")
    else:
        logger.info(f"sources: {Path(target).name} was already registered")
    return changed


def mark_user(
    root: Path, target: Path, verbose: bool = False, quiet: bool = False
) -> bool:
    """Register *target* as user material so it lands in ``initial/``.

    The counterpart of :func:`mark_downloaded`, for material the user
    uploaded after the task was created.
    """
    root = Path(root).resolve()
    logger.setup_logging(root, verbose=verbose, quiet=quiet)
    man = sources_mod.SourceManifest.load(root)
    changed = man.add(sources_mod.KIND_USER, Path(target).name)
    man.save()
    if changed:
        logger.info(f"sources: registered {Path(target).name} as user material")
    else:
        logger.info(f"sources: {Path(target).name} was already registered")
    return changed


def undo(
    history_file: Path,
    root: Optional[Path] = None,
) -> history.HistoryResult:
    """Reverse an already-verified organize run (user-initiated undo)."""
    return history.undo(history_file, root=root)


def redo(
    history_file: Path,
    root: Optional[Path] = None,
) -> history.HistoryResult:
    """Re-apply an already-verified organize run (user-initiated redo)."""
    return history.redo(history_file, root=root)


def dedupe_action(
    root: Path,
    action: str = "report",
    verbose: bool = False,
    quiet: bool = False,
) -> dedupe.DedupeResult:
    """Standalone dedupe command (outside the main pipeline)."""
    logger.setup_logging(root, verbose=verbose, quiet=quiet)
    if action == "move":
        return dedupe.run_dedupe_verified(root, action="move")
    return dedupe.run_dedupe(root, action="report")


def broadcast_only(
    root: Path,
    use_ai: bool = False,
    max_files: int = broadcast_mod.DEFAULT_MAX_FILES,
    keywords_per_file: int = broadcast_mod.DEFAULT_KEYWORDS,
    verbose: bool = False,
    quiet: bool = False,
) -> broadcast_mod.BroadcastResult:
    """Build the ``_broadcast/`` context-compression index for *root*.

    Read-only with respect to the original files: the only writes are
    ``_broadcast/INDEX.md`` and ``_broadcast/index.json``. See
    :mod:`scripts.broadcast`.
    """
    return broadcast_mod.broadcast(
        root,
        use_ai=use_ai,
        max_files=max_files,
        keywords_per_file=keywords_per_file,
        verbose=verbose,
        quiet=quiet,
    )


def run_from_cli(argv: Optional[List[str]] = None) -> int:
    """CLI entry point.

    Supported forms::

        # Create the skeleton and lift existing content (cheap, no verify)
        python -m scripts.run init <root> [--config X] [--profile P] [--classify] [--no-config]

        # Main pipeline at a chosen tier
        python -m scripts.run organize <root> [--mode quick|incremental|full]
        python -m scripts.run organize <root> [--keep N] [--config X] [--profile P]
        python -m scripts.run organize <root> [--dedupe-action off|report|move] [--index]
        python -m scripts.run <root>   # legacy positional-only form (full mode)

        # Undo / redo an already-verified run
        python -m scripts.run undo <history_file> [--root <root>]
        python -m scripts.run redo <history_file> [--root <root>]

        # Standalone dedupe outside the main pipeline
        python -m scripts.run dedupe <root> [--action report|move]

        # Broadcast center: context-compression index (read-only digest)
        python -m scripts.run broadcast <root> [--ai] [--max-files N] [--keywords K]

        # Hand-off / reporting: build the indexes only
        python -m scripts.run index <root>

        # Safety airbag: snapshot before a risky batch operation
        python -m scripts.run snapshot <root> [--phase before|after]

        # Provenance: tell the tool where a file came from
        python -m scripts.run mark-downloaded <root> <file> [--url URL]
        python -m scripts.run mark-user <root> <file>
    """
    argv = list(argv) if argv is not None else list(sys.argv[1:])

    # Detect known subcommands first; otherwise the legacy form takes over
    # with a positional root.
    KNOWN = (
        "organize",
        "init",
        "undo",
        "redo",
        "dedupe",
        "broadcast",
        "index",
        "snapshot",
        "mark-downloaded",
        "mark-user",
        "doctor",
    )
    cmd = argv[0] if argv and argv[0] in KNOWN else None
    positional = argv[0] if (cmd is None and argv) else None

    def _add_log_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("-v", "--verbose", action="store_true")
        p.add_argument("-q", "--quiet", action="store_true")

    # ---- subcommand: organize ----
    if cmd == "organize":
        p = argparse.ArgumentParser(prog="task-organizer organize")
        p.add_argument("root", type=Path)
        p.add_argument("--config", type=Path, default=None)
        p.add_argument("--profile", default=None,
                       help="named profile from the config's `profiles:` map")
        p.add_argument("--mode", choices=list(MODES), default=DEFAULT_MODE)
        p.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                       help=f"runs of artifacts to keep under process/ (default {DEFAULT_KEEP})")
        p.add_argument("--dedupe-action", choices=["off", "report", "move"], default="off")
        p.add_argument("--index", action="store_true", default=None,
                       help="force index generation (default: on except in quick mode)")
        p.add_argument("--no-index", dest="index", action="store_false",
                       help="skip Index.md / Index.xlsx generation")
        _add_log_flags(p)
        a = p.parse_args(argv[1:])
        res = run(a.root, rules_config=a.config, dedupe_action=a.dedupe_action,
                  verbose=a.verbose, quiet=a.quiet, mode=a.mode, keep=a.keep,
                  profile=a.profile, generate_index=a.index)
        for line in res.summary_lines():
            print(line)
        return 0 if res.ok else 1

    # ---- subcommand: init ----
    if cmd == "init":
        p = argparse.ArgumentParser(prog="task-organizer init")
        p.add_argument("root", type=Path)
        p.add_argument("--config", type=Path, default=None)
        p.add_argument("--profile", default=None)
        p.add_argument("--classify", action="store_true",
                       help="apply placement rules to legacy files instead of "
                            "moving everything into material/initial/")
        p.add_argument("--no-config", dest="write_config", action="store_false",
                       help="do not write the commented .task-organizer.yml template")
        _add_log_flags(p)
        a = p.parse_args(argv[1:])
        r = init_folder(a.root, rules_config=a.config, classify=a.classify,
                        profile=a.profile, verbose=a.verbose, quiet=a.quiet,
                        write_config=a.write_config)
        for line in r.summary_lines():
            print(line)
        return 0 if r.ok else 1

    # ---- subcommand: undo / redo ----
    if cmd in ("undo", "redo"):
        p = argparse.ArgumentParser(prog=f"task-organizer {cmd}")
        p.add_argument("history_file", type=Path)
        p.add_argument("--root", type=Path, default=None)
        a = p.parse_args(argv[1:])
        r = undo(a.history_file, root=a.root) if cmd == "undo" else redo(a.history_file, root=a.root)
        print(f"{cmd}: {r.message}")
        label = "restored" if cmd == "undo" else "applied"
        for f in r.restored:
            print(f"  {label}: {f}")
        for c in r.conflicts:
            print(f"  conflict: {c}")
        return 0 if r.ok else 1

    # ---- subcommand: dedupe ----
    if cmd == "dedupe":
        p = argparse.ArgumentParser(prog="task-organizer dedupe")
        p.add_argument("root", type=Path)
        p.add_argument("--action", choices=["report", "move"], default="report")
        _add_log_flags(p)
        a = p.parse_args(argv[1:])
        r = dedupe_action(a.root, action=a.action, verbose=a.verbose, quiet=a.quiet)
        print(f"dedupe ({r.action}): {r.exact_groups} exact group(s), {r.similar_pairs} similar pair(s)")
        for f in r.moved:
            print(f"  moved: {f}")
        print(f"report: {r.report_path}")
        return 0 if r.ok else 1

    # ---- subcommand: broadcast ----
    if cmd == "broadcast":
        p = argparse.ArgumentParser(prog="task-organizer broadcast")
        p.add_argument("root", type=Path)
        p.add_argument("--ai", action="store_true",
                       help="force AI summaries without TASK_ORG_AI (an API key is still required)")
        p.add_argument("--max-files", type=int,
                       default=broadcast_mod.DEFAULT_MAX_FILES,
                       help=f"safety cap on indexed files (default {broadcast_mod.DEFAULT_MAX_FILES})")
        p.add_argument("--keywords", type=int,
                       default=broadcast_mod.DEFAULT_KEYWORDS,
                       help=f"keywords per file (default {broadcast_mod.DEFAULT_KEYWORDS})")
        _add_log_flags(p)
        a = p.parse_args(argv[1:])
        r = broadcast_only(a.root, use_ai=a.ai, max_files=a.max_files,
                           keywords_per_file=a.keywords,
                           verbose=a.verbose, quiet=a.quiet)
        for line in r.summary_lines():
            print(line)
        return 0 if r.ok else 1

    # ---- subcommand: index ----
    if cmd == "index":
        p = argparse.ArgumentParser(prog="task-organizer index")
        p.add_argument("root", type=Path)
        _add_log_flags(p)
        a = p.parse_args(argv[1:])
        written = index_only(a.root, verbose=a.verbose, quiet=a.quiet)
        for w in written:
            print(f"index: wrote {w}")
        if not written:
            print("index: nothing written (see errors above)")
            return 1
        return 0

    # ---- subcommand: snapshot ----
    if cmd == "snapshot":
        p = argparse.ArgumentParser(prog="task-organizer snapshot")
        p.add_argument("root", type=Path)
        p.add_argument("--phase", choices=["before", "after"], default="before")
        _add_log_flags(p)
        a = p.parse_args(argv[1:])
        out = snapshot_only(a.root, phase=a.phase, verbose=a.verbose, quiet=a.quiet)
        if out is None:
            print("snapshot: failed (see errors above)")
            return 1
        print(f"snapshot: wrote {out}")
        return 0

    # ---- subcommand: mark-downloaded / mark-user ----
    if cmd in ("mark-downloaded", "mark-user"):
        p = argparse.ArgumentParser(prog=f"task-organizer {cmd}")
        p.add_argument("root", type=Path)
        p.add_argument("target", type=Path)
        if cmd == "mark-downloaded":
            p.add_argument("--url", default="")
        _add_log_flags(p)
        a = p.parse_args(argv[1:])
        if cmd == "mark-downloaded":
            changed = mark_downloaded(a.root, a.target, url=a.url,
                                      verbose=a.verbose, quiet=a.quiet)
        else:
            changed = mark_user(a.root, a.target, verbose=a.verbose, quiet=a.quiet)
        kind = "downloaded" if cmd == "mark-downloaded" else "user material"
        print(f"sources: {a.target.name} -> {kind}" + ("" if changed else " (already registered)"))
        return 0

    # ---- doctor: read-only diagnostics (never mutates the folder) ----
    if cmd == "doctor":
        p = argparse.ArgumentParser(prog=f"task-organizer {cmd}")
        p.add_argument("root", type=Path)
        _add_log_flags(p)
        a = p.parse_args(argv[1:])
        from scripts import doctor as _doctor
        for line in _doctor.doctor_summary_lines(
            a.root, verbose=a.verbose, quiet=a.quiet
        ):
            print(line)
        return 0

    # ---- no args (or explicit --help): show top-level help ----
    if positional is None or "--help" in argv or "-h" in argv:
        print(
            "usage: task-organizer {init,organize,undo,redo,dedupe,broadcast,"
            "index,snapshot,mark-downloaded,mark-user,doctor}\n"
            "\n"
            "subcommands:\n"
            "  init           create the three-tier skeleton and lift existing\n"
            "                 content into material/initial/ (no snapshot, no verify)\n"
            "  organize       run the pipeline (scan -> snapshot -> organize ->\n"
            "                 dedupe -> verify -> index -> history)\n"
            "                 --mode quick|incremental|full, --keep N\n"
            "  undo           reverse an already-verified organize run from a history JSON\n"
            "  redo           re-apply an already-verified organize run from a history JSON\n"
            "  dedupe         scan for / quarantine duplicate files (report or move to material/duplicates/)\n"
            "  broadcast      build _broadcast/ -- a read-only context-compression\n"
            "                 index (one-line summary + keywords per file); later\n"
            "                 sessions read the index first and open only the\n"
            "                 originals they need\n"
            "  index          generate Index.md / Index.xlsx only (hand-off / reporting)\n"
            "  snapshot       take a standalone snapshot (safety airbag before a risky batch)\n"
            "  mark-downloaded register a file the assistant fetched -> material/downloaded/\n"
            "  mark-user      register a file the user uploaded  -> material/initial/\n"
            "  doctor         read-only diagnostics: is the structure complete, which\n"
            "                 files are stranded at the root, is the broadcast index\n"
            "                 fresh -- and tells you the single next step to run\n"
            "\n"
            "execution tiers (organize):\n"
            "  full        snapshots + SHA-256 + C1-C8 + rollback + history  (default)\n"
            "  incremental like full, but skips hashing unchanged files (mtime+size cache)\n"
            "  quick       classify + move only -- no snapshot, no verification\n"
            "\n"
            "legacy form:\n"
            "  task-organizer <root>  # equivalent to 'organize <root>' (full mode)\n"
            "\n"
            "Run 'task-organizer <subcommand> -h' for per-subcommand help."
        )
        # Exit 0 for an explicit help request; 2 for a bare no-arg invocation.
        return 0 if ("--help" in argv or "-h" in argv) else 2

    # ---- legacy positional-only form (root present, no subcommand) ----
    p = argparse.ArgumentParser(prog="task-organizer", add_help=False)
    p.add_argument("root", type=Path)
    p.add_argument("--config", type=Path, default=None, dest="config")
    p.add_argument("--profile", default=None)
    p.add_argument("--mode", choices=list(MODES), default=DEFAULT_MODE)
    p.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    p.add_argument("--dedupe-action", choices=["off", "report", "move"], default="off")
    p.add_argument("--index", action="store_true", default=None)
    p.add_argument("--no-index", dest="index", action="store_false")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    a = p.parse_args(argv)
    res = run(a.root, rules_config=a.config, dedupe_action=a.dedupe_action,
              verbose=a.verbose, quiet=a.quiet, mode=a.mode, keep=a.keep,
              profile=a.profile, generate_index=a.index)
    for line in res.summary_lines():
        print(line)
    return 0 if res.ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI shim
    sys.exit(run_from_cli())
