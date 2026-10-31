"""Repo-wide consistency guard: the 18 skills stay organized.

The SEM module and the three graduated heavy skills each landed as separate
pieces of work. This suite is the anti-drift net that keeps the whole
`skills/` tree coherent as one unit, and it encodes the conventions that
the READMEs state in prose:

1. every skill ships the same surface (`SKILL.md`, `README.md`, `LICENSE`,
   `manifest.json`);
2. `SKILL.md` frontmatter agrees with `manifest.json` (name / version /
   entry_point) — the same rule `test_plugin_manifests.py` enforces for
   host manifests;
3. the declared `entrypoint` actually exists on disk;
4. all 18 `LICENSE` files are the same MIT text (whitespace-normalised, so
   a re-wrap of the boilerplate is not a false positive);
5. no stub markers in the human/AI-facing docs;
6. the dependency tables in `README.md` **and** `README_zh.md` agree with
   each skill's `manifest.json` `dependencies` — this is the check that
   catches a doc claiming a dependency the manifest does not declare (the
   `pandoc` / `cleanlab` drift that survived several releases), and a
   manifest dependency no doc mentions;
7. every contact address in the tree is the one canonical mailbox — the
   `jiamingshi_physics@` spelling that sat in `capstone-labmate`'s
   packaging while the rest of the repo used `jiamingshi_git@` survived
   two releases because nothing compared the two.

Run:  python -m pytest tests/test_repo_consistency.py -q
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from conftest import SKILLS_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_VERSION = "1.2.0"
CANONICAL_CONTACT_EMAIL = "jiamingshi_git@outlook.com"
ALLOWED_STAGES = {"workspace", "ingest", "gates", "processors"}

SURFACE_FILES = ("SKILL.md", "README.md", "LICENSE", "manifest.json")

STUB_MARKERS = (
    (re.compile(r"^\s*TODO\b"), "TODO marker"),
    (re.compile(r"^\s*FIXME\b"), "FIXME marker"),
    (re.compile(r"^\s*XXX\b"), "XXX marker"),
    (re.compile(r"^\s*NotImplementedError"), "NotImplementedError"),
    (re.compile(r"^\s*\.\.\.\s*$"), "bare ellipsis body"),
)

# ---------------------------------------------------------------- helpers

def _tracked_files():
    """Repo-relative paths of every file worth scanning.

    Uses `git ls-files` when the tree is a git checkout, and falls back to a
    recursive walk (honouring `.gitignore`'s coarse rules) when it is a plain
    source drop — the distributed ZIP and the working copies under
    `Deepseek Harness/` have no `.git` metadata.
    """
    try:
        proc = subprocess.run(["git", "ls-files"], capture_output=True,
                              text=True, cwd=REPO_ROOT)
        if proc.returncode == 0:
            return proc.stdout.splitlines()
    except OSError:
        pass
    skip_dirs = {".git", "__pycache__", ".pytest_cache", "process", "results",
                 "_broadcast", "_reports", ".benchmarks", "test_workspace"}
    out = []
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(REPO_ROOT)
        if any(part in skip_dirs for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return sorted(out)


def _skill_dirs():
    return sorted(p for p in SKILLS_DIR.iterdir()
                  if p.is_dir() and (p / "manifest.json").is_file())


def _manifest(skill_dir: Path) -> dict:
    return json.loads((skill_dir / "manifest.json").read_text(encoding="utf-8"))


def _frontmatter(skill_dir: Path) -> dict:
    """Flatten a SKILL.md frontmatter into one dict.

    Top-level keys (`name`, `description`) and the nested `metadata:` block
    share no key names, so a flat merge is unambiguous: every line that
    names a key is recorded, regardless of indent. YAML block scalars
    (`description: >` / `|`) are the one exception — their indented
    continuation lines are joined into the value, not treated as keys.
    """
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)[1]
    out: dict = {}
    pending_block = None
    block_lines: list = []
    for line in block.splitlines():
        if pending_block is not None:
            if line.startswith(" "):
                block_lines.append(line.strip())
                continue
            out[pending_block] = " ".join(block_lines)
            pending_block = None
            block_lines = []
        if not line.strip():
            continue
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value in (">", "|"):
            pending_block = key
        else:
            out[key] = value.strip().strip("'\"")
    if pending_block is not None:
        out[pending_block] = " ".join(block_lines)
    return out


def _norm_ws(text: str) -> str:
    return " ".join(text.split())


# README display name -> manifest dependency name. Everything else must
# match verbatim (case-insensitive).
_DEP_ALIASES = {
    "opencv": "cv2",
    "opencv-python": "cv2",
    "scikit-learn": "scikit-learn",
}

# Tokens that legitimately appear in a docs table but are never a Python
# manifest dependency (R toolchain, optional exporters).
_DISPLAY_ONLY = {"r", "rscript", "lme4", "lavaan", "python-docx"}


def _is_no_dep_cell(cell: str) -> bool:
    c = _norm_ws(cell).strip("`* ").lower()
    return (c in {"", "无", "none", "-", "—", "–"}
            or "stdlib only" in c
            or "纯标准库" in c)


def _parse_required(cell: str) -> list:
    """Extract the required dependencies from one table cell.

    Returns a list of *alternative groups*: `,` separates conjuncts (every
    group must be satisfied) and `/` separates alternatives inside a group
    (`pdfminer.six / pypdf` means "either backend"). An empty list means the
    skill declares no required dependency.
    """
    if _is_no_dep_cell(cell):
        return []
    cleaned = re.sub(r"\([^)]*\)", " ", cell)      # drop "(lme4/lavaan)"
    groups = []
    for part in re.split(r"[,，、]", cleaned):
        alts = set()
        for raw in re.split(r"/", part):
            tok = raw.strip().strip("`* ").lower()
            if not tok or tok in _DISPLAY_ONLY:
                continue
            alts.add(_DEP_ALIASES.get(tok, tok))
        if alts:
            groups.append(frozenset(alts))
    return groups


def _parse_dep_table(text: str) -> dict:
    """skill name -> {'required': set, 'row': str} from a README table."""
    rows = {}
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        skills_cell = cells[0]
        if skills_cell.lower().startswith(("skill", "技能", "---")):
            continue
        if set(skills_cell) <= set("-: "):
            continue
        names = []
        for chunk in re.split(r"[,，]", skills_cell):
            name = re.sub(r"\*\(.*?\)\*", "", chunk).strip().strip("`* ")
            if name:
                names.append(name)
        required = _parse_required(cells[1])
        for name in names:
            rows[name] = {"required": required, "row": line}
    return rows

# ---------------------------------------------------------------- tests

def test_every_skill_ships_the_full_surface():
    dirs = _skill_dirs()
    assert len(dirs) == 18, f"expected 18 skills, found {len(dirs)}"
    missing = {d.name: f for d in dirs for f in SURFACE_FILES
               if not (d / f).is_file()}
    assert not missing, f"skills missing surface files: {missing}"


def test_versions_are_unified():
    """Every skill version declaration reads EXPECTED_VERSION.

    The v1.2.0 release unified the project version across every manifest,
    but earlier passes only walked `manifest.json` / `SKILL.md`; a 2026-10-25
    audit found `scripts/__init__.py` (1.0.1 / 0.0.0), `CITATION.cff`
    (1.0.0), and `config/examples/` schema versions (1.0.0) still stale.
    This test now walks every declaration surface so a future bump cannot
    silently miss one again.
    """
    drift = {}
    for d in _skill_dirs():
        name = d.name
        if _manifest(d).get("version") != EXPECTED_VERSION:
            drift[f"{name}/manifest.json"] = _manifest(d).get("version")
        fm_ver = _frontmatter(d).get("version")
        if fm_ver != EXPECTED_VERSION:
            drift[f"{name}/SKILL.md"] = fm_ver
        for init in ("scripts/__init__.py", "src/__init__.py"):
            p = d / init
            if p.is_file():
                m = re.search(r'__version__\s*=\s*"([^"]+)"',
                              p.read_text(encoding="utf-8"))
                if not m or m.group(1) != EXPECTED_VERSION:
                    drift[f"{name}/{init}"] = m.group(1) if m else None
        cff = d / "CITATION.cff"
        if cff.is_file():
            m = re.search(r"^version:\s*(\S+)",
                          cff.read_text(encoding="utf-8"), re.M)
            if not m or m.group(1) != EXPECTED_VERSION:
                drift[f"{name}/CITATION.cff"] = m.group(1) if m else None
        for cfg in sorted((d / "config" / "examples").glob("*")):
            if not cfg.is_file():
                continue
            text = cfg.read_text(encoding="utf-8")
            if cfg.suffix == ".json":
                try:
                    ver = json.loads(text).get("version")
                except json.JSONDecodeError:
                    ver = None
            else:
                m = re.search(r"^version:\s*(\S+)", text, re.M)
                ver = m.group(1) if m else None
            if ver is not None and ver != EXPECTED_VERSION:
                drift[f"{name}/config/examples/{cfg.name}"] = ver
    assert not drift, f"version drift: {drift}"


def test_changelog_documents_the_current_version():
    """Every skill that ships a CHANGELOG documents the current release.

    This is the repo-wide form of the per-skill "version three-way"
    convention (manifest/SKILL.md == `__init__.__version__` == newest
    CHANGELOG section) that the legacy skill-internal tests encode.
    """
    missing = {}
    for d in _skill_dirs():
        cl = d / "CHANGELOG.md"
        if cl.is_file() and f"[{EXPECTED_VERSION}]" not in \
                cl.read_text(encoding="utf-8"):
            missing[d.name] = "no current-version section"
    assert not missing, \
        f"CHANGELOG missing [{EXPECTED_VERSION}]: {missing}"


def test_host_manifests_and_lib_declare_the_same_version():
    """package.json, the four dot-plugin manifests, and the live version
    strings in `lib/` (Crossref user agent, .bib output header) all read
    EXPECTED_VERSION. The `lib/` strings ship to the outside world, so a
    stale one misreports the release to Crossref and to every .bib header.
    """
    drift = {}
    pkg = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    if pkg.get("version") != EXPECTED_VERSION:
        drift["package.json"] = pkg.get("version")
    for plug in (".claude-plugin", ".codebuddy-plugin", ".codex-plugin",
                 ".dsh-plugin"):
        pj = REPO_ROOT / plug / "plugin.json"
        if pj.is_file():
            v = json.loads(pj.read_text(encoding="utf-8")).get("version")
            if v != EXPECTED_VERSION:
                drift[f"{plug}/plugin.json"] = v
        mj = REPO_ROOT / plug / "marketplace.json"
        if mj.is_file():
            for entry in json.loads(mj.read_text(
                    encoding="utf-8")).get("plugins", []):
                # the version field is mandatory on every marketplace entry
                # (the Claude Code marketplace schema defines it), so a
                # missing one counts as drift just like a stale one
                if entry.get("version") != EXPECTED_VERSION:
                    drift[f"{plug}/marketplace.json"] = \
                        entry.get("version")
    lib = REPO_ROOT / "lib" / "chelate_core"
    ua = (lib / "doi_audit.py").read_text(encoding="utf-8")
    m = re.search(r'USER_AGENT\s*=\s*"chelate-shell/([^"]+)"', ua)
    if not m or m.group(1) != EXPECTED_VERSION:
        drift["lib/chelate_core/doi_audit.py"] = m.group(1) if m else None
    bib = (lib / "bibtex_norm.py").read_text(encoding="utf-8")
    m = re.search(r"bibtex-normalizer v([0-9][0-9A-Za-z.\-+]*)", bib)
    if not m or m.group(1) != EXPECTED_VERSION:
        drift["lib/chelate_core/bibtex_norm.py"] = m.group(1) if m else None
    assert not drift, f"version drift: {drift}"


def test_stages_are_valid():
    bad = {d.name: _manifest(d).get("stage") for d in _skill_dirs()
           if _manifest(d).get("stage") not in ALLOWED_STAGES}
    assert not bad, f"invalid stage: {bad}"


def test_sandbox_required_is_a_boolean():
    bad = {d.name: _manifest(d).get("sandbox_required") for d in _skill_dirs()
           if not isinstance(_manifest(d).get("sandbox_required"), bool)}
    assert not bad, f"sandbox_required must be a bool: {bad}"


def test_declared_entrypoint_exists():
    missing = {}
    for d in _skill_dirs():
        ep = _manifest(d).get("entrypoint")
        if not ep or not (d / ep).is_file():
            missing[d.name] = ep
    assert not missing, f"entrypoint missing on disk: {missing}"


def test_entrypoint_is_one_of_the_two_documented_layouts():
    """Adapter skills use `run.py`; engine skills use `scripts/run.py`."""
    bad = {}
    for d in _skill_dirs():
        ep = _manifest(d).get("entrypoint")
        if ep not in ("run.py", "scripts/run.py"):
            bad[d.name] = ep
    assert not bad, f"undeclared entrypoint layout: {bad}"


def test_skillmd_frontmatter_agrees_with_manifest():
    problems = {}
    for d in _skill_dirs():
        m, fm = _manifest(d), _frontmatter(d)
        issues = []
        if fm.get("name") != m.get("name"):
            issues.append(f"name {fm.get('name')!r} != {m.get('name')!r}")
        if fm.get("version") != m.get("version"):
            issues.append(f"version {fm.get('version')!r} != {m.get('version')!r}")
        md_ep = (fm.get("entry_point") or "").replace("python ", "").strip()
        if md_ep and md_ep != m.get("entrypoint"):
            issues.append(f"entry_point {md_ep!r} != {m.get('entrypoint')!r}")
        if issues:
            problems[d.name] = issues
    assert not problems, f"frontmatter/manifest drift: {problems}"


def test_skillmd_has_a_quick_execution_block():
    """Every SKILL.md the project owns carries a Quick Execution block — the
    one-line call template that keeps the invoking AI from burning tokens on
    the source tree.

    The nine legacy trees are exempt: their SKILL.md bodies are byte-frozen
    by the zero-amputation red line (tests/test_capability_guard.py), so the
    block cannot be back-ported into them without breaking that guard.
    """
    from conftest import LEGACY_SKILLS
    missing = [d.name for d in _skill_dirs()
               if d.name not in LEGACY_SKILLS
               and "quick execution" not in
               (d / "SKILL.md").read_text(encoding="utf-8").lower()]
    assert not missing, f"SKILL.md without a Quick Execution block: {missing}"


def test_licenses_are_the_same_mit_text():
    texts = {}
    for d in _skill_dirs():
        raw = (d / "LICENSE").read_text(encoding="utf-8")
        assert "MIT License" in raw, f"{d.name}/LICENSE is not MIT"
        assert "Jiaming Shi" in raw, f"{d.name}/LICENSE lost the author line"
        texts[d.name] = _norm_ws(raw)
    distinct = set(texts.values())
    assert len(distinct) == 1, (
        "LICENSE files diverged (whitespace-normalised): "
        + ", ".join(sorted(k for k, v in texts.items()
                           if v != next(iter(distinct)))))


def test_no_stub_markers_in_skill_docs():
    hits = []
    for d in _skill_dirs():
        for doc in ("SKILL.md", "README.md"):
            for i, line in enumerate(
                    (d / doc).read_text(encoding="utf-8").splitlines(), 1):
                for pat, label in STUB_MARKERS:
                    if pat.search(line):
                        hits.append(f"{d.name}/{doc}:{i} ({label})")
    assert not hits, f"stub markers in skill docs: {hits}"


# ----------------------------------------------- dependency table parity

# The per-skill dependency matrix moved out of the README into docs/
# DEPENDENCIES*.md; the parity guarantee now covers those two files.
@pytest.mark.parametrize("doc", ["docs/DEPENDENCIES.md",
                                 "docs/DEPENDENCIES_zh.md"])
def test_readme_dep_tables_cover_every_skill(doc):
    table = _parse_dep_table((REPO_ROOT / doc).read_text(encoding="utf-8"))
    listed = set(table)
    expected = {d.name for d in _skill_dirs()}
    assert listed >= expected, (
        f"{doc}: skills absent from the dependency table: "
        f"{sorted(expected - listed)}")


# The per-skill dependency matrix moved out of the README into docs/
# DEPENDENCIES*.md; the parity guarantee now covers those two files.
@pytest.mark.parametrize("doc", ["docs/DEPENDENCIES.md",
                                 "docs/DEPENDENCIES_zh.md"])
def test_manifest_dependencies_are_documented(doc):
    """Every manifest dependency must be mentioned in the skill's table row
    (the `cv2`/`opencv` alias is the only tolerated spelling difference)."""
    table = _parse_dep_table((REPO_ROOT / doc).read_text(encoding="utf-8"))
    display = {"cv2": ("cv2", "opencv")}
    problems = {}
    for d in _skill_dirs():
        row = table.get(d.name)
        if row is None:
            continue  # covered by the coverage test above
        hay = row["row"].lower()
        for dep in _manifest(d).get("dependencies", []):
            forms = display.get(dep, (dep,))
            if not any(f in hay for f in forms):
                problems.setdefault(d.name, []).append(dep)
    assert not problems, f"{doc}: manifest deps not documented: {problems}"


# The per-skill dependency matrix moved out of the README into docs/
# DEPENDENCIES*.md; the parity guarantee now covers those two files.
@pytest.mark.parametrize("doc", ["docs/DEPENDENCIES.md",
                                 "docs/DEPENDENCIES_zh.md"])
def test_documented_required_deps_match_the_manifest(doc):
    """The reverse direction: a required dependency claimed in the table
    must actually be declared in the manifest. This is what caught
    `latex-exporter | pandoc` and `ml-auditor | cleanlab, ...`."""
    table = _parse_dep_table((REPO_ROOT / doc).read_text(encoding="utf-8"))
    problems = {}
    for d in _skill_dirs():
        row = table.get(d.name)
        if row is None:
            continue
        declared = {dep.lower() for dep in _manifest(d).get("dependencies", [])}
        unsatisfied = [
            "/".join(sorted(group))
            for group in row["required"]
            if not (group & declared)
        ]
        if unsatisfied:
            problems[d.name] = unsatisfied
    assert not problems, (
        f"{doc}: table claims required deps the manifest does not declare: "
        f"{problems}")


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Addresses that are deliberately *not* the maintainer's mailbox:
# RFC 2606/6761 reserved domains used as placeholders, and the upstream
# projects' own contacts listed in the third-party license inventory.
_PLACEHOLDER_DOMAINS = ("example.com", "example.invalid")


def test_contact_email_is_unified():
    """Every real contact address in the tree is CANONICAL_CONTACT_EMAIL.

    The `jiamingshi_physics@` spelling sat in `capstone-labmate`'s
    packaging while the other twelve surfaces used `jiamingshi_git@`;
    nothing compared them, so the drift survived two releases. Placeholder
    addresses on reserved domains (`you@example.com` in CONTRIBUTING.md,
    the Crossref politeness mailbox `chelate-shell@example.invalid`) and
    the third-party license inventory are exempt by design.

    CHANGELOGs are exempt too: they are historical records and must stay
    free to quote the superseded spelling when documenting the fix (the
    version-uniformity test likewise never inspects changelogs).
    """
    tracked = _tracked_files()
    offenders = {}
    for rel in tracked:
        if rel.startswith("THIRD_PARTY_LICENSES"):
            continue
        if rel == "CHANGELOG.md" or rel.endswith("/CHANGELOG.md"):
            continue  # historical record — may quote superseded values
        p = REPO_ROOT / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue  # binary (figures, .cap fixtures, ...)
        for addr in _EMAIL_RE.findall(text):
            domain = addr.rsplit("@", 1)[1].lower()
            if domain in _PLACEHOLDER_DOMAINS:
                continue
            if addr != CANONICAL_CONTACT_EMAIL:
                offenders.setdefault(addr, []).append(rel)
    assert not offenders, (
        f"contact addresses that are not {CANONICAL_CONTACT_EMAIL}: "
        + "; ".join(
            f"{addr} (in {', '.join(sorted(set(files)))})"
            for addr, files in sorted(offenders.items())))
