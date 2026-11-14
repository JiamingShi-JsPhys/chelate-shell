"""Shared pytest fixtures and helpers for the Chelate Shell test suite.

Strategy note: several legacy skills ship a package named `scripts` (or `src`).
Importing two of them into one pytest process would collide in sys.modules,
so per-skill code runs in an isolated subprocess via `run_in_skill()`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"

ALL_SKILLS = [
    "task-organizer", "document-evolution-tracker",
    "video-tracker",
    "formula-validator", "conflict-detector",
    "fulltext-extractor", "literature-retriever", "bibtex-normalizer",
    "reference-auditor", "data-profiler",
    "quantitative-validator", "ml-auditor",
    "latex-exporter",
    "security-guard",
    "sci-visualizer",
    "3d-modeler",
    "longitudinal-analysis", "ai-trace-remover", "multi-dim-manager",
]
LEGACY_SKILLS = ALL_SKILLS[:8]
NEW_SKILLS = ALL_SKILLS[8:]
# Skeleton skills used to ship manifest + SKILL.md only (run.py deferred)
# and were recorded as registry errors / excluded from routing. As of v1.2.0
# all three (quantitative-validator, ml-auditor, latex-exporter) have
# graduated: they now ship a real entrypoint and join the routing table, so
# this list is intentionally empty.
SKELETON_SKILLS: list = []
ROUTED_SKILLS = [s for s in ALL_SKILLS if s not in SKELETON_SKILLS]


def skill_root(name: str) -> Path:
    """Resolve a skill's directory.

    The layout is flat: every skill is `skills/<name>/`. Namespace folders in
    between are gone because the host skill scanners (Claude Code, Codex) do
    not descend into them; `test_registry.py` enforces that.
    """
    path = SKILLS_DIR / name
    if not path.is_dir():
        raise KeyError(f"skill not found: {name}")
    return path


def missing_modules(*modules):
    """Return the subset of `modules` that cannot be imported here.

    Skills are allowed to degrade to UNVERIFIED when an optional dependency
    is absent — that is the path a fresh user gets, and issue #1 asked CI to
    guard it. But a test that asserts a real verdict (PASS/FAIL from sympy,
    pint, pandas, …) has nothing to assert without the dependency, so it must
    skip rather than fail. `requires()` is the marker for those.
    """
    missing = []
    for mod in modules:
        try:
            found = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):  # parent package missing / bad name
            found = False
        if not found:
            missing.append(mod)
    return missing


def requires(*modules):
    """pytest marker: skip when an optional dependency is not installed."""
    missing = missing_modules(*modules)
    return pytest.mark.skipif(
        bool(missing),
        reason="optional dependency not installed: " + ", ".join(missing))


def entrypoint_of(skill: str) -> str:
    """Return the manifest entrypoint path for `skill` (e.g. run.py or
    scripts/run.py)."""
    import json
    manifest = (skill_root(skill) / "manifest.json").read_text(encoding="utf-8")
    return json.loads(manifest).get("entrypoint", "run.py")


def run_path_of(skill: str):
    """Absolute path to a skill's executable adapter (resolved from the
    manifest entrypoint, which may live under scripts/)."""
    return skill_root(skill) / entrypoint_of(skill)

STAGE_OF = {
    "task-organizer": "workspace",
    "document-evolution-tracker": "workspace",
    "multi-dim-manager": "workspace",
    "video-tracker": "ingest",
    "fulltext-extractor": "ingest", "literature-retriever": "ingest",
    "bibtex-normalizer": "ingest",
    "formula-validator": "gates",
    "conflict-detector": "gates", "reference-auditor": "gates",
    "data-profiler": "gates",
    "longitudinal-analysis": "gates",
    "quantitative-validator": "gates", "ml-auditor": "gates",
    "ai-trace-remover": "processors", "latex-exporter": "processors",
    "security-guard": "infrastructure",
    "sci-visualizer": "generation",
    "3d-modeler": "domain_extensions",
}

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def run_in_skill(skill: str, code: str, timeout: int = 300) -> dict:
    """Run `code` in a subprocess with <skill root> first on sys.path.

    The code must print a single JSON object on stdout; it is parsed and
    returned. Raises AssertionError with stderr on any failure.
    """
    env = dict(os.environ)
    skill_dir = skill_root(skill)
    # skill root first (packages `scripts` / `src` win), then the bare-module
    # folder for adapters that import helpers without an __init__.py.
    paths = [str(skill_dir), str(skill_dir / "scripts")]
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


@pytest.fixture(scope="session", autouse=True)
def _hermetic_approval_keys(tmp_path_factory):
    """Keep approval keys out of the user's real per-user key directory.

    ``core.approval`` puts signing keys in ``%LOCALAPPDATA%`` (or
    ``$XDG_DATA_HOME``) so they are unreachable from a workspace; the suite
    redirects them to a temp directory instead of littering that path.
    """
    root = tmp_path_factory.mktemp("chelate-keys")
    previous = os.environ.get("CHELATE_KEY_ROOT")
    os.environ["CHELATE_KEY_ROOT"] = str(root)
    # The update notice would otherwise reach for github.com from every CLI
    # subprocess a test starts; a test suite is not a place to ask the network.
    previous_off = os.environ.get("CHELATE_UPDATE_OFF")
    os.environ["CHELATE_UPDATE_OFF"] = "1"
    yield root
    if previous is None:
        os.environ.pop("CHELATE_KEY_ROOT", None)
    else:
        os.environ["CHELATE_KEY_ROOT"] = previous
    if previous_off is None:
        os.environ.pop("CHELATE_UPDATE_OFF", None)
    else:
        os.environ["CHELATE_UPDATE_OFF"] = previous_off


@pytest.fixture()
def workspace(tmp_path) -> Path:
    """A fresh four-zone workspace (process/gates pre-created)."""
    for zone in ("inbox", "process", "process/gates", "results",
                 "_broadcast"):
        (tmp_path / zone).mkdir(parents=True, exist_ok=True)
    return tmp_path
