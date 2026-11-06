"""rotate.py -- automatic artifact rotation.

Why this exists
---------------
Every run of the pipeline writes timestamped artifacts into ``process/``:

- ``YYYYMMDD_HHMMSS_before.json`` / ``..._after.json`` (snapshots)
- ``YYYYMMDD_HHMMSS_history.json`` (operation history)
- ``YYYYMMDD_HHMMSS_OrganizeLog.md`` / ``..._Cancelled.md`` (logs)

Nothing ever removed them, so a folder that is organized weekly grows
without bound. This module keeps only the newest *N* runs' worth of
artifacts and deletes the rest, so ``process/`` stays bounded.

Safety rules
------------
1. **The newest ``before`` and the newest ``after`` snapshot are always
   kept**, regardless of *N*, so :func:`scripts.snapshot.find_latest_snapshot`
   and a standalone ``verify`` can never lose their reference state.
2. Files are grouped by their timestamp prefix, so a run's before/after/
   history/log are rotated together and the audit trail stays coherent.
3. Anything that is not a recognised timestamped artifact is left alone --
   fixed-name outputs (``Index.md``, ``verification_report.md``,
   ``duplicate_report.md``, ``logs/``) are never touched.
4. Rotation never raises: unreadable entries are skipped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set

from scripts import utils

#: Default number of runs to keep.
DEFAULT_KEEP = 5

#: ``YYYYMMDD_HHMMSS`` prefix shared by every timestamped artifact.
_STAMP_RE = re.compile(r"^(\d{8}_\d{6})_")

#: Recognised rotating artifacts (matched on the suffix after the stamp).
_ROTATING_SUFFIXES = (
    "_before.json",
    "_after.json",
    "_history.json",
    "_organizelog.md",
    "_cancelled.md",
)


@dataclass
class RotateResult:
    """Outcome of one rotation pass."""

    root: str
    keep: int
    deleted: List[str] = field(default_factory=list)
    kept_groups: List[str] = field(default_factory=list)
    protected: List[str] = field(default_factory=list)

    @property
    def deleted_count(self) -> int:
        return len(self.deleted)

    def summary_lines(self) -> List[str]:
        lines = [
            f"rotate: keep={self.keep}, "
            f"deleted {self.deleted_count} expired artifact(s)"
        ]
        if self.protected:
            lines.append(f"rotate: protected latest snapshots {sorted(set(self.protected))}")
        return lines


def _stamp_of(name: str) -> str:
    """Return the ``YYYYMMDD_HHMMSS`` stamp of an artifact name, or ''."""
    m = _STAMP_RE.match(name.lower())
    return m.group(1) if m else ""


def _is_rotating(name: str) -> bool:
    """True when *name* is a timestamped artifact we are allowed to rotate."""
    low = name.lower()
    return any(low.endswith(suffix) for suffix in _ROTATING_SUFFIXES)


def _collect(root: Path) -> Dict[str, List[Path]]:
    """Group rotating artifacts under ``process/`` by their timestamp stamp."""
    groups: Dict[str, List[Path]] = {}
    proc = Path(root) / utils.TIER_PROCESS
    if not proc.is_dir():
        return groups
    for p in proc.iterdir():
        if not p.is_file():
            continue
        if not _is_rotating(p.name):
            continue
        stamp = _stamp_of(p.name)
        if not stamp:
            continue
        groups.setdefault(stamp, []).append(p)
    return groups


def _latest_stamp(root: Path, phase: str) -> str:
    """Return the stamp of the newest *phase* snapshot ('' when absent)."""
    proc = Path(root) / utils.TIER_PROCESS
    if not proc.is_dir():
        return ""
    best = ""
    for p in proc.iterdir():
        if not p.is_file():
            continue
        low = p.name.lower()
        if not low.endswith(f"_{phase}.json"):
            continue
        stamp = _stamp_of(p.name)
        if stamp > best:
            best = stamp
    return best


def rotate_artifacts(root: Path, keep: int = DEFAULT_KEEP) -> RotateResult:
    """Keep only the newest *keep* runs' artifacts under ``process/``.

    Parameters
    ----------
    root:
        Task root.
    keep:
        How many runs (timestamp groups) to retain. Values below 1 are
        clamped to 1 -- deleting every snapshot would break verification.

    Returns
    -------
    RotateResult:
        Lists what was deleted and what was protected.
    """
    root = Path(root).resolve()
    keep = max(1, int(keep))
    result = RotateResult(root=str(root), keep=keep)

    groups = _collect(root)
    if not groups:
        return result

    # Safety: never rotate away the snapshots a verify would look up.
    protected: Set[str] = {_latest_stamp(root, "before"), _latest_stamp(root, "after")}
    protected.discard("")
    result.protected = sorted(protected)

    stamps_desc = sorted(groups.keys(), reverse=True)
    keep_set: Set[str] = set(stamps_desc[:keep]) | protected
    result.kept_groups = sorted(keep_set, reverse=True)

    for stamp in stamps_desc:
        if stamp in keep_set:
            continue
        for p in groups[stamp]:
            try:
                p.unlink()
                result.deleted.append(str(p))
            except OSError:
                # Best effort: a locked file is simply kept for now.
                continue

    return result


def rotate_snapshots(root: Path, keep: int = DEFAULT_KEEP) -> RotateResult:
    """Rotate **only** the before/after snapshots (history and logs survive).

    Provided for callers that want a tighter retention window for the bulky
    JSON snapshots without touching the audit trail.
    """
    root = Path(root).resolve()
    keep = max(1, int(keep))
    result = RotateResult(root=str(root), keep=keep)

    proc = root / utils.TIER_PROCESS
    if not proc.is_dir():
        return result

    snaps: List[Path] = []
    for p in proc.iterdir():
        if p.is_file() and _stamp_of(p.name) and (
            p.name.lower().endswith("_before.json")
            or p.name.lower().endswith("_after.json")
        ):
            snaps.append(p)
    if not snaps:
        return result

    stamps = sorted({_stamp_of(p.name) for p in snaps}, reverse=True)
    protected = {_latest_stamp(root, "before"), _latest_stamp(root, "after")}
    protected.discard("")
    result.protected = sorted(protected)
    keep_set = set(stamps[:keep]) | protected
    result.kept_groups = sorted(keep_set, reverse=True)

    for p in snaps:
        if _stamp_of(p.name) in keep_set:
            continue
        try:
            p.unlink()
            result.deleted.append(str(p))
        except OSError:
            continue

    return result
