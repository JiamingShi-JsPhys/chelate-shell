"""Doctor -- a read-only diagnostics command.

``doctor`` inspects a task folder and tells you (a) whether the standard
three-tier structure is present, (b) which loose files are stranded at
the root, (c) which of those look like deliverables that *should* have
been filed into ``results/``, and (d) whether the broadcast index is
fresh relative to the source tree.  It **writes nothing** -- no files
created, no moves, no re-broadcast -- so it is always safe to run.

Use it as a *triage* step: when something in a folder "feels off" (the
structure is missing, files are piled at the root, a deliverable landed
in the wrong tier, the broadcast map looks stale) run::

    python -m scripts.run doctor <root>

and follow the "next step" it prints.  This is the human-facing answer
to the C8 missed-init warning: doctor turns a *warning* into an
*actionable diagnosis*.
"""

from __future__ import annotations

import json as _json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from scripts import broadcast, rules, utils
from scripts.utils import logger


def _dt_fromiso(value: str) -> Optional[float]:
    """Parse the ISO-8601 ``generated_at`` string into an epoch timestamp.

    Returns ``None`` when the value is missing or unparseable -- callers
    treat that as "cannot prove fresh" and fall back to the mtime
    comparison only.
    """
    if not value:
        return None
    try:
        # Strip a trailing 'Z' (Zulu) marker that some runtimes refuse.
        norm = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(norm)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


@dataclass
class DoctorResult:
    """Outcome of one doctor run -- read-only findings plus next steps."""

    root: str
    structure_complete: bool = False
    missing_tiers: List[str] = field(default_factory=list)
    loose_root_files: List[str] = field(default_factory=list)
    deliverable_loose_files: List[str] = field(default_factory=list)
    broadcast_present: bool = False
    broadcast_fresh: bool = False
    next_step: str = ""

    @property
    def ok(self) -> bool:
        """True when nothing in the folder looks wrong (healthy)."""
        return (
            self.structure_complete
            and not self.loose_root_files
            and not self.deliverable_loose_files
        )

    def summary_lines(self) -> List[str]:
        lines = [f"Doctor: {self.root}"]
        lines.append(
            "  structure: "
            + ("complete (material/ + process/ + results/)"
               if self.structure_complete
               else f"incomplete -- missing: {', '.join(self.missing_tiers) or '(none)'}")
        )
        if self.loose_root_files:
            shown = ", ".join(self.loose_root_files[:8])
            more = f" (+{len(self.loose_root_files) - 8} more)" if len(self.loose_root_files) > 8 else ""
            lines.append(f"  loose files at root: {shown}{more}")
        else:
            lines.append("  loose files at root: none")
        if self.deliverable_loose_files:
            shown = ", ".join(self.deliverable_loose_files[:8])
            more = f" (+{len(self.deliverable_loose_files) - 8} more)" if len(self.deliverable_loose_files) > 8 else ""
            lines.append(f"  deliverable-looking files stranded at root: {shown}{more}")
        bstate = "absent" if not self.broadcast_present else ("fresh" if self.broadcast_fresh else "stale")
        lines.append(f"  broadcast index: {bstate}")
        lines.append(f"  next step: {self.next_step}")
        return lines


def _loose_root_files(root: Path) -> List[str]:
    """Files at the task root that are neither tool-owned nor hidden."""
    names: List[str] = []
    if not root.is_dir():
        return names
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        if p.name.startswith(".") or p.name in utils.ROOT_OWNED_FILES:
            continue
        names.append(p.name)
    return names


def _newest_source_mtime(root: Path) -> float:
    """Newest mtime of any source file, excluding tool-owned zones.

    Walks the whole tree (no symlink follow) and skips hidden entries, the
    ``process/`` bookkeeping zone, and ``_broadcast/`` itself -- the zones
    the tool owns and that legitimately change on every run.  Returns 0.0
    when the tree holds no source files at all.
    """
    owned = (utils.TIER_PROCESS, utils.BROADCAST_DIRNAME)
    newest = 0.0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            n for n in dirnames
            if not n.startswith(".") and n not in owned
        ]
        base = Path(dirpath)
        for fn in filenames:
            if fn.startswith("."):
                continue
            p = base / fn
            try:
                if p.is_symlink() or not p.is_file():
                    continue
                m = p.stat().st_mtime
            except OSError:
                continue
            if m > newest:
                newest = m
    return newest


def _broadcast_fresh(root: Path, max_files: int) -> bool:
    """Heuristic freshness check using only what the index already stores.

    A broadcast index is "fresh" when no source file anywhere under the
    folder is newer than the index's own write time.  This is a
    conservative, read-only heuristic (mtime comparison, no fingerprint
    machinery required) that is good enough for triage: it flags "the map
    may be stale, run ``broadcast``" without ever mutating the folder.
    """
    index_path = root / utils.BROADCAST_DIRNAME / "index.json"
    try:
        index_mtime = index_path.stat().st_mtime
    except OSError:
        return False

    newest_source = _newest_source_mtime(root)
    if newest_source > index_mtime:
        # Content genuinely post-dates the index write.
        return False

    # Cross-check against the recorded generated_at when present.  The
    # timestamp is written at *second* granularity, while filesystem mtimes
    # carry sub-second precision -- so allow a one-second grace window, or
    # an index built in the same wall-clock second as its newest source
    # would be flagged stale in error.  Only flag staleness when the
    # content genuinely post-dates the recorded generation time by more
    # than that window.
    try:
        payload = _json.loads(index_path.read_text(encoding="utf-8"))
        gen_epoch = _dt_fromiso(str(payload.get("generated_at", "")))
        if gen_epoch is not None and newest_source > gen_epoch + 1.0:
            return False
    except (OSError, ValueError, TypeError):
        pass

    return True


def doctor(
    root: Path,
    max_files: int = broadcast.DEFAULT_MAX_FILES,
    verbose: bool = False,
    quiet: bool = False,
) -> DoctorResult:
    """Diagnose *root* and return a read-only :class:`DoctorResult`.

    Never mutates the folder: no files are created, moved or rewritten.
    The returned result carries the findings and a concrete next step so
    the caller (human or agent) knows exactly which tool to run.
    """
    root = Path(root).resolve()
    logger.setup_logging(root, verbose=verbose, quiet=quiet, file_log=False)

    result = DoctorResult(root=str(root))

    if not root.is_dir():
        result.next_step = f"root does not exist: {root}"
        return result

    # 1) Structure completeness.
    result.structure_complete = utils.structure_complete(root)
    for tier in (utils.TIER_ORGANIZE, utils.TIER_PROCESS, utils.TIER_RESULT):
        if not (root / tier).is_dir():
            result.missing_tiers.append(tier)

    # 2) Loose files at the root, and which of them look like
    #    deliverables (keyword hit -> results/) rather than material.
    result.loose_root_files = _loose_root_files(root)
    for name in result.loose_root_files:
        if rules.target_for(name) == "results":
            result.deliverable_loose_files.append(name)

    # 3) Broadcast index freshness (mtime vs. source tree).
    bdir = root / utils.BROADCAST_DIRNAME
    result.broadcast_present = (bdir / "INDEX.md").is_file() and (bdir / "index.json").is_file()
    if result.broadcast_present:
        result.broadcast_fresh = _broadcast_fresh(root, max_files)

    # 4) Pick the single most useful next step.
    if not result.structure_complete:
        if result.deliverable_loose_files:
            result.next_step = (
                "run `init --classify` to build the structure and file the "
                "stranded deliverables into results/ (a missed-init signal)"
            )
        else:
            result.next_step = "run `init` to build the standard structure"
    elif result.broadcast_present and not result.broadcast_fresh:
        result.next_step = "run `broadcast` to refresh the stale _broadcast/ index"
    else:
        result.next_step = "healthy -- no action needed"

    return result


def doctor_summary_lines(root: Path, max_files: int = broadcast.DEFAULT_MAX_FILES,
                         verbose: bool = False, quiet: bool = False) -> List[str]:
    """Run :func:`doctor` and return its report lines (CLI convenience)."""
    return doctor(root, max_files=max_files,
                  verbose=verbose, quiet=quiet).summary_lines()
