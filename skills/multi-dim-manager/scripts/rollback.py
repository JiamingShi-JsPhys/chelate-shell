"""Non-destructive rollback to a past round's snapshot.

Default behaviour restores the target round's recorded post-state into a *new*
directory (``<workdir>.rollback_NNNN``) so the live working directory is never
touched. With ``force=True`` the manager restores into the live working
directory instead. Every rollback is itself written to the audit log.
"""

from __future__ import annotations

from pathlib import Path

from .audit import AuditLog, RoundRecord, now_iso
from .errors import RollbackError
from .snapshot import Manifest, restore


def rollback_to(
    audit: AuditLog,
    round_no: int,
    workdir: Path,
    store_dir: Path,
    force: bool = False,
) -> Path:
    """Restore round *round_no*'s post-state.

    Args:
        audit: The experiment audit log.
        round_no: 1-based round to roll back to.
        workdir: Live working directory (used only when ``force``).
        store_dir: Content-addressed store produced during the run.
        force: If True, restore into *workdir*; otherwise into a new dir.

    Returns:
        The directory the state was restored into.

    Raises:
        RollbackError: If the requested round was never recorded.
    """
    rec = audit.get(round_no)
    if rec is None:
        raise RollbackError(f"round {round_no} was never recorded")
    if not rec.snapshot_post:
        raise RollbackError(f"round {round_no} has no post-snapshot to restore")

    # snapshot_post is the inner ``relpath -> hash`` map, not the wrapped dict.
    manifest = Manifest(
        round_no=rec.round_no, phase="post", files=rec.snapshot_post,
        store_dir=store_dir,
    )
    workdir = Path(workdir)
    if force:
        target = workdir
    else:
        target = workdir.parent / f"{workdir.name}.rollback_{round_no:04d}"

    restored = restore(manifest, target)
    audit.record(
        RoundRecord(
            round_no=round_no,
            status="rolledback",
            timestamp=now_iso(),
            params=rec.params,
            input_hash=rec.input_hash,
            output_hash=rec.output_hash,
            note=f"restored post-state of round {round_no} into {restored}"
            + (" (force overwrite)" if force else " (new directory)"),
        )
    )
    return restored
