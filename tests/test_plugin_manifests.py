"""Plugin manifest contract tests.

The four per-platform plugin manifests (`.claude-plugin`, `.codebuddy-plugin`,
`.codex-plugin`, `.dsh-plugin`) are what each host platform reads when it loads
the plugin. Claude Code validates them strictly: `author` must be an object
with a `name`, and a string `skills` field (or a broken `icon` URL) makes the
whole plugin silently ignored. These tests lock in the corrected shape so a
future edit cannot regress into the v1.0.0 failure mode again.

Data schemas:
    Reads:  .claude-plugin/*.json, .codebuddy-plugin/*.json,
            .codex-plugin/*.json, .dsh-plugin/*, package.json,
            skills/<skill>/manifest.json (version source of truth).
Caller: pytest only. No other file imports this module.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import REPO_ROOT, SKILLS_DIR  # noqa: E402

PLUGIN_DIRS = {
    "claude": REPO_ROOT / ".claude-plugin",
    "codebuddy": REPO_ROOT / ".codebuddy-plugin",
    "codex": REPO_ROOT / ".codex-plugin",
    "dsh": REPO_ROOT / ".dsh-plugin",
}
# hosts whose plugin.json follows the Claude Code contract
CLAUDE_STYLE = ("claude", "codebuddy", "codex")


def _load(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _skill_version() -> str:
    """The single source of truth: every skill manifest must agree."""
    versions = set()
    for manifest in sorted(SKILLS_DIR.glob("*/manifest.json")):
        versions.add(_load(manifest)["version"])
    assert len(versions) == 1, f"skill manifests disagree on version: {versions}"
    return versions.pop()


def test_plugin_directories_exist_for_every_platform():
    for platform, path in PLUGIN_DIRS.items():
        assert path.is_dir(), f"missing plugin dir for {platform}: {path}"


@pytest.mark.parametrize("platform", CLAUDE_STYLE)
def test_claude_style_plugin_json_contract(platform):
    """author must be an object; skills must be omitted (auto-scan)."""
    data = _load(PLUGIN_DIRS[platform] / "plugin.json")
    assert data["name"] == "chelate-shell"
    assert data["version"] == _skill_version()
    assert isinstance(data["description"], str) and data["description"]

    author = data.get("author")
    assert isinstance(author, dict), (
        f"{platform}: author must be an object, got {type(author).__name__}")
    assert isinstance(author.get("name"), str) and author["name"].strip()

    # a string "skills" field is what got the plugin silently rejected in
    # v1.0.0 — the skills/ directory is auto-scanned, so the field must stay
    # absent (or be a list of strings, which we deliberately do not use)
    assert "skills" not in data, (
        f"{platform}: omit 'skills' so the host auto-scans skills/")
    # icon was the second rejection cause; keep it out of plugin.json
    assert "icon" not in data


def test_codex_interface_block_is_intact():
    data = _load(PLUGIN_DIRS["codex"] / "plugin.json")
    interface = data.get("interface")
    assert isinstance(interface, dict)
    assert interface["displayName"] == "Chelate Shell"
    assert interface["category"] == "Developer Tools"


def test_dsh_plugin_json_points_at_a_real_entry():
    data = _load(PLUGIN_DIRS["dsh"] / "plugin.json")
    assert data["name"] == "chelate-shell"
    assert data["version"] == _skill_version()
    main = data.get("main")
    assert main, "dsh plugin.json must declare main"
    assert (PLUGIN_DIRS["dsh"] / main).is_file()


@pytest.mark.parametrize("platform", ["claude", "codebuddy", "codex"])
def test_marketplace_json_describes_the_plugin(platform):
    data = _load(PLUGIN_DIRS[platform] / "marketplace.json")
    plugins = data.get("plugins")
    assert isinstance(plugins, list) and plugins
    entry = plugins[0]
    assert entry["name"] == "chelate-shell"
    assert entry["source"] == "./"
    # marketplace version, when present, must track the skill manifests
    if "version" in entry:
        assert entry["version"] == _skill_version()
    owner = data.get("owner")
    if owner is not None:
        assert isinstance(owner.get("name"), str) and owner["name"]


def test_dsh_cjs_entries_export_name_and_apply():
    for path in (PLUGIN_DIRS["dsh"] / "index.js", REPO_ROOT / "index.js"):
        assert path.is_file(), f"missing CJS entry: {path}"
        text = path.read_text(encoding="utf-8")
        assert "name" in text and "apply" in text


def test_package_json_version_matches_skills():
    data = _load(REPO_ROOT / "package.json")
    assert data["name"] == "chelate-shell"
    assert data["version"] == _skill_version()
    assert (REPO_ROOT / "cordis.patch.yml").is_file()


def test_icon_asset_present():
    icon = REPO_ROOT / "assets" / "icon.png"
    assert icon.is_file() and icon.stat().st_size > 0


def test_orchestrator_doc_describes_v11_layout():
    doc = (REPO_ROOT / "ORCHESTRATOR.md").read_text(encoding="utf-8")
    assert "v1.1.0" in doc
    assert "14" in doc  # skill count
    for stage in ("workspace", "ingest", "gates", "processors"):
        assert stage in doc
    for skill in ("task-organizer", "ai-trace-remover", "reference-auditor"):
        assert skill in doc


def _frontmatter(skill: str) -> dict:
    """Parse the SKILL.md YAML frontmatter (flat key: value lines only).

    Supports one nesting level: a valueless top-level key (e.g. `metadata:`)
    starts a block whose two-space-indented lines become its entries.
    """
    text = (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---"), f"{skill}: SKILL.md has no frontmatter"
    block = text.split("---", 2)[1]
    out: dict = {}
    current = out
    for line in block.splitlines():
        if not line.strip():
            continue
        if line.startswith(" "):
            # nested line (e.g. "  version: 1.1.0") under the current block
            assert current is not out, f"{skill}: unexpected indent: {line!r}"
            key, _, value = line.strip().partition(":")
            current[key.strip()] = value.strip().strip("'")
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value:
            out[key] = value
            current = out
        else:
            out[key] = {}
            current = out[key]
    return out


def test_skill_md_frontmatter_matches_manifest():
    """SKILL.md contract fields must agree with the machine-read manifest.

    The nine legacy skills shipped stale frontmatter in v1.0.0 (versions
    like 1.0.0-beta, entry points pointing at CLIs the Router never calls,
    python_requires 3.9 while the repo declares 3.10+). v1.1.0 re-points
    them at the thin adapter; this test keeps the two surfaces in sync.
    """
    for manifest_path in sorted(SKILLS_DIR.glob("*/manifest.json")):
        skill = manifest_path.parent.name
        manifest = _load(manifest_path)
        fm = _frontmatter(skill)
        assert fm["name"] == manifest["name"], skill
        assert fm["metadata"]["version"] == manifest["version"], \
            f"{skill}: SKILL.md version {fm['metadata']['version']} != " \
            f"manifest {manifest['version']}"
        assert fm["metadata"]["entry_point"] == \
            f"python {manifest['entrypoint']}", \
            f"{skill}: SKILL.md entry_point must point at the adapter"
        assert fm["metadata"]["python_requires"] == ">=3.10", \
            f"{skill}: python_requires must match the repo-wide 3.10+ floor"


def test_all_skills_declare_python_floor_310():
    """One Python floor across the whole tree (README states 3.10+)."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Python 3.10+" in readme
    for manifest_path in sorted(SKILLS_DIR.glob("*/manifest.json")):
        skill = manifest_path.parent.name
        fm = _frontmatter(skill)
        assert fm["metadata"]["python_requires"] == ">=3.10", skill
