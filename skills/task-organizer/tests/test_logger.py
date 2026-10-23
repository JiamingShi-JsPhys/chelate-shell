"""Tests for :mod:`scripts.utils.logger` -- standard-library logging .

The logger writes to ``process/logs/YYYYMMDD.log`` lazily and mirrors key
operations to the console. These tests verify the lazy file creation, the
level switches, and that the module stays a no-op until :func:`setup_logging`
is called.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.utils import logger


@pytest.fixture(autouse=True)
def _reset_logger():
    """Isolate logger state between tests (handlers + root)."""
    logger.reset()
    yield
    logger.reset()


# ---------------------------------------------------------------------------
# Lazy file creation
# ---------------------------------------------------------------------------


def test_log_file_not_created_before_emit(tmp_path: Path) -> None:
    logger.setup_logging(root=tmp_path)
    log_dir = tmp_path / "process" / "logs"
    assert not log_dir.exists()  # lazy: nothing written yet

    logger.info("hello")
    # After the first emit the per-day file must exist with the message.
    today = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"{today}.log"
    assert log_file.exists()
    assert "hello" in log_file.read_text(encoding="utf-8")


def test_multiple_emits_append_to_same_day_file(tmp_path: Path) -> None:
    logger.setup_logging(root=tmp_path)
    logger.info("first")
    logger.info("second")
    today = datetime.now().strftime("%Y%m%d")
    text = (tmp_path / "process" / "logs" / f"{today}.log").read_text(encoding="utf-8")
    assert "first" in text
    assert "second" in text


# ---------------------------------------------------------------------------
# Level switches
# ---------------------------------------------------------------------------


def test_debug_emitted_only_when_verbose(tmp_path: Path, capsys) -> None:
    # Without verbose, debug is not emitted to the console (stderr).
    logger.setup_logging(root=tmp_path, verbose=False)
    logger.debug("dbg-msg")
    assert "dbg-msg" not in capsys.readouterr().err

    # With verbose, debug reaches the console.
    logger.reset()
    logger.setup_logging(root=tmp_path, verbose=True)
    logger.debug("dbg-msg")
    assert "dbg-msg" in capsys.readouterr().err


def test_quiet_suppresses_info(tmp_path: Path, capsys) -> None:
    logger.setup_logging(root=tmp_path, quiet=True)
    logger.info("info-hidden")
    assert "info-hidden" not in capsys.readouterr().err
    # Warnings still surface even in quiet mode (WARNING >= threshold).
    logger.warning("warn-visible")
    assert "warn-visible" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# No-op without setup
# ---------------------------------------------------------------------------


def test_emit_without_setup_does_not_raise(tmp_path: Path) -> None:
    # Without setup_logging there is no file handler; emit must be a no-op.
    logger.reset()
    # Must not raise even though _STATE['root'] is None.
    logger.info("safe")


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def test_reset_clears_handlers(tmp_path: Path) -> None:
    logger.setup_logging(root=tmp_path)
    assert logger._LOGGER.handlers
    logger.reset()
    assert not logger._LOGGER.handlers
