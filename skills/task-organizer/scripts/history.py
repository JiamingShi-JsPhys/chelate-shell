"""history.py -- operation history with user-initiated undo / redo.

After every *successful* organize, :func:`write_history` persists a compact
record of every move (and directory creation) into
``process/history/YYYYMMDD_HHMMSS.json``. This is the user-facing counterpart
to :mod:`rollback`:

- ``rollback`` is automatic and fires only when *verification fails* -- it
  restores the before-state of the run that is being undone.
- ``undo`` / ``redo`` are *user-initiated* and operate on an already
  *verified* state: ``undo`` reverses the moves recorded in a history file;
  ``redo`` re-applies them.

Both ``undo`` and ``redo`` are themselves wrapped in the forced-verification
protocol: the reverse/replay moves are snapshotted before and after, and if
verification fails the operation is rolled back so the folder is never left
in a half-applied, un-auditable state.

The history file is generated *after* the main run passes verification, so it
does not perturb the main run's snapshots; verify.py whitelists
``process/history/*.json`` as an allowed new file (C6 only warns on it).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from scripts import organize, snapshot, utils
from scripts.utils import logger

HISTORY_DIRNAME = "history"
HISTORY_PREFIX = "history"


@dataclass
class HistoryAction:
    """A single recorded operation."""

    action: str # "move"
    source: str # absolute original path
    target: str # absolute path after the operation
    reason: str # placement rule / "undo" / "redo"
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "source": self.source,
            "target": self.target,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryAction":
        return cls(
            action=d.get("action", "move"),
            source=d["source"],
            target=d["target"],
            reason=d.get("reason", ""),
            timestamp=d.get("timestamp", ""),
        )


@dataclass
class History:
    """The persisted operation history for one organize run."""

    created_at: str
    root: str
    actions: List[HistoryAction] = field(default_factory=list)
    created_dirs: List[str] = field(default_factory=list)
    before_snapshot: Optional[str] = None
    after_snapshot: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "created_at": self.created_at,
            "root": self.root,
            "before_snapshot": self.before_snapshot,
            "after_snapshot": self.after_snapshot,
            "created_dirs": self.created_dirs,
            "actions": [a.to_dict() for a in self.actions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "History":
        return cls(
            created_at=d.get("created_at", ""),
            root=d.get("root", ""),
            actions=[HistoryAction.from_dict(a) for a in d.get("actions", [])],
            created_dirs=d.get("created_dirs", []),
            before_snapshot=d.get("before_snapshot"),
            after_snapshot=d.get("after_snapshot"),
        )


@dataclass
class HistoryResult:
    """Outcome of an undo / redo operation."""

    ok: bool
    actions: int = 0
    restored: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    message: str = ""

    @property
    def reversed_count(self) -> int:
        return len(self.restored)


def write_history(
    root: Path,
    session: utils.OrganizeSession,
    before: Optional[snapshot.Snapshot] = None,
    after: Optional[snapshot.Snapshot] = None,
) -> Path:
    """Persist *session*'s move records + created dirs to a history file.

    Parameters
    ----------
    root:
        Task root (history is written to ``<root>/process/history``).
    session:
        The :class:`OrganizeSession` produced by the organize step.
    before / after:
        Optional snapshot objects; their file names are recorded for context.

    Returns
    -------
    Path:
        The written history JSON path.
    """
    root = Path(root).resolve()
    ts = utils.now_stamp()
    hist = History(
        created_at=datetime.now().isoformat(),
        root=str(root),
        before_snapshot=Path(before.root).name if before is not None else None,
        after_snapshot=Path(after.root).name if after is not None else None,
        created_dirs=list(session.new_directories),
        actions=[
            HistoryAction(
                action="move",
                source=rec.source,
                target=rec.target,
                reason=rec.reason,
                timestamp=rec.timestamp,
            )
            for rec in session.move_records
            if rec.status == "moved"
        ],
    )
    history_dir = root / utils.TIER_PROCESS / HISTORY_DIRNAME
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / f"{ts}_{HISTORY_PREFIX}.json"
    utils.write_json(path, hist.to_dict())
    logger.info(f"history: wrote {path.name} ({len(hist.actions)} moves)")
    return path


def _load_history_file(path: Path) -> History:
    """Load a history JSON document (raises on bad input)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return History.from_dict(data)


def _apply_directions(
    history: History,
    root: Path,
    forward: bool,
) -> "tuple":
    """Apply moves in forward (redo) or reverse (undo) direction.

    Returns ``(success, restored, conflicts)``. Each move is recorded into a
    fresh session and goes through the same snapshot/verify/rollback protocol.
    """
    root = Path(root).resolve()
    session = utils.OrganizeSession(root=root)

    # Snapshot before the undo/redo operation.
    before = snapshot.make_snapshot(root, phase="before")

    restored: List[str] = []
    conflicts: List[str] = []
    for act in history.actions:
        # forward (redo): move source -> target again (the forward direction).
        # reverse (undo): move target -> source (the original location).
        if forward:
            src, tgt = Path(act.source), Path(act.target)
        else:
            src, tgt = Path(act.target), Path(act.source)
        if not src.exists():
            conflicts.append(f"{src} (source missing, cannot move)")
            continue
        tgt.parent.mkdir(parents=True, exist_ok=True)
        ok, msg = organize._move_file(src, tgt, session)
        if ok:
            restored.append(str(tgt))
        else:
            conflicts.append(f"{src} -> {tgt}: {msg}")

    # Snapshot after, then verify.
    after = snapshot.make_snapshot(root, phase="after")
    from scripts import verify

    vres = verify.verify(root, session=session, before=before, after=after, write_report=False)
    if vres.passed:
        return (True, restored, conflicts)

    # Verification failed -> roll back the undo/redo itself and report.
    from scripts import rollback

    rb = rollback.rollback(root, session=session)
    conflicts.extend(rb.conflicts)
    return (False, restored, conflicts)


def _load_history_or_report(path: Path) -> "tuple":
    """Load a history file, converting any bad input into a failed result.

    A mistyped path or a hand-mangled JSON must not dump a traceback at the
    user -- the CLI is expected to print ``ok: False`` plus the reason.

    Returns ``(history, error)``: exactly one of the two is None.
    """
    try:
        return _load_history_file(path), None
    except FileNotFoundError:
        return None, f"history file not found: {path}"
    except (OSError, ValueError) as exc:
        # ValueError covers json.JSONDecodeError (a subclass) and the
        # History.from_dict validation failures.
        return None, f"cannot read history file {path}: {exc}"


def undo(history_file: Path, root: Optional[Path] = None) -> HistoryResult:
    """Reverse the operations recorded in *history_file*.

    Parameters
    ----------
    history_file:
        The history JSON (e.g. ``process/history/20260101_120000_history.json``).
    root:
        Optional explicit task root; defaults to the history document's root.

    Returns
    -------
    HistoryResult:
        ``ok`` is True when the undo completed and re-verified cleanly.
    """
    path = Path(history_file)
    history, error = _load_history_or_report(path)
    if history is None:
        logger.error(f"undo: {error}")
        return HistoryResult(ok=False, actions=0, message=error)
    work_root = Path(root) if root is not None else Path(history.root)
    logger.info(f"undo: starting from {path.name}")
    success, restored, conflicts = _apply_directions(history, work_root, forward=False)
    return HistoryResult(
        ok=success,
        actions=len(history.actions),
        restored=restored,
        conflicts=conflicts,
        message=(
            "undo completed and re-verified"
            if success
            else "undo failed verification and was rolled back"
        ),
    )


def redo(history_file: Path, root: Optional[Path] = None) -> HistoryResult:
    """Re-apply the operations recorded in *history_file* (inverse of undo).

    Returns
    -------
    HistoryResult:
        ``ok`` is True when the redo completed and re-verified cleanly.
    """
    path = Path(history_file)
    history, error = _load_history_or_report(path)
    if history is None:
        logger.error(f"redo: {error}")
        return HistoryResult(ok=False, actions=0, message=error)
    work_root = Path(root) if root is not None else Path(history.root)
    logger.info(f"redo: starting from {path.name}")
    success, restored, conflicts = _apply_directions(history, work_root, forward=True)
    return HistoryResult(
        ok=success,
        actions=len(history.actions),
        restored=restored,
        conflicts=conflicts,
        message=(
            "redo completed and re-verified"
            if success
            else "redo failed verification and was rolled back"
        ),
    )


def latest_history(root: Path) -> Optional[Path]:
    """Return the most recent history file under ``process/history/``."""
    hist_dir = Path(root).resolve() / utils.TIER_PROCESS / HISTORY_DIRNAME
    if not hist_dir.is_dir():
        return None
    candidates = [p for p in hist_dir.iterdir() if p.name.endswith(f"_{HISTORY_PREFIX}.json")]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.name, reverse=True)
    return candidates[0]
