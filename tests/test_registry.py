"""Registry tests: flat scan of skills/, manifest schema validation."""
from __future__ import annotations

import json

import pytest

from conftest import (ALL_SKILLS, NEW_SKILLS, ROUTED_SKILLS, SKELETON_SKILLS,
                      REPO_ROOT, SKILLS_DIR, STAGE_OF, skill_root)
from core.registry import Registry, validate_manifest

STAGES = {"workspace", "ingest", "gates", "processors",
          "infrastructure", "generation", "domain_extensions"}


def test_all_routed_skills_registered():
    """All routed skills ship an entrypoint and must register. (The three
    former skeleton skills — quantitative-validator, ml-auditor,
    latex-exporter — graduated in v1.2.0, so there are no skeleton errors
    left. v1.3.0 adds security-guard, which declares stage=infrastructure.)"""
    reg = Registry().scan(str(SKILLS_DIR))
    assert reg.names() == sorted(ROUTED_SKILLS)
    assert len(reg) == 19
    # any residual skeleton would be reported, not silently dropped
    reported = " ".join(reg.errors)
    for s in SKELETON_SKILLS:
        assert f"{s}\\manifest.json: entrypoint not found" in reported, \
            f"{s} should be reported as a skeleton error"


def test_physical_flatness_no_nested_manifests():
    # Every manifest is a direct child of skills/: skills/<skill>/manifest.json.
    # A namespace folder in between is invisible to the host skill scanners
    # (Claude Code, Codex), so the layout is enforced here rather than merely
    # described in the docs.
    for p in SKILLS_DIR.rglob("manifest.json"):
        depth = len(p.relative_to(SKILLS_DIR).parts) - 1
        assert depth == 1, f"manifest is not a direct child of skills/: {p}"
    # no stray files directly in skills/ (only skill directories)
    for child in SKILLS_DIR.iterdir():
        assert child.is_dir(), f"stray file in skills/: {child}"


def test_registry_rejects_a_nested_manifest(tmp_path):
    """A manifest below skills/<x>/<skill>/ is reported, not silently loaded.

    Guards the failure mode this layout caused: the registry and the host
    disagreeing about the skill count, where one sees 20 and the other 17.
    """
    nested = tmp_path / "layer" / "ghost-skill"
    nested.mkdir(parents=True)
    (nested / "manifest.json").write_text("{}", encoding="utf-8")
    reg = Registry().scan(str(tmp_path))
    assert reg.names() == []
    assert any("exactly one level under skills/" in e for e in reg.errors), \
        reg.errors


@pytest.mark.parametrize("name", ALL_SKILLS)
def test_manifest_contract(name):
    data = json.loads((skill_root(name) / "manifest.json")
                      .read_text(encoding="utf-8"))
    assert validate_manifest(data) == []
    assert data["name"] == name
    assert data["stage"] == STAGE_OF[name]
    assert data["stage"] in STAGES
    entrypoint = data["entrypoint"]
    assert entrypoint.endswith("run.py"), entrypoint
    # Skeleton skills ship manifest + SKILL.md but not the entrypoint yet.
    if name not in SKELETON_SKILLS:
        assert (skill_root(name) / entrypoint).is_file(), \
            f"{name}: entrypoint {entrypoint} not found"
    assert isinstance(data["input_types"], list) and data["input_types"]
    assert isinstance(data["dependencies"], list)
    assert data["description"].strip()


def test_manifest_rejects_legacy_and_bad_fields():
    good = {"name": "x", "version": "1.1.0", "stage": "gates",
            "input_types": ["csv"], "output_type": "gate_result",
            "dependencies": [], "entrypoint": "run.py",
            "description": "d"}
    assert validate_manifest(good) == []
    # old single-value field must not come back
    assert validate_manifest(dict(good, input_type="csv"))
    assert validate_manifest(dict(good, stage="03_gates"))
    assert validate_manifest(dict(good, namespace="core"))
    assert validate_manifest({k: v for k, v in good.items()
                              if k != "output_type"})
    assert validate_manifest(dict(good, input_types="csv"))  # not a list
    assert validate_manifest(dict(good, version=1.1))  # not a string


def test_stage_partition_matches_blueprint():
    reg = Registry().scan(str(SKILLS_DIR))
    assert sorted(r.name for r in reg.by_stage("ingest")) == [
        "bibtex-normalizer", "fulltext-extractor",
        "literature-retriever", "video-tracker"]
    assert sorted(r.name for r in reg.by_stage("gates")) == [
        "conflict-detector", "data-profiler", "formula-validator",
        "longitudinal-analysis", "ml-auditor", "quantitative-validator",
        "reference-auditor"]
    assert sorted(r.name for r in reg.by_stage("processors")) == [
        "ai-trace-remover", "latex-exporter"]
    assert sorted(r.name for r in reg.by_stage("workspace")) == [
        "document-evolution-tracker", "multi-dim-manager",
        "task-organizer"]


def test_input_type_routing():
    reg = Registry().scan(str(SKILLS_DIR))
    assert "fulltext-extractor" in [r.name for r in reg.by_input("pdf")]
    assert "reference-auditor" in [r.name for r in reg.by_input("doi")]
    assert "formula-validator" in [r.name for r in reg.by_input("latex_string")]
    assert reg.by_input("no-such-type") == []


def test_new_skill_dependencies_declared():
    reg = Registry().scan(str(SKILLS_DIR))
    expected = {
        "fulltext-extractor": "pypdf", "literature-retriever": "arxiv",
        "bibtex-normalizer": "bibtexparser", "reference-auditor": "requests",
        "data-profiler": "pandas",
    }
    for name, dep in expected.items():
        assert dep in reg.get(name).dependencies


def test_skill_md_present_for_every_skill():
    missing = [n for n in ALL_SKILLS
               if not (skill_root(n) / "SKILL.md").is_file()]
    assert missing == []


def test_repo_layout_top_level():
    for item in ("core", "contracts", "skills", "tests", "cli.py",
                 "bootstrap.py"):
        assert (REPO_ROOT / item).exists(), f"missing top-level {item}"
