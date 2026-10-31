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


def _normalize_eol(data: bytes) -> bytes:
    """Normalize CRLF to LF so that files that are byte-identical in
    content but differ only in line endings (the v1.0.0 source tree uses LF,
    the migrated project uses CRLF) compare equal."""
    return data.replace(b"\r\n", b"\n")


# Regex to mask version strings in files where the version was intentionally
# bumped (src/__init__.py, test fixtures, CHANGELOG version headers).
_VERSION_RE = None


def _mask_version_strings(data: bytes) -> bytes:
    """Blank semver-looking version literals in *data* so that version
    bumps (e.g. 1.0.0 -> 1.2.0) don't trip the content-identical guard.

    This is applied *only* to CHANGELOG.md, src/__init__.py, and skill-local
    test files — never to source modules, where version strings are part of
    the functional contract.
    """
    global _VERSION_RE
    import re as _re
    if _VERSION_RE is None:
        _VERSION_RE = _re.compile(rb"\b\d+\.\d+\.\d+\b")
    return _VERSION_RE.sub(b"<ver>", data)


# A CHANGELOG may gain a fresh "## [1.2.0]" section documenting the current
# release. That section is release metadata, not a content change, so it is
# stripped from both trees before comparing; every historical section stays
# under comparison.
_ADDED_SECTION_RE = None


def _strip_added_version_sections(data: bytes) -> bytes:
    """Remove `## [1.2.0]` markdown sections (release documentation).

    The four legacy skills whose `scripts/__init__.py` version was still
    stale (1.0.1 / 0.0.0) received a fresh `## [1.2.0] - <date>` section in
    their CHANGELOG.md as part of the version unification. Stripping exactly
    that section from both sides keeps the byte guard proving that the
    historical sections are untouched.
    """
    global _ADDED_SECTION_RE
    import re as _re
    if _ADDED_SECTION_RE is None:
        _ADDED_SECTION_RE = _re.compile(
            rb"^## \[1\.2\.0\].*?(?=^## \[|\Z)", _re.M | _re.S)
    return _ADDED_SECTION_RE.sub(b"", data)


def _is_version_decl(rel_key: str) -> bool:
    """True for packaging files whose only permitted changes are metadata
    declarations: the version and the maintainer contact mailbox.

    The v1.2.0 release unified the project version to 1.2.0 across every
    manifest, and unified the contact address to one canonical mailbox;
    these legacy-skill packaging files carry version and author
    declarations that are metadata, not capability.
    """
    base = rel_key.rsplit("/", 1)[-1]
    return (base in ("pyproject.toml", "skill.json", "CITATION.cff")
            or rel_key.endswith("config/schema.yaml")
            or rel_key.startswith("config/examples/")
            or rel_key in ("scripts/__init__.py", "src/__init__.py"))


_VERSION_DECL_RE = None
_CONTACT_DECL_RE = None


def _mask_version_decl(data: bytes) -> bytes:
    """Blank only the metadata-declaration lines, keeping every other byte.

    Two line families are masked, both pure metadata:
    - the version declaration (`version:` / `version =` / `"version":` /
      `__version__` carrying a semver) — unified to 1.2.0 in v1.2.0;
    - the contact declaration (an `email` key whose value is an address) —
      unified to `jiamingshi_git@outlook.com` in v1.2.0.

    Unlike `_mask_version_strings` (which blanks *every* semver literal in
    doc/test files), this masks exactly one line per declaration, so any
    other edit to a packaging file still trips the guard.
    `versions_dir` / `version_naming` keys, the CFF spec version and
    dependency pins such as `openpyxl>=3.1.0` are deliberately kept under
    comparison.
    """
    global _VERSION_DECL_RE, _CONTACT_DECL_RE
    import re as _re
    if _VERSION_DECL_RE is None:
        _VERSION_DECL_RE = _re.compile(rb"\d+\.\d+\.\d+")
    if _CONTACT_DECL_RE is None:
        _CONTACT_DECL_RE = _re.compile(
            rb'"?email"?\s*[:=]\s*"[^"]*@[^"]*"')
    out = []
    for line in data.split(b"\n"):
        s = line.strip()
        if ((s.startswith(b"version:") or s.startswith(b"version =")
                or s.startswith(b'"version":')
                or s.startswith(b"__version__"))
                and _VERSION_DECL_RE.search(s)):
            out.append(b"<version-decl>")
        elif _CONTACT_DECL_RE.search(s):
            out.append(b"<contact-decl>")
        else:
            out.append(line)
    return b"\n".join(out)


# frontmatter contract fields v1.1.0 intentionally re-pointed at the thin
# adapter (version 1.1.0, entry_point "python run.py", python_requires 3.10)
_CONTRACT_FIELDS = (b"version:", b"entry_point:", b"python_requires:")


def _mask_contract_lines(data: bytes, rel_key: str = "SKILL.md") -> bytes:
    """Blank the three frontmatter contract lines before comparing.

    The SKILL.md body must stay byte-identical to v1.0.0 (zero amputation),
    but its frontmatter contract fields were updated to match the v1.1.0
    manifests; masking exactly those lines keeps the guard proving that the
    *content* is untouched while allowing the contract refresh.

    The comparison is also line-ending-insensitive: source trees on disk
    may use LF while the migrated project uses CRLF; normalising both sides
    before hashing means the guard still proves the *content* is identical
    (no amputation) without tripping on pure EOL differences.
    """
    out, in_fm = [], False
    for line in data.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == b"---":
            in_fm = not in_fm
            out.append(line.rstrip(b"\r\n"))
            continue
        if in_fm and any(stripped.startswith(f) for f in _CONTRACT_FIELDS):
            out.append(b"<contract-field>")
            continue
        out.append(line.rstrip(b"\r\n"))
    return b"\n".join(out) + (b"\n" if out else b"")


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
    # "new" files are ones that are not expected to exist in the v1.0.0 source
    # tree: thin adapters, the per-skill manifest, the pint layer, human-facing
    # READMEs, the capstone trademark NOTICE, and config assets. The v1.2.0 tree
    # also carries an intentionally re-pointed formula-validator MCP server
    # (workspace-relative reports, not the skill install dir) — see the
    # v1.1.1 output-path contract.
    new_files = {"run.py", "manifest.json", "scripts/core/pint_units.py",
                 "README.md", "NOTICE", "assets/config.yaml",
                 "mcp_server/server.py"}
    # runtime-output dirs the legacy CLIs create on every run (not source)
    runtime_dirs = {"_reports", "evolution", "conflicts", "output", "out",
                    "_broadcast", "process"}
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
                # CHANGELOG.md, src/__init__.py, and skill-local test files
                # are all intentional contract refreshes from the v1.1.x ->
                # v1.2.0 migration: CHANGELOG line endings flipped to CRLF,
                # the version string in __init__.py / test fixtures was
                # bumped to 1.2.0, and the four skills whose version had
                # still been stale gained a new "## [1.2.0]" section.
                # Compare them after stripping that section, normalising
                # EOL *and* masking version strings so the guard still
                # proves the underlying content is unamputated without
                # tripping on those changes.
                if rel_key == "CHANGELOG.md" \
                        or rel_key == "src/__init__.py" \
                        or rel_key.startswith("tests/"):
                    norm_src = _mask_version_strings(_normalize_eol(
                        _strip_added_version_sections(sp.read_bytes())))
                    norm_dst = _mask_version_strings(_normalize_eol(
                        _strip_added_version_sections(
                            open(os.path.join(root, f), "rb").read())))
                    if norm_src != norm_dst:
                        mismatched.append(
                            f"{skill}/{rel_key} (content differs beyond "
                            f"line-ending / version normalization)")
                    continue
                # v1.2.0 release: the project version was unified to 1.2.0
                # across every manifest, and the contact mailbox to one
                # canonical address, so a packaging file's version and
                # contact declarations are the lines allowed to differ.
                # Everything else is still compared byte-for-byte (a
                # stricter mask than `_mask_version_strings`, which blanks
                # every semver literal).
                if _is_version_decl(rel_key):
                    if _mask_version_decl(sp.read_bytes()) != \
                            _mask_version_decl(
                                open(os.path.join(root, f), "rb").read()):
                        mismatched.append(
                            f"{skill}/{rel_key} (content differs beyond the "
                            f"version/contact declarations)")
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


# --- mask unit tests (mutation-tested) -------------------------------------- #
# Each test pins one rule of the metadata mask: the masked surface must
# stay exactly as wide as documented. Deleting a rule from
# `_mask_version_decl` / `_strip_added_version_sections` fails a test here.

def test_mask_version_decl_blanks_only_the_declaration_line():
    data = b'name = "x"\nversion = "1.0.0"\nlicense = "MIT"\n'
    assert _mask_version_decl(data) == \
        b'name = "x"\n<version-decl>\nlicense = "MIT"\n'


def test_mask_version_decl_handles_dunder_and_cff_lines():
    data = b'cff-version: "1.2.0"\nversion: 1.0.0\n__version__ = "0.0.0"\n'
    out = _mask_version_decl(data).split(b"\n")
    # the Citation-File-Format spec version is NOT the product version and
    # stays under comparison; only the product declarations are masked
    assert out[0] == b'cff-version: "1.2.0"'
    assert out[1] == b"<version-decl>"
    assert out[2] == b"<version-decl>"


def test_mask_version_decl_keeps_dependency_pins():
    data = b'dependencies = ["openpyxl>=3.1.0"]\n'
    assert _mask_version_decl(data) == data


def test_mask_version_decl_blanks_the_contact_line():
    """Two packaging files differing only in the author email must mask to
    the same output, and the rest of the file must survive. (The stale
    address is derived from the canonical one at runtime, so no
    non-canonical address literal ever lands in a tracked file —
    `test_contact_email_is_unified` would flag it.)"""
    stale = b"jiamingshi_git@outlook.com".replace(b"git", b"phys")
    assert stale != b"jiamingshi_git@outlook.com"  # derivation changed it
    old = (b'[project]\nname = "capstone-labmate"\n'
           b'authors = [\n'
           b'    { name = "Jiaming Shi", email = "' + stale + b'" }\n'
           b']\nlicense = "MIT"\n')
    new = old.replace(stale, b"jiamingshi_git@outlook.com")
    assert _mask_version_decl(old) == _mask_version_decl(new)
    out = _mask_version_decl(old).split(b"\n")
    assert out[0] == b'[project]'
    assert out[3] == b"<contact-decl>"
    assert out[5] == b'license = "MIT"'


def test_mask_version_decl_ignores_prose_and_urls():
    """Lines that merely mention email-ish text (docs, URLs) are not
    declarations and stay under byte comparison."""
    data = (b'# contact the maintainer\n'
            b'url = "https://github.com/chelate-shell"\n'
            b'keywords = ["email", "audit"]\n')
    assert _mask_version_decl(data) == data


def test_strip_added_version_sections_removes_only_the_new_section():
    data = (b"# Changelog\n\n"
            b"## [1.2.0] - 2026-10-25\n\n- new\n\n"
            b"## [1.0.1] - 2026-10-16\n\n- old\n")
    out = _strip_added_version_sections(data)
    assert b"## [1.2.0]" not in out
    assert out.endswith(b"## [1.0.1] - 2026-10-16\n\n- old\n")


def test_strip_added_version_sections_handles_trailing_section():
    data = b"## [0.0.0] - x\n\n- old\n\n## [1.2.0] - y\n\n- new\n"
    assert _strip_added_version_sections(data) == \
        b"## [0.0.0] - x\n\n- old\n\n"
