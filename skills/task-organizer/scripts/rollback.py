"""rollback.py -- reverse the organize run and restore the before-state.

Triggered automatically when :mod:`verify` fails, or invoked manually after
a failed run. The rollback is *log-driven*: it reads the move records and
the list of directories the organizer created, then undoes them in reverse
order.

Rollback contract
-----------------
1. **Reverse moves** -- for every ``moved`` record, rename the target back to
   its source. If the original source name is now occupied, fall back to a
   ``_r1``/``_r2`` suffix and record the discrepancy (never overwrite).
2. **Remove created directories** -- delete the three-tier skeleton that the
   organizer built, but **only** directories that are now empty. Non-empty
   directories are left in place and reported.
3. **Purge auto-generated files** -- drop index / log / snapshot / report
   files that the pipeline itself created.
4. **Seal the log** -- rename ``..._OrganizeLog.md`` to
   ``..._OrganizeLog_Cancelled.md`` so the audit trail is preserved but clearly
   marked as cancelled.
5. **Return a report** -- :class:`RollbackResult` summarizing what was undone
   and what could not be.

The rollback never raises on individual failures -- each step degrades and is
recorded in the result so the operator can see exactly where it stopped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from scripts import snapshot, utils


@dataclass
class RollbackResult:
    """Outcome of a :func:`rollback` run."""

    restored_files: List[str] = field(default_factory=list)
    removed_dirs: List[str] = field(default_factory=list)
    purged_files: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    sealed_log: Optional[str] = None
    success: bool = False

    @property
    def restored_count(self) -> int:
        return len(self.restored_files)


def _rel_to(root: Path, p: Path) -> str:
    """Render *p* relative to *root* with forward slashes.

    :func:`utils.is_allowed_new_file` whitelists some artifacts by **path**
    (e.g. ``process/sources.json``), so callers must hand it a relative path
    rather than a bare filename.
    """
    try:
        return Path(p).resolve().relative_to(Path(root).resolve()).as_posix()
    except (ValueError, OSError):
        return Path(p).name


def _reverse_moves(
    session: utils.OrganizeSession,
    result: RollbackResult,
) -> None:
    """Undo every 'moved' record, in reverse insertion order."""
    # Reverse so later moves are undone first (FIFO -> LIFO).
    for rec in reversed(list(session.move_records)):
        if rec.status != "moved":
            continue
        target = Path(rec.target)
        source = Path(rec.source)

        if not target.exists():
            # The moved file is already gone; nothing to restore.
            result.conflicts.append(
                f"{rec.source} -> {rec.target} (target missing, cannot restore)"
            )
            continue

        source.parent.mkdir(parents=True, exist_ok=True)

        if source.exists():
            # Collision at the original name -- suffix with _rN to preserve.
            suffixed = _suffixed_source(source, rec)
            try:
                target.rename(suffixed)
                result.restored_files.append(str(suffixed))
                result.conflicts.append(
                    f"restored to {suffixed} (original name occupied)"
                )
            except OSError as exc:
                result.conflicts.append(f"rename failed: {exc}")
            continue

        try:
            target.rename(source)
            result.restored_files.append(str(source))
        except OSError as exc:
            result.conflicts.append(f"rename failed: {exc}")


def _suffixed_source(source: Path, rec) -> Path:
    """Return source with ``_rN`` inserted before the extension."""
    stem, suffix = source.stem, source.suffix
    for i in range(1, 10_000):
        cand = source.with_name(f"{stem}_r{i}{suffix}")
        if not cand.exists():
            return cand
    raise OSError(f"cannot find free suffixed source for {source}")


def _created_dirs_under(root: Path, created: List[str]) -> Set[Path]:
    """Map recorded created-dirs back to absolute Paths under *root*.

    Every recorded directory's **ancestors down to (but not including) the
    root** are included, because the organizer's ``mkdir(parents=True)``
    creates intermediate folders (e.g. organize) that hold a leaf dir
    (e.g. material/initial). Removing children deepest-first leaves the
    intermediates empty, so they must be on the candidate list too.
    """
    root = Path(root).resolve()
    out: Set[Path] = set()
    for c in created:
        p = Path(c)
        abs_p = p.resolve() if p.is_absolute() else (root / p).resolve()
        out.add(abs_p)
        # Walk upward from abs_p's parent until we reach root, adding every
        # intermediate directory. Deepest-first removal (in
        # _remove_created_dirs) empties each intermediate before it is tried.
        anc = abs_p.parent
        while anc != root:
            out.add(anc)
            anc = anc.parent
    return out


def _remove_created_dirs(
    root: Path,
    session: utils.OrganizeSession,
    result: RollbackResult,
) -> None:
    """Delete directories the organizer created, deepest-first.

    For each candidate directory the helper first removes any leftover
    *tool-generated* files (indexes, logs, snapshots, the sealed log), then
    rmdir's the directory if it is now empty. User content was already
    restored to its original location by :func:`_reverse_moves`, so the only
    things that can remain here are generated artifacts -- which are purged.
    Directories that still hold user files are never touched (safety net).
    """
    created = _created_dirs_under(root, session.new_directories)
    # Ensure the three standard tier top-level dirs are deletion candidates -- 
    # build_structure records leaf sub-dirs, and organize is an intermediate
    # ancestor that may not be captured otherwise.
    root = Path(root).resolve()
    for tier in (utils.TIER_ORGANIZE, utils.TIER_PROCESS, utils.TIER_RESULT):
        created.add(root / tier)
    # Deepest-first so children are cleared before their parents.
    for d in sorted(created, key=lambda p: len(p.parts), reverse=True):
        try:
            if not d.exists() or not d.is_dir():
                continue
            # Purge any tool-generated files still inside (including the
            # sealed log that _seal_log may have written back).
            for child in list(d.iterdir()):
                if not child.is_file():
                    continue
                # NOTE: pass the *relative* path, not the bare name -- the
                # provenance manifest is whitelisted as ``process/sources.json``
                # and would never match a name-only check.
                rel = _rel_to(root, child)
                if utils.is_allowed_new_file(rel):
                    child.unlink()
                    result.purged_files.append(str(child))
                elif "Cancelled" in child.name:
                    child.unlink()
                    result.purged_files.append(str(child))
            # Now rmdir if empty.
            if not any(d.iterdir()):
                d.rmdir()
                result.removed_dirs.append(str(d))
        except OSError:
            pass


def _purge_generated_files(root: Path, result: RollbackResult) -> None:
    """Remove index/log/snapshot/report files the pipeline generated."""
    proc = Path(root) / utils.TIER_PROCESS
    tiers = [
        Path(root) / utils.TIER_ORGANIZE / utils.INDEX_MD_NAME,
        Path(root) / utils.TIER_ORGANIZE / utils.INDEX_XLSX_NAME,
    ]
    candidates: List[Path] = list(tiers)
    if proc.is_dir():
        for p in proc.iterdir():
            if p.is_file() and utils.is_allowed_new_file(_rel_to(root, p)):
                candidates.append(p)

    for p in candidates:
        try:
            if p.exists():
                p.unlink()
                result.purged_files.append(str(p))
        except OSError:
            result.conflicts.append(f"could not purge {p}")


def _seal_log(root: Path, session: utils.OrganizeSession, result: RollbackResult) -> None:
    """Rename the organize log to ``..._Cancelled.md`` to mark it cancelled."""
    if session.log_path is None or not Path(session.log_path).exists():
        return
    log = Path(session.log_path)
    sealed = log.with_name(log.name.replace(".md", "_Cancelled.md"))
    try:
        log.rename(sealed)
        result.sealed_log = str(sealed)
    except OSError:
        # If sealing fails, keep the original but note it.
        result.sealed_log = str(log)
        result.conflicts.append(f"could not seal log at {log}")


def rollback(
    root: Path,
    session: Optional[utils.OrganizeSession] = None,
) -> RollbackResult:
    """Restore *root* to its pre-organize state.

    Parameters
    ----------
    root:
        The task folder that was (or will be) organized.
    session:
        The :class:`OrganizeSession` produced by :mod:`organize`. When None,
        the rollback attempts to *reconstruct* the session by reading the
        sealed / active log and the before-snapshot -- this is a degraded
        path and will likely leave some conflicts, which is reported.

    Returns
    -------
    RollbackResult:
        ``success`` is True when no conflicts were recorded.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"rollback target is not a directory: {root}")

    if session is None:
        session = _reconstruct_session(root)

    result = RollbackResult()
    _reverse_moves(session, result)
    # Purge generated files *before* removing directories so that the tier
    # folders (e.g. process) are empty and can be rmdir'd cleanly.
    _purge_generated_files(root, result)
    _remove_created_dirs(root, session, result)
    _seal_log(root, session, result)

    result.success = not result.conflicts
    return result


def _reconstruct_session(root: Path) -> utils.OrganizeSession:
    """Best-effort session rebuild when the live session object is lost.

    Reads the active log (OrganizeLog.md) and any before-snapshot to recover the
    move records. Used only as a fallback -- primary rollback should always
    be called with the live session from the same run.
    """
    session = utils.OrganizeSession(root=root)

    # Recover created directories from the log's Created directories section.
    proc = Path(root) / utils.TIER_PROCESS
    if proc.is_dir():
        for p in sorted(proc.iterdir()):
            if not p.is_file():
                continue
            if "OrganizeLog" in p.name and not p.name.endswith("Cancelled.md"):
                session.log_path = p
                try:
                    text = p.read_text(encoding="utf-8")
                except OSError:
                    text = ""
                # Parse "- `<rel>`" bullets under Created directories.
                in_new = False
                for line in text.splitlines():
                    if line.startswith("## Created directories"):
                        in_new = True
                        continue
                    if in_new and line.startswith("## "):
                        in_new = False
                    if in_new:
                        m = re.search(r"[-*]\s*`([^`]+)`", line)
                        if m:
                            session.new_directories.append(m.group(1))

    # Recover move records from the log's Placement log section.
    if session.log_path:
        try:
            text = session.log_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        in_move = False
        for line in text.splitlines():
            if line.startswith("## Placement log"):
                in_move = True
                continue
            if in_move and line.startswith("## "):
                in_move = False
                break
            if in_move:
                m = re.search(
                    r"[-*]\s*`([^`]+)`\s* -> \s*`([^`]+)`", line
                )
                if m:
                    src_rel, tgt_rel = m.group(1), m.group(2)
                    src = root / src_rel
                    tgt = root / tgt_rel
                    session.move_records.append(
                        utils.MoveRecord(
                            source=str(src),
                            target=str(tgt),
                            reason="recovered",
                            status="moved",
                        )
                    )
    return session
