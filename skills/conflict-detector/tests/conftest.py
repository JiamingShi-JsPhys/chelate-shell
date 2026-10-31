"""Shared pytest fixtures for the conflict-detector test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture()
def two_docs() -> Dict[str, str]:
    """Two inline JSON documents with a numeric + boolean conflict."""
    return {
        "a": '{"x": 1, "active": true}',
        "b": '{"x": 9, "active": false}',
    }
