"""Registry tests: flat scan of skills/, manifest schema validation."""
from __future__ import annotations

import json

import pytest

from conftest import ALL_SKILLS, NEW_SKILLS, REPO_ROOT, SKILLS_DIR, STAGE_OF
from core.registry import Registry, validate_manifest

STAGES = {"workspace", "ingest", "gates", "processors"}


def test_all_fourteen_skills_registered():
    reg = Registry().scan(str(SKILLS_DIR))
    assert reg.names() == sorted(ALL_SKILLS)
    assert len(reg) == 14
    assert reg.errors == []


def test_physical_flatness_no_nested_manifests():
    # every manifest must sit exactly one level below skills/
    nested = [p for p in SKILLS_DIR.rglob("manifest.json")
              if p.parent.parent != SKILLS_DIR]
    assert nested == [], f"nested manifests violate flat layout: {nested}"
    # no category folders such as namespaces/ or 03_gates/
    for child in SKILLS_DIR.iterdir():
        assert child.is_dir(), f"stray file in skills/: {child}"


@pytest.mark.parametrize("name", ALL_SKILLS)
def test_manifest_contract(name):
    data = json.loads((SKILLS_DIR / name / "manifest.json")
                      .read_text(encoding="utf-8"))
    assert validate_manifest(data) == []
    assert data["name"] == name
    assert data["stage"] == STAGE_OF[name]
    assert data["stage"] in STAGES
    assert data["entrypoint"] == "run.py"
    assert (SKILLS_DIR / name / "run.py").is_file()
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
        "bibtex-normalizer", "capstone-labmate", "fulltext-extractor",
        "literature-retriever", "video-tracker"]
    assert sorted(r.name for r in reg.by_stage("gates")) == [
        "conflict-detector", "data-profiler", "formula-validator",
        "longitudinal-analysis", "reference-auditor"]
    assert sorted(r.name for r in reg.by_stage("processors")) == [
        "ai-trace-remover"]
    assert sorted(r.name for r in reg.by_stage("workspace")) == [
        "document-evolution-tracker", "multi-dim-manager", "task-organizer"]


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
               if not (SKILLS_DIR / n / "SKILL.md").is_file()]
    assert missing == []


def test_repo_layout_top_level():
    for item in ("core", "contracts", "skills", "tests", "cli.py",
                 "bootstrap.py"):
        assert (REPO_ROOT / item).exists(), f"missing top-level {item}"
