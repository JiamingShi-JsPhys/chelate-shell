"""organize.py -- three-tier structure creation and file placement.

Pipeline position
-----------------
scan -> snapshot(before) -> **organize** -> snapshot(after) -> verify

``organize`` is the *mutating* stage. It:
1. Builds the standard three-tier structure under *root*.
2. Classifies every non-hidden, non-empty file with the placement rules.
3. Moves files into their tier, auto-suffixing ``_1``/``_2`` on collision.
4. Skips (never moves) hidden files, symlinks, readonly files, and any
   entry whose move would fail.
5. Records every decision into ``OrganizeSession`` so that
   ``verify`` and ``rollback`` can audit and reverse.

Where a file goes (provenance model)
-------------------------------------------
The destination is decided by **who produced the file**, never by guessing
from its name:

===========================================  ===========================
Provenance                                  Target
===========================================  ===========================
registered as user material (``sources``)   ``material/initial/``
registered as AI-downloaded (``sources``)   ``material/downloaded/``
matched by the keyword rules                that rule's target
no keyword match (assistant output)         ``process`` (the fallback)
===========================================  ===========================

``material/initial/`` is reserved for the user's own material: the tool
never writes anything of its own there, so it can never collide with the
user's files.

**Verbatim guarantee.** User material is moved with its name and content
untouched. When a same-named file already sits in the destination the file
is **left where it is and reported as a conflict** instead of being renamed
-- silently renaming a user's ``report.pdf`` to ``report_1.pdf`` would
break the "put my initial material back exactly as it was" promise. Only
files the tool itself owns (drafts, downloads, indexes) may be suffixed.

placement rules (checked in priority order, first match wins)
--------------------------------------------------------------
1. filename contains final / deliverable / 定稿 / 最终版 / 综述 / 报告
   -> results/   (includes the Chinese deliverable words)
2. filename contains draft / intermediate / temp / tmp / raw / 草稿 / 临时
   -> process/
3. anything else -> process/ (see the provenance table above)
4. files already *inside* a standard tier or the process
   folder are left untouched (they are the tool's own output).

The old ``download / reference`` keyword rule was removed:
"downloaded" is a provenance, not a filename pattern.

Re-filing stranded files
---------------------------------
A *blind* first ``organize`` -- one that runs before anything was declared --
dumps unknown files into the ``process/`` fallback. Once the user later
declares their provenance (``mark-user`` / ``mark-downloaded``), the next
``organize`` **moves them home**: registered user material stranded in
``process/`` goes to ``material/initial/``, registered downloads go to
``material/downloaded/``. Files with no declaration stay in ``process/``
(the assistant-output fallback), which is what keeps re-runs idempotent.
Tool artifacts (snapshots, logs, ``sources.json``) are never re-filed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts import rules as rules_mod, scan, sources as sources_mod, utils
from scripts.utils import logger


# ---------------------------------------------------------------------------
# placement rule keywords (case-insensitive substring match on the filename)
# ---------------------------------------------------------------------------

#: Deprecated local copy. Kept only so that ``target_for`` and the public
#: ``organize.target_for`` remain importable; the authoritative table now
#: lives in :mod:`scripts.rules` (``BUILTIN_PLACEMENT``) and can be overridden
#: by a ``.task-organizer.yml`` config file.
_PLACEMENT_RULES: List[Tuple[str, List[str]]] = [
    (target, list(keywords))
    for _priority, keywords, target in rules_mod.BUILTIN_PLACEMENT
]

#: Default target when no keyword matches and provenance is unknown.
#: ``process`` -- the assistant's own output must never land in the
#: user-reserved ``material/initial/``.
_DEFAULT_TARGET = rules_mod.BUILTIN_DEFAULT_TARGET

#: Where the user's own material lives. Reserved: the tool never writes
#: anything of its own here (see the module docstring).
USER_MATERIAL_TARGET = f"{utils.TIER_ORGANIZE}/{utils.SUB_INIT}"

#: Directories the tool owns; files already inside them are never moved.
_OWNED_PREFIXES = (
    "material",
    "process",
    "results",
    utils.BROADCAST_DIRNAME,
)


@dataclass
class OrganizeResult:
    """Outcome of one ``organize_folder`` run.

    - ``moved``: list of ``(source, target, rule)`` that were actually moved.
    - ``skipped``: list of ``(path, reason)`` that were intentionally left.
    - ``session``: the live :class:`OrganizeSession` for downstream use.
    """

    moved: List[Tuple[Path, Path, str]] = field(default_factory=list)
    skipped: List[Tuple[Path, str]] = field(default_factory=list)
    session: utils.OrganizeSession = field(default_factory=utils.OrganizeSession)

    @property
    def moved_count(self) -> int:
        return len(self.moved)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def _match_rule(
    name: str,
    rules: Optional[rules_mod.Rules] = None,
    manifest: Optional[sources_mod.SourceManifest] = None,
) -> str:
    """Return the target sub-dir (relative to root) for a file *name*.

    Resolution order (see the module docstring):

    1. **Provenance** -- files registered in the manifest win outright, so a
       user file named ``download_notes.pdf`` still lands in ``initial/`` and
       an assistant fetch named ``notes.pdf`` lands in ``downloaded/``.
    2. **Keyword rules** -- when *rules* is provided (a
       :class:`scripts.rules.Rules` loaded from a ``.task-organizer.yml``
       config or the built-ins), its keyword table is used; otherwise the
       hard-coded built-in table is used, preserving the default
       behaviour.
    """
    if manifest is not None:
        kind = manifest.kind_of(name)
        if kind == sources_mod.KIND_USER:
            return f"{utils.TIER_ORGANIZE}/{utils.SUB_INIT}"
        if kind == sources_mod.KIND_DOWNLOADED:
            return f"{utils.TIER_ORGANIZE}/{utils.SUB_DOWNLOAD}"
    return rules_mod.target_for(name, rules)


def _is_owned_path(rel: str) -> bool:
    """True if *rel* is already inside a tool-owned standard folder."""
    norm = rel.replace("\\", "/")
    for prefix in _OWNED_PREFIXES:
        if norm.startswith(prefix + "/") or norm == prefix:
            return True
    return False


def _top_level_files(root: Path) -> List[Path]:
    """Yield regular files directly under *root* (not recursing).

    The placement decision is made on top-level files; sub-folders are
    relocated wholesale (see :func:`_user_subfolders`). Recursing into
    arbitrary user sub-folders would be too destructive.
    """
    out: List[Path] = []
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if p.is_dir():
            continue
        if p.is_symlink():
            continue
        if utils.is_hidden(p):
            continue
        out.append(p)
    return out


def _user_subfolders(root: Path) -> List[Path]:
    """Return the **non-empty** top-level folders the user owns.

    A folder is the user's own organisational unit, so it is relocated
    intact rather than flattened: ``src/data/inner.txt`` must still be
    ``src/data/inner.txt`` after the move, otherwise the "put my initial
    material back exactly as it was" promise is broken.

    Excluded: the three standard tiers, hidden folders and symlinks. Empty
    folders are excluded too -- they are reported as "skipped" by the
    caller, not moved.
    """
    out: List[Path] = []
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if not p.is_dir() or p.is_symlink():
            continue
        if utils.is_hidden(p):
            continue
        if p.name in _OWNED_PREFIXES:
            continue
        try:
            if not any(p.iterdir()):
                continue  # empty -> reported as skipped, never moved
        except OSError:
            continue
        out.append(p)
    return out


def _move_file(
    src: Path,
    target: Path,
    session: utils.OrganizeSession,
    preserve_name: bool = False,
) -> Tuple[bool, str]:
    """Attempt a single move. Returns ``(ok, message)``.

    Never raises -- all failures are turned into a skip reason so the batch
    keeps running.

    Parameters
    ----------
    preserve_name:
        When True (used for **user material**), a name collision is *not*
        resolved by appending ``_1``/``_2``. The file is left exactly where
        it is and reported as a conflict, because renaming a user's file
        would break the verbatim guarantee. Only the tool's own output may
        be suffixed.
    """
    if not src.exists():
        logger.warning(f"organize: skip {src.name}: source no longer exists")
        return False, "source no longer exists"
    if utils.is_readonly(src):
        logger.warning(f"organize: skip {src.name}: readonly file")
        return False, "readonly file, not moved"

    # Make sure the target directory exists.
    target.parent.mkdir(parents=True, exist_ok=True)

    # Collision handling.
    if preserve_name and target.exists():
        # Never rename the user's material -- report and leave in place.
        logger.warning(
            f"organize: skip {src.name}: name already taken at "
            f"{target.parent.name}/ (user material is never renamed)"
        )
        return False, f"name already exists in {target.parent.name}/ (left in place)"

    final_target = (
        target if preserve_name else utils.unique_target_dir(target.parent, target.name)
    )

    try:
        src.rename(final_target)
    except OSError:
        try:
            import shutil

            shutil.move(str(src), str(final_target))
        except Exception as exc: # pragma: no cover - last-resort path
            logger.error(f"organize: move failed {src.name}: {exc}")
            return False, f"move failed: {exc}"

    session.add_move(src, final_target, reason=target.parent.name, status="moved")
    logger.info(f"organize: moved {src.name} -> {final_target.name}")
    return True, str(final_target)


def move_directory(
    src: Path,
    target_dir: Path,
    session: utils.OrganizeSession,
    reason: Optional[str] = None,
    preserve_name: bool = True,
) -> Tuple[bool, str]:
    """Move a whole directory into *target_dir*, preserving its name.

    Used by :mod:`init` to lift a legacy sub-folder into
    ``material/initial/<name>`` without recursing into it -- scattering a
    user's sub-tree across the tiers would be far more destructive than
    relocating it intact.

    Returns ``(ok, message)`` and never raises.
    """
    src = Path(src)
    if not src.is_dir():
        return False, "source is not a directory"
    if src.is_symlink():
        return False, "symlink, not moved"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"cannot create target: {exc}"

    if preserve_name and (target_dir / src.name).exists():
        return False, (
            f"a folder named {src.name}/ already exists in "
            f"{target_dir.name}/ (left in place)"
        )

    final_target = (
        target_dir / src.name
        if preserve_name
        else utils.unique_target_dir(target_dir, src.name)
    )
    try:
        src.rename(final_target)
    except OSError:
        try:
            import shutil

            shutil.move(str(src), str(final_target))
        except Exception as exc:  # pragma: no cover - last-resort path
            logger.error(f"organize: dir move failed {src.name}: {exc}")
            return False, f"move failed: {exc}"

    # Relocating a folder changes the absolute path of every file inside it.
    # verify.py diffs snapshots by absolute path, so each of those files needs
    # its own traceable record -- otherwise C4 reports them as unauthorized
    # deletions and the whole run rolls back.
    moved_files = _record_nested_moves(
        src, final_target, session, reason or target_dir.name
    )
    # The container directory itself is *created* by the move, not a user
    # move: rollback reverses the file records and then rmdir's the (empty)
    # container. Recording it as a plain move instead would make rollback try
    # to rename the folder back on top of the files it just restored.
    _record_created_tree(final_target, session)
    logger.info(
        f"organize: moved dir {src.name} -> {final_target} ({moved_files} file(s))"
    )
    return True, str(final_target)


def _record_nested_moves(
    old_root: Path,
    new_root: Path,
    session: utils.OrganizeSession,
    reason: str,
) -> int:
    """Record a move for every regular file under a relocated folder.

    Returns the number of records added. Hidden files and symlinks are
    skipped, matching what the scanner and snapshots consider.
    """
    added = 0
    if not new_root.is_dir():
        return added
    for p in sorted(new_root.rglob("*")):
        if p.is_dir() or p.is_symlink() or utils.is_hidden(p):
            continue
        try:
            rel = p.relative_to(new_root)
        except ValueError:  # pragma: no cover - defensive
            continue
        old = old_root / rel
        session.add_move(old, p, reason=reason, status="moved")
        added += 1
    return added


def _record_created_tree(final_target: Path, session: utils.OrganizeSession) -> None:
    """Register *final_target* and every directory inside it as created.

    Relocating ``src/`` into ``material/initial/src`` also creates
    ``material/initial/src/data`` (and any deeper folders) as a side effect of
    the rename. Rollback restores the nested files first and then rmdir's the
    containers deepest-first -- if the inner directories are not on the
    candidate list they survive as empty husks, which is exactly the
    "leftover material/ tree after rollback" bug this prevents.
    """
    known = set(session.new_directories)
    for d in sorted(final_target.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not d.is_dir() or d.is_symlink():
            continue
        if str(d) not in known:
            session.new_directories.append(str(d))
            known.add(str(d))
    if str(final_target) not in known:
        session.new_directories.append(str(final_target))


def organize_folder(
    root: Path,
    session: Optional[utils.OrganizeSession] = None,
    rules: Optional[rules_mod.Rules] = None,
    manifest: Optional[sources_mod.SourceManifest] = None,
) -> OrganizeResult:
    """Run the full placement pass under *root*.

    Steps
    -----
    1. Build the three-tier structure (mkdir -p semantics).
    2. Create a fresh log file under process/.
    3. Move top-level files into their tier.
    3b. Re-file provenance-registered files stranded in ``process/`` back into ``initial/`` / ``downloaded/``.
    4. Promote nested loose files (outside owned tiers) into initial.
    5. Append a Placement log section to the log.
    6. Return an :class:`OrganizeResult`.

    The function is idempotent: running it twice leaves the structure intact
    and does not re-move files that already sit in their correct tier. The
    only exception is the re-file pass, which exists precisely to
    *correct* an earlier blind run once provenance has been declared.

    Parameters
    ----------
    manifest:
        Provenance manifest (see :mod:`scripts.sources`). When omitted it is
        loaded from disk. Files already sitting in ``material/initial/`` or
        ``material/downloaded/`` are registered automatically, so a user who
        drops material straight into ``initial/`` never has to declare
        anything and the manifest stays self-maintaining.

    Notes
    -----
    ``organize`` classifies **unknown** files with the keyword rules and
    sends the leftovers to ``process`` -- it never guesses that a file is the
    user's. Lifting pre-existing content into ``material/initial/`` is
    ``init``'s job (or ``mark-user``), which is what keeps ``initial/``
    exclusively the user's territory.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"organize target is not a directory: {root}")

    session = session or utils.OrganizeSession(root=root)
    result = OrganizeResult(session=session)

    # ---- Provenance: load (or bootstrap an empty one) and self-heal. ----
    man = manifest if manifest is not None else sources_mod.SourceManifest.load(root)
    _register_tier_residents(root, man)

    # 1. Structure.
    created = utils.build_structure(root, session)
    if created:
        utils.append_log(
            session,
            "Created directories",
            [f"- `{Path(c).relative_to(root)}`" for c in created],
        )

    # Record empty folders (skip, do not touch).
    empties = utils.list_empty_dirs(root)
    for e in empties:
        session.add_skipped(e, "empty folder, not organized")
        result.skipped.append((e, "empty folder, not organized"))
    if empties:
        utils.append_log(
            session,
            "empty folder(skipped)",
            [f"- `{e.relative_to(root)}`" for e in empties],
        )

    # 2. Top-level moves.
    for src in _top_level_files(root):
        target_rel = _match_rule(src.name, rules, man)
        target_dir = root / target_rel
        target = target_dir / src.name
        verbatim = man.is_verbatim(src.name)

        ok, msg = _move_file(src, target, session, preserve_name=verbatim)
        if ok:
            result.moved.append((src, target, target_rel))
        else:
            reason = msg
            session.add_skipped(src, reason)
            result.skipped.append((src, reason))

    # 3. Non-empty user sub-folders -> relocated **whole** into initial/.
    #    Flattening them destroyed the user's own folder structure;
    #    folder structure; "put my initial material back exactly as it was"
    #    means ``src/data/inner.txt`` must still be ``src/data/inner.txt``.
    for src in _user_subfolders(root):
        target_dir = root / USER_MATERIAL_TARGET
        ok, msg = move_directory(src, target_dir, session, preserve_name=True)
        if ok:
            result.moved.append((src, target_dir / src.name, USER_MATERIAL_TARGET))
        else:
            session.add_skipped(src, msg)
            result.skipped.append((src, msg))

    # 3b. Re-file provenance-registered files stranded in process/.
    #     A blind first run dumped them into the fallback bucket before
    #     anything was declared; now that the manifest knows who produced
    #     them, they must actually move home instead of sitting in process/
    #     forever. Unregistered files are NOT touched (idempotent re-runs).
    for src in _stranded_registered(root, man):
        target_rel = _match_rule(src.name, rules, man)
        target = root / target_rel / src.name
        ok, msg = _move_file(src, target, session, preserve_name=man.is_verbatim(src.name))
        if ok:
            result.moved.append((src, target, target_rel))
        else:
            session.add_skipped(src, msg)
            result.skipped.append((src, msg))

    # 4. Persist the provenance manifest (cheap: names only, no hashing).
    man.save()

    # 5. Write the Placement log to the log.
    _write_placement_log(root, session, result)

    return result


def _register_tier_residents(
    root: Path, manifest: sources_mod.SourceManifest
) -> None:
    """Register files already living in ``initial/`` / ``downloaded/``.

    A user who drops material straight into ``material/initial/`` (the
    documented workflow) never has to declare it: seeing the file there is
    enough. Same for downloads the assistant placed in ``downloaded/``.
    This is what keeps the manifest self-maintaining and idempotent.
    """
    for sub, kind in (
        (utils.SUB_INIT, sources_mod.KIND_USER),
        (utils.SUB_DOWNLOAD, sources_mod.KIND_DOWNLOADED),
    ):
        tier = root / utils.TIER_ORGANIZE / sub
        if not tier.is_dir():
            continue
        for p in sorted(tier.rglob("*")):
            if p.is_file() and not utils.is_hidden(p) and not p.is_symlink():
                manifest.add(kind, p.name)


def _stranded_registered(
    root: Path, manifest: sources_mod.SourceManifest
) -> List[Path]:
    """Top-level files in ``process/`` whose registered provenance says they
    belong in a different tier.

    Only files with an explicit ``user`` / ``downloaded`` registration are
    candidates. Tool artifacts (snapshots, logs, the manifest itself) are
    excluded via :func:`utils.is_allowed_new_file` (called with the
    root-relative path, so the manifest is protected by exact path), and
    **unregistered** files are never touched -- that is what keeps a re-run
    idempotent: a blind first organize dumps unknown files into ``process/``
    and they stay there until someone declares their provenance.
    """
    proc = root / utils.TIER_PROCESS
    if not proc.is_dir():
        return []
    out: List[Path] = []
    for p in sorted(proc.iterdir()):
        if p.is_dir() or p.is_symlink() or utils.is_hidden(p):
            continue
        if utils.is_allowed_new_file(f"{utils.TIER_PROCESS}/{p.name}"):
            continue
        if manifest.kind_of(p.name) in (
            sources_mod.KIND_USER,
            sources_mod.KIND_DOWNLOADED,
        ):
            out.append(p)
    return out


def _write_placement_log(
    root: Path,
    session: utils.OrganizeSession,
    result: OrganizeResult,
) -> None:
    """Append a human-readable placement report to the organize log."""
    lines: List[str] = []
    lines.append(f"moved {result.moved_count} files. ")
    lines.append("")
    for src, tgt, rule in result.moved:
        s_rel = _rel(root, src)
        t_rel = _rel(root, tgt)
        lines.append(f"- `{s_rel}` -> `{t_rel}` (Placement rule: {rule})")
    if result.skipped:
        lines.append("")
        lines.append(f"skipped {result.skipped_count} items: ")
        for p, reason in result.skipped:
            lines.append(f"- `{_rel(root, p)}`: {reason}")
    utils.append_log(session, "Placement log", lines)


def _rel(root: Path, p: Path) -> str:
    """Best-effort relative rendering for log lines."""
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def target_for(name: str) -> str:
    """Public helper: which standard sub-dir does *name* go into?

    Exposed for tests and for the index pipeline, which needs the same
    decision without re-implementing the keyword table.
    """
    return _match_rule(name)


def owned_prefixes() -> Tuple[str,...]:
    """Return the tool-owned directory prefixes (for verify)."""
    return _OWNED_PREFIXES
