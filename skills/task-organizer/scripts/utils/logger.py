"""logger.py -- standard-library logging for task-organizer.

This module centralizes logging so that key operations (file moves, skips,
and failures) are recorded at INFO level into ``process/logs/YYYYMMDD.log``,
and optionally mirrored to the console.

Design constraints
------------------
- Standard library only (logging); no third-party dependencies.
- The log file is created **lazily** on the first emitted record, so it never
  appears before the first log call (which happens during the organize step,
  between the before/after snapshots). This keeps it from perturbing the
  forced verification (the file is "new" in the after-snapshot, flagged only
  by the non-fatal C6, never by C2/C5).
- When :func:`setup_logging` is not called (e.g. inside unit tests), the
  module is a no-op -- no console noise, no files written.

Usage
-----
- Call ``setup_logging(root, verbose=..., quiet=...)`` once at the start of a
  run.
- Use the module helpers ``info`` / ``warning`` / ``error`` / ``debug`` at
  key points.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "task-organizer"
_LOGGER = logging.getLogger(_LOGGER_NAME)

_FMT = logging.Formatter(
    "%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Module-level state. Kept deliberately small; this is a tool, not a framework.
_STATE: dict = {
    "root": None,
    "verbose": False,
    "quiet": False,
    "file_log": True,
    "file_handler": None,  # type: Optional[logging.FileHandler]
    "console_handler": None,  # type: Optional[logging.StreamHandler]
}


def setup_logging(
    root: Optional[Path] = None,
    verbose: bool = False,
    quiet: bool = False,
    file_log: bool = True,
) -> logging.Logger:
    """Configure the task-organizer logger.

    Parameters
    ----------
    root:
        The task root. When set, the next log emission will open
        ``<root>/process/logs/YYYYMMDD.log`` lazily.
    verbose:
        Emit DEBUG to the console as well.
    quiet:
        Suppress INFO on the console (only WARNING and above show); the file
        log is always at DEBUG detail.
    file_log:
        When False, **no** log file is ever opened -- console only. Used by
        ``init``, whose whole point is to stay cheap and leave nothing behind
        that a snapshot would have to account for.
    """
    _STATE["root"] = Path(root).resolve() if root is not None else None
    _STATE["verbose"] = verbose
    _STATE["quiet"] = quiet
    _STATE["file_log"] = file_log
    _STATE["file_handler"] = None

    if _STATE["console_handler"] is None:
        ch = logging.StreamHandler()
        ch.setFormatter(_FMT)
        _LOGGER.addHandler(ch)
        _STATE["console_handler"] = ch
    ch = _STATE["console_handler"]
    if quiet:
        ch.setLevel(logging.WARNING)
    elif verbose:
        ch.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)

    if not _LOGGER.handlers:  # ensure at least one handler exists
        _LOGGER.addHandler(logging.NullHandler())
    _LOGGER.setLevel(logging.DEBUG)
    return _LOGGER


def _ensure_file_handler() -> None:
    """Open the per-day log file on first use (lazy)."""
    if _STATE["file_handler"] is not None:
        return
    root = _STATE["root"]
    if root is None or not _STATE.get("file_log", True):
        return
    log_dir = root / "process" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        fh = logging.FileHandler(log_dir / f"{stamp}.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_FMT)
        _LOGGER.addHandler(fh)
        _STATE["file_handler"] = fh
    except OSError:
        # Never let logging break the pipeline.
        pass


def _emit(level: int, msg: str) -> None:
    _ensure_file_handler()
    _LOGGER.log(level, msg)


def debug(msg: str) -> None:
    _emit(logging.DEBUG, msg)


def info(msg: str) -> None:
    _emit(logging.INFO, msg)


def warning(msg: str) -> None:
    _emit(logging.WARNING, msg)


def error(msg: str) -> None:
    _emit(logging.ERROR, msg)


def reset() -> None:
    """Drop handlers (used by tests to avoid cross-test leakage)."""
    for h in list(_LOGGER.handlers):
        _LOGGER.removeHandler(h)
    _STATE["file_handler"] = None
    _STATE["console_handler"] = None
    _STATE["root"] = None
