"""Shared test fixtures and the CLI runner used by the end-to-end tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Register this conftest under the module name `conftest` as well, so
# `from conftest import ...` in the test modules works even when pytest's
# rootdir is a different skill (each skill ships its own tests/conftest.py).
sys.modules.setdefault("conftest", sys.modules[__name__])

CLI = ROOT / "scripts" / "cli.py"


def run_cli(*args: str, timeout: int = 300):
    """Run the CLI and return the completed process."""
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, timeout=timeout)


def cli_json(*args: str, timeout: int = 300) -> tuple[dict, int]:
    """Run the CLI and return (summary dict, exit code)."""
    proc = run_cli(*args, timeout=timeout)
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    assert lines, f"no output from CLI; stderr={proc.stderr[:400]}"
    return json.loads(lines[-1]), proc.returncode


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT
