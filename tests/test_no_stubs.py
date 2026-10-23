"""Architecture guard: skills stay thin, logic lives in lib/chelate_core.

v1.1.0 rule ("programs live outside the skills"): a skill's run.py is a
declarative adapter — argparse flags plus handlers that call into
lib/chelate_core. The business logic (extraction, search, parsing,
profiling, verification) must NOT be re-implemented inside skill folders.

This module enforces that rule mechanically, in addition to the classic
no-stub checks (no TODO/FIXME/NotImplementedError/bare-ellipsis bodies).
"""
from __future__ import annotations

import re

import pytest

from conftest import NEW_SKILLS, REPO_ROOT, SKILLS_DIR

STUB_PATTERNS = [
    (re.compile(r"^\s*TODO\b"), "TODO marker"),
    (re.compile(r"^\s*FIXME\b"), "FIXME marker"),
    (re.compile(r"^\s*XXX\b"), "XXX marker"),
    (re.compile(r"^\s*raise NotImplementedError"), "NotImplementedError"),
    (re.compile(r"^\s*\.\.\.\s*$"), "bare ellipsis body"),
]

ALL_SKILLS = sorted(p.name for p in SKILLS_DIR.iterdir()
                    if p.is_dir() and (p / "manifest.json").is_file())

LIB_DIR = REPO_ROOT / "lib" / "chelate_core"

# The no-stub rule applies to code written for v1.1.0: the five new skills
# and the shared library. The nine legacy skill trees are migrated
# byte-for-byte from the audited v1.0.0 release (proven by
# test_capability_guard.py) and keep their original contents untouched.
NO_STUB_TARGETS = [(s, SKILLS_DIR / s) for s in NEW_SKILLS]
NO_STUB_TARGETS.append(("lib/chelate_core", LIB_DIR))

# core modules that must exist and carry real weight (LOC floor)
CORE_MODULES = {
    "adapter.py": 150,
    "pdf_text.py": 40,
    "arxiv_search.py": 30,
    "bibtex_norm.py": 60,
    "doi_audit.py": 40,
    "csv_profile.py": 50,
    "formula_merge.py": 50,
    "yamlmini.py": 40,
    "paths.py": 25,
}

# adapter line budget: declarative wiring only
ADAPTER_MAX_LINES = 90
ADAPTER_MIN_LINES = 15


# ---------------------------------------------------------------------------
# classic no-stub checks (now across every skill + the shared library)
# ---------------------------------------------------------------------------

def _python_files(root):
    return [f for f in sorted(root.rglob("*.py"))
            if "__pycache__" not in str(f)]


@pytest.mark.parametrize("label,root", NO_STUB_TARGETS,
                         ids=[t[0] for t in NO_STUB_TARGETS])
def test_no_stub_markers(label, root):
    files = _python_files(root)
    assert files, f"{label} has no python files"
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8")
                                 .splitlines(), 1):
            for pattern, label_ in STUB_PATTERNS:
                assert not pattern.search(line), \
                    f"{f}:{i} {label_}: {line.strip()}"


@pytest.mark.parametrize("label,root", NO_STUB_TARGETS,
                         ids=[t[0] for t in NO_STUB_TARGETS])
def test_no_bare_pass_body(label, root):
    """`pass` is allowed only inside except/class/def with a real sibling."""
    for f in _python_files(root):
        lines = f.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if re.match(r"^\s*pass\s*$", line):
                ctx = "\n".join(lines[max(0, i - 3):i + 2])
                assert re.search(r"except|class |def ", ctx), \
                    f"{f}:{i} bare pass: {ctx!r}"


# ---------------------------------------------------------------------------
# thin-adapter rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", NEW_SKILLS)
def test_new_skill_adapter_is_thin(skill):
    """New skills: run.py only wires CLI -> lib, no business logic inline."""
    code = (SKILLS_DIR / skill / "run.py").read_text(encoding="utf-8")
    n_lines = len(code.splitlines())
    assert ADAPTER_MIN_LINES <= n_lines <= ADAPTER_MAX_LINES, \
        f"{skill}/run.py must be a thin adapter ({n_lines} lines, " \
        f"budget {ADAPTER_MIN_LINES}-{ADAPTER_MAX_LINES})"
    # it must delegate to the shared library
    assert "from lib.chelate_core import" in code, \
        f"{skill}/run.py does not import lib/chelate_core"
    # and it must not re-implement heavy logic locally
    for marker in ("import sympy", "import pandas", "import fitz",
                   "import arxiv", "import bibtexparser", "import requests"):
        assert marker not in code, \
            f"{skill}/run.py imports {marker} directly — move it to lib/"


@pytest.mark.parametrize("skill", NEW_SKILLS)
def test_new_skill_has_standard_files(skill):
    """The standard skill folder: SKILL.md, manifest.json, README.md,
    LICENSE, run.py, assets/config.yaml."""
    root = SKILLS_DIR / skill
    for rel in ("SKILL.md", "manifest.json", "README.md", "LICENSE",
                "run.py", "assets/config.yaml"):
        assert (root / rel).is_file(), f"{skill} missing {rel}"


@pytest.mark.parametrize("skill", ALL_SKILLS)
def test_every_skill_has_standard_files(skill):
    root = SKILLS_DIR / skill
    for rel in ("SKILL.md", "manifest.json", "README.md", "LICENSE",
                "run.py"):
        assert (root / rel).is_file(), f"{skill} missing {rel}"


def test_lib_carries_the_logic():
    """lib/chelate_core must exist and hold the real implementations."""
    assert LIB_DIR.is_dir(), "lib/chelate_core/ missing"
    for module, floor in CORE_MODULES.items():
        path = LIB_DIR / module
        assert path.is_file(), f"lib/chelate_core/{module} missing"
        n = len(path.read_text(encoding="utf-8").splitlines())
        assert n >= floor, \
            f"lib/chelate_core/{module} too thin ({n} < {floor} lines)"


def test_skill_folders_hold_no_duplicate_core_logic():
    """No skill folder may define its own copy of a core function name
    that already exists in lib/chelate_core (anti copy-paste guard)."""
    import ast
    lib_defs = set()
    for f in _python_files(LIB_DIR):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                lib_defs.add(node.name)
    assert lib_defs, "no functions found in lib/chelate_core"
    # names that must never be redefined inside a skill folder
    protected = {d for d in lib_defs
                 if d in ("profile_csv", "verify_doi", "extract_dois",
                          "search", "extract", "normalize", "merge_verdict",
                          "load_config", "run_legacy", "dispatch")}
    assert protected, "expected core entry points not found in lib/"
    for skill in NEW_SKILLS:
        for f in _python_files(SKILLS_DIR / skill):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in protected:
                    pytest.fail(
                        f"{f.relative_to(SKILLS_DIR)} redefines {node.name}() "
                        f"— it belongs to lib/chelate_core")


# ---------------------------------------------------------------------------
# uniform adapter CLI contract
# ---------------------------------------------------------------------------

def test_every_adapter_exposes_root_and_action():
    import subprocess
    import sys
    for skill in ALL_SKILLS:
        proc = subprocess.run(
            [sys.executable, str(SKILLS_DIR / skill / "run.py"), "--help"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, \
            f"{skill} --help failed: {proc.stderr[-300:]}"
        assert "--root" in proc.stdout and "--action" in proc.stdout, \
            f"{skill} adapter does not expose the uniform --root/--action contract"


def test_adapters_accept_generic_stage_actions():
    """The Router passes generic stage actions (gate/ingest/process/
    workspace); every adapter must map them onto its default action
    instead of failing with 'unknown action'."""
    import subprocess
    import sys
    from conftest import STAGE_OF
    generic = {"workspace": "workspace", "ingest": "ingest",
               "gates": "gate", "processors": "process"}
    for skill in ALL_SKILLS:
        action = generic[STAGE_OF[skill]]
        proc = subprocess.run(
            [sys.executable, str(SKILLS_DIR / skill / "run.py"),
             "--root", ".", "--action", action],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
        out = proc.stdout + proc.stderr
        assert "unknown action" not in out, \
            f"{skill} rejected the generic stage action {action!r}: {out[-300:]}"
