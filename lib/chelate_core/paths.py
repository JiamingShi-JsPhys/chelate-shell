"""Path resolution for the chelate-shell repository, skills and workspaces.

Every skill adapter resolves its own location through this module so that
adapters work no matter which directory the Router (or a user) launched
them from.
"""
from __future__ import annotations

import os
import pathlib

# lib/chelate_core/paths.py -> parents[0]=chelate_core, [1]=lib, [2]=repo root
REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[2])
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")


def repo_root() -> str:
    """Absolute path of the chelate-shell repository root."""
    return REPO_ROOT


def skills_dir() -> str:
    """Absolute path of the flat skills/ directory."""
    return SKILLS_DIR


def skill_root(dunder_file: str) -> str:
    """Absolute path of the skill directory that owns `dunder_file`.

    Called from a skill's root run.py as: skill_root(__file__).
    """
    return str(pathlib.Path(dunder_file).resolve().parent)


def workspace(root: str, *parts: str) -> str:
    """Join (and create) a path under the workspace root.

    The four-zone layout is process/ (intermediate), results/ (promoted),
    _broadcast/ (read-only index) and the user's own files; only process/
    and results/ are created here.
    """
    path = os.path.join(root, *parts)
    os.makedirs(path, exist_ok=True)
    return path


def resolve_input(root: str, path: str) -> pathlib.Path:
    """Resolve a CLI ``--input`` path against the workspace root.

    The Router launches adapters with cwd=repository root, so a relative
    input like ``draft.md`` would otherwise be looked up in the wrong
    directory. Resolution order: absolute paths and paths that already
    exist relative to the current working directory pass through
    unchanged; a relative path that exists under ``root`` is resolved
    against it; otherwise the original path is returned so the caller's
    "not found" error shows exactly what the user typed.
    """
    p = pathlib.Path(path)
    if p.is_absolute() or p.exists():
        return p
    candidate = pathlib.Path(root) / p
    return candidate if candidate.exists() else p


def resolve_inputs(root: str, raw_paths) -> tuple:
    """Resolve a list of CLI input paths against the workspace root.

    Returns ``(resolved, missing)``: ``resolved`` holds the absolute path of
    every input that exists (precedence rules: see resolve_input), and
    ``missing`` the original strings that could not be found anywhere — the
    caller reports them verbatim so the user sees what they typed.
    """
    resolved: list = []
    missing: list = []
    for raw in raw_paths or []:
        p = resolve_input(root, raw)
        if p.is_file():
            resolved.append(os.path.abspath(str(p)))
        else:
            missing.append(raw)
    return resolved, missing


def process_dir(root: str, *parts: str) -> str:
    """Path under <root>/process/ (created on demand)."""
    return workspace(root, "process", *parts)


def results_dir(root: str, *parts: str) -> str:
    """Path under <root>/results/ (created on demand)."""
    return workspace(root, "results", *parts)


def ensure_on_syspath(*paths: str) -> None:
    """Prepend each existing path to sys.path (idempotent)."""
    for p in paths:
        if p and p not in sys_path():
            insert_syspath(p)


def sys_path() -> list:
    import sys
    return sys.path


def insert_syspath(p: str) -> None:
    import sys
    sys.path.insert(0, p)
