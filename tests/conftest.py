"""Shared pytest fixtures and helpers for the Chelate Shell test suite.

Strategy note: several legacy skills ship a package named `scripts` (or `src`).
Importing two of them into one pytest process would collide in sys.modules,
so per-skill code runs in an isolated subprocess via `run_in_skill()`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"

ALL_SKILLS = [
    "task-organizer", "multi-dim-manager", "document-evolution-tracker",
    "capstone-labmate", "video-tracker", "longitudinal-analysis",
    "formula-validator", "ai-trace-remover", "conflict-detector",
    "fulltext-extractor", "literature-retriever", "bibtex-normalizer",
    "reference-auditor", "data-profiler",
]
LEGACY_SKILLS = ALL_SKILLS[:9]
NEW_SKILLS = ALL_SKILLS[9:]

STAGE_OF = {
    "task-organizer": "workspace", "multi-dim-manager": "workspace",
    "document-evolution-tracker": "workspace",
    "capstone-labmate": "ingest", "video-tracker": "ingest",
    "fulltext-extractor": "ingest", "literature-retriever": "ingest",
    "bibtex-normalizer": "ingest",
    "longitudinal-analysis": "gates", "formula-validator": "gates",
    "conflict-detector": "gates", "reference-auditor": "gates",
    "data-profiler": "gates",
    "ai-trace-remover": "processors",
}

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def run_in_skill(skill: str, code: str, timeout: int = 300) -> dict:
    """Run `code` in a subprocess with <skill root> first on sys.path.

    The code must print a single JSON object on stdout; it is parsed and
    returned. Raises AssertionError with stderr on any failure.
    """
    env = dict(os.environ)
    skill_root = SKILLS_DIR / skill
    # skill root first (packages `scripts` / `src` win), then the bare-module
    # folder used by capstone-labmate (scripts/_capx.py, no __init__.py).
    paths = [str(skill_root), str(skill_root / "scripts")]
    env["PYTHONPATH"] = os.pathsep.join(paths) + os.pathsep \
        + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(REPO_ROOT),
                          env=env, capture_output=True, text=True,
                          timeout=timeout)
    if proc.returncode != 0:
        raise AssertionError(
            f"run_in_skill({skill}) failed rc={proc.returncode}\n"
            f"stdout: {proc.stdout[-2000:]}\nstderr: {proc.stderr[-2000:]}")
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    return json.loads(lines[-1])


@pytest.fixture()
def workspace(tmp_path) -> Path:
    """A fresh four-zone workspace (process/gates pre-created)."""
    for zone in ("inbox", "process", "process/gates", "results",
                 "_broadcast"):
        (tmp_path / zone).mkdir(parents=True, exist_ok=True)
    return tmp_path
