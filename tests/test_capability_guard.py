"""Capability guard: every legacy skill keeps its full module inventory.

These tests are the anti-amputation guard for the v1.1.0 migration: each
legacy skill's key modules must import and expose the named functions, and
every migrated file must stay byte-identical to the v1.0.0 source tree
(when that tree is available on disk). See docs/FILE_FUNCTION_MAP.md.
"""
from __future__ import annotations

import hashlib
import os

import pytest

from conftest import LEGACY_SKILLS, SKILLS_DIR, run_in_skill

# (module, [required top-level names]) per skill, expressed as subprocess code
INVENTORY = {
    "task-organizer": [
        ("scripts.init", ["init_folder", "write_config_template", "InitResult"]),
        ("scripts.organize", ["organize_folder", "move_directory", "OrganizeResult"]),
        ("scripts.broadcast", ["broadcast", "local_keywords", "BroadcastResult"]),
        ("scripts.run", ["run_from_cli"]),
    ],
    "multi-dim-manager": [
        ("scripts.param_space", ["expand", "load_space", "ParamSpace"]),
        ("scripts.executor", ["run_plugin", "ExecutionResult"]),
        ("scripts.run", ["main"]),
    ],
    "document-evolution-tracker": [
        ("src.diff_blocks", ["split_blocks", "BlockDiff"]),
        ("src.lineage", ["build_lineage", "LineageNode"]),
        ("src.versioning", []),
        ("src.cli", ["main"]),
    ],
    "capstone-labmate": [
        ("_capx", ["extract_datasets", "parse_main_xml", "open_cap_zip",
                   "build_time_axis", "extract_document_text"]),
        ("process_cap", ["run", "main"]),
        ("draft_report", ["main"]),
    ],
    "video-tracker": [
        ("scripts.fft_analyzer", ["compute_spectrum", "SpectrumResult"]),
        ("scripts.physics", ["score_trajectory", "teleport_metric",
                             "conservation_score", "fit_reconstruct"]),
        ("scripts.tracker", ["TrajectoryPoint", "ObjectResult"]),
        ("scripts.data_export", []),
        ("scripts.run", ["main"]),
    ],
    "longitudinal-analysis": [
        ("src.steps.descriptive", ["run"]),
        ("src.steps.lmm", ["run"]),
        ("src.steps.mediation", ["run"]),
        ("src.steps.sensitivity", ["run"]),
        ("src.r_runner", []),
        ("src.cli", ["main"]),
    ],
    "formula-validator": [
        ("scripts.core.dimensions", ["check_equation", "analyse"]),
        ("scripts.core.limits", ["find_singularities"]),
        ("scripts.core.numeric", ["sample_values"]),
        ("scripts.core.symbolic", ["prove_identity",
                                   "high_precision_check"]),
        ("scripts.core.matrixprops", []),
        ("scripts.core.pint_units", ["check_equation_units",
                                     "expression_dimensionality"]),
        ("scripts.core.pipeline", ["validate_equation",
                                   "inspect_expression"]),
        ("scripts.cli", ["main"]),
    ],
    "ai-trace-remover": [
        ("src.core.engine", ["scan", "TraceReport", "grade_zh", "grade_en"]),
        ("src.core.patterns_en", ["ENPattern"]),
        ("src.core.patterns_zh", []),
        ("src.core.hard_bans", []),
        ("src.core.sound_rules", []),
        ("src.cli", ["main"]),
    ],
    "conflict-detector": [
        ("src.rules", ["run_detection", "pair_facts"]),
        ("src.cli", ["main"]),
    ],
}

@pytest.mark.parametrize("skill", LEGACY_SKILLS)
def test_legacy_key_functions_exist(skill):
    """Import each key module in an isolated subprocess and assert names."""
    for module, names in INVENTORY[skill]:
        code = (
            "import importlib, json, sys\n"
            f"missing = []\n"
            f"try:\n"
            f"    mod = importlib.import_module({module!r})\n"
            f"except Exception as exc:\n"
            f"    print(json.dumps({{'ok': False, 'error': repr(exc)}}))\n"
            f"    sys.exit(0)\n"
            f"for n in {names!r}:\n"
            f"    if not hasattr(mod, n):\n"
            f"        missing.append(n)\n"
            f"print(json.dumps({{'ok': not missing, 'missing': missing}}))\n"
        )
        out = run_in_skill(skill, code, timeout=120)
        assert out["ok"], f"{skill}:{module} missing {out.get('missing')} " \
                          f"error={out.get('error')}"


def test_r_scripts_migrated():
    for script in ("lmm.R", "mediation.R"):
        p = SKILLS_DIR / "longitudinal-analysis" / "R" / script
        assert p.is_file() and p.stat().st_size > 0


def test_capstone_templates_and_configs_migrated():
    root = SKILLS_DIR / "capstone-labmate"
    assert (root / "assets" / "blank.base.cap").is_file()
    assert any((root / "templates").glob("*.md")) or \
        any((root / "templates").glob("*.txt"))


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# frontmatter contract fields v1.1.0 intentionally re-pointed at the thin
# adapter (version 1.1.0, entry_point "python run.py", python_requires 3.10)
_CONTRACT_FIELDS = (b"version:", b"entry_point:", b"python_requires:")


def _mask_contract_lines(data: bytes) -> bytes:
    """Blank out the three contract lines inside the frontmatter block.

    The SKILL.md body must stay byte-identical to v1.0.0 (zero amputation),
    but its frontmatter contract fields were updated to match the v1.1.0
    manifests; masking exactly those lines keeps the guard proving that the
    *content* is untouched while allowing the contract refresh.
    """
    out, in_fm = [], False
    for line in data.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == b"---":
            in_fm = not in_fm
            out.append(line)
            continue
        if in_fm and any(stripped.startswith(f) for f in _CONTRACT_FIELDS):
            eol = b"\r\n" if line.endswith(b"\r\n") else b"\n"
            out.append(b"<contract-field>" + eol)
            continue
        out.append(line)
    return b"".join(out)


def test_migrated_files_byte_identical_to_v1_source():
    """Zero-amputation proof: every carried-over file matches the source.

    SKILL.md bodies must stay byte-identical to v1.0.0; only the three
    frontmatter contract fields (version / entry_point / python_requires)
    were re-pointed at the v1.1.0 thin adapter, and those lines are masked
    before hashing (see `_mask_contract_lines`). The frontmatter-to-manifest
    agreement itself is enforced in `tests/test_plugin_manifests.py`.
    """
    source_root = SKILLS_DIR.parent.parent / "chelate-shell-main" / "skills"
    if not source_root.is_dir():
        pytest.skip("v1.0.0 source tree not present on this machine")
    # files that are new in v1.1.0 by design (adapter, manifest, pint layer,
    # human-facing README, capstone trademark NOTICE, new-skill config assets)
    new_files = {"run.py", "manifest.json", "scripts/core/pint_units.py",
                 "README.md", "NOTICE", "assets/config.yaml"}
    # runtime-output dirs the legacy CLIs create on every run (not source)
    runtime_dirs = {"_reports", "evolution", "conflicts", "output", "out",
                    "_broadcast"}
    mismatched, checked = [], 0
    for skill in LEGACY_SKILLS:
        src, dst = source_root / skill, SKILLS_DIR / skill
        for root, dirs, files in os.walk(dst):
            # __pycache__/.pytest_cache are build caches; test_workspace is
            # a user scratch workspace (never part of the source tree)
            dirs[:] = [d for d in dirs if d not in ("__pycache__",
                                                    ".pytest_cache",
                                                    "test_workspace")]
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), dst)
                rel_key = rel.replace(os.sep, "/")
                if rel_key in new_files or rel_key.split("/")[0] \
                        in runtime_dirs:
                    continue
                sp = src / rel
                if not sp.is_file():
                    mismatched.append(f"{skill}/{rel_key} (not in source)")
                    continue
                checked += 1
                if rel_key == "SKILL.md":
                    # body must be byte-identical; only the three contract
                    # fields may differ (masked before comparing)
                    dst_bytes = open(os.path.join(root, f), "rb").read()
                    if _mask_contract_lines(sp.read_bytes()) != \
                            _mask_contract_lines(dst_bytes):
                        mismatched.append(
                            f"{skill}/{rel_key} (body differs beyond the "
                            f"contract fields)")
                    continue
                if _sha(sp) != _sha(os.path.join(root, f)):
                    mismatched.append(f"{skill}/{rel_key} (content differs)")
    assert checked > 200, f"only {checked} files compared — walk failed?"
    assert mismatched == [], f"files changed during migration: {mismatched}"


def test_no_python_file_lost():
    """File count parity with the documented 179-file inventory."""
    total = sum(
        1 for skill in LEGACY_SKILLS
        for root, dirs, files in os.walk(SKILLS_DIR / skill)
        for f in files
        if f.endswith(".py") and "__pycache__" not in root
    )
    # 179 legacy files + 9 new run.py adapters + 1 pint_units.py
    assert total == 179 + 9 + 1, f"expected 189 py files, found {total}"
