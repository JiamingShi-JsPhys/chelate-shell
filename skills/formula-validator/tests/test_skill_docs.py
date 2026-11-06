"""Contract tests.

These lock the wording that the rest of the package and the release process
depend on. Changing a sentence here should be a deliberate act, so the tests
assert on key phrases rather than whole blocks of prose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import ROOT

SKILL = ROOT / "SKILL.md"
README = ROOT / "README.md"
CN_DOC = ROOT / "README_zh.md"
CHANGELOG = ROOT / "CHANGELOG.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing required file: {path.name}"
    return path.read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    assert m, "SKILL.md has no YAML frontmatter"
    return m.group(1)


def _description() -> str:
    m = re.search(r"^description:\s*>\s*\n((?:[ \t]+.*\n?)+)",
                  _frontmatter(_read(SKILL)), re.M)
    assert m, "no block description in frontmatter"
    return " ".join(m.group(1).split())


def _cjk(text: str) -> list[str]:
    return sorted({c for c in text if any((
        "\u4e00" <= c <= "\u9fff",      # CJK unified ideographs
        "\u3000" <= c <= "\u303f",      # CJK punctuation, including ，。
        "\uff00" <= c <= "\uffef",      # fullwidth forms
    ))})


def test_skill_readme_has_no_cjk():
    text = _read(README)
    # The only permitted CJK is the navigation link to the Chinese README, which
    # must sit at the very top of the English README.
    nav = "[English](README.md) · [中文说明](README_zh.md)"
    assert text.lstrip().startswith(nav), "README must begin with the bilingual nav link"
    body = text.replace(nav, "")
    bad = _cjk(body)
    assert not bad, f"the skill README must stay free of CJK (nav link exempted): {bad!r}"


def test_skill_readme_has_no_version_marker():
    found = re.findall(r"\bv?\d+\.\d+\.\d+\b", _read(README))
    assert not found, f"version numbers belong in frontmatter and CHANGELOG: {found}"


def test_description_states_general_trigger_principle():
    d = _description()
    assert "not exhaustive" in d, "description must disclaim the example words"
    assert "no keyword list can enumerate them all" in d
    assert "independent of how" in d, "description must block the veto dimension"


def test_description_has_no_cjk():
    assert not _cjk(_description()), "description is read by the router; keep it clean"


def test_skill_frontmatter_name_matches_directory():
    m = re.search(r"^name:\s*(\S+)", _frontmatter(_read(SKILL)), re.M)
    assert m and m.group(1) == ROOT.name


def test_version_is_consistent_between_skill_and_source():
    from scripts import __version__

    m = re.search(r"^version:\s*(\S+)", _frontmatter(_read(SKILL)), re.M)
    assert m, "SKILL.md frontmatter has no version"
    assert m.group(1) == __version__, (
        f"SKILL.md says {m.group(1)} but scripts/__init__.py says {__version__}")


def test_changelog_documents_current_version():
    from scripts import __version__

    text = _read(CHANGELOG)
    assert f"[{__version__}]" in text, (
        f"CHANGELOG has no section for the current version {__version__}")


def test_changelog_uses_crlf_line_endings():
    raw = CHANGELOG.read_bytes()
    orphan = raw.replace(b"\r\n", b"").count(b"\n")
    assert orphan == 0, (
        f"{orphan} LF-only line(s) in CHANGELOG; keep it CRLF or git shows a "
        "whole-file diff")


def test_changelog_keeps_a_not_claimed_section():
    assert "Not claimed" in _read(CHANGELOG)


def test_chinese_doc_keeps_locked_phrases():
    text = _read(CN_DOC)
    for phrase in ("量纲", "断点", "极限", "已知局限", "蒙特卡洛", "定义式"):
        assert phrase in text, f"中文文档缺少锁定短语: {phrase}"


def test_skill_body_is_action_oriented():
    body = _read(SKILL)
    assert "## Execution steps" in body
    assert "## Hard constraints" in body
    assert "scripts/cli.py" in body, "the body must name the script to run"


def test_readme_has_a_limitations_section():
    assert "## Limitations" in _read(README)


def test_readme_test_count_matches_this_suite():
    """The advertised count must not drift from what pytest actually collects."""
    import subprocess
    import sys

    m = re.search(r"^- (\d+) cases", _read(README), re.M)
    assert m, "README must state the test count"
    advertised = int(m.group(1))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    tail = [ln for ln in proc.stdout.strip().splitlines() if "test" in ln.lower()]
    collected = 0
    for line in tail:
        m2 = re.match(r"^(\d+) tests? collected", line)
        if m2:
            collected = int(m2.group(1))
    if collected == 0:  # pytest not installed or collection unavailable
        pytest.skip("could not determine the collected test count")
    assert advertised == collected, (
        f"README advertises {advertised} cases but pytest collects {collected}")


def test_skill_md_states_that_the_model_does_not_compute():
    """The one design rule the project exists to hold.

    If this sentence is ever removed from SKILL.md, a future contributor has
    no signal that adding a model-side arithmetic path is forbidden.
    """
    text = _read(SKILL)
    assert re.search(r"never compute the algebra yourself", text, re.I), (
        "SKILL.md no longer carries the hard constraint that the language "
        "model must not compute the algebra itself; that is the load-bearing "
        "rule of this skill")


def test_contributing_documents_the_same_rule():
    text = _read(ROOT / "CONTRIBUTING.md")
    assert re.search(r"model (is a translator|does not compute)", text, re.I), (
        "CONTRIBUTING.md must repeat the rule so a contributor cannot miss it")


def test_release_assets_are_not_committed():
    """The release zip is uploaded, not version-controlled."""
    gi = _read(ROOT / ".gitignore")
    assert "_reports/" in gi and ".pytest_cache/" in gi


def test_no_document_references_another_skill():
    """Every skill in this repository is independent.

    The first release shipped a protocol, a specification, and tests for
    talking to a group-theory skill that does not exist, and named it in the
    MCP tool description. This test makes that class of mistake impossible to
    reintroduce quietly: no document shipped with this skill may name another
    skill or advertise an integration with one.
    """
    shipped = [
        SKILL, README, CN_DOC, CHANGELOG,
        ROOT / "CONTRIBUTING.md",
        ROOT / "mcp_server" / "README.md",
    ]
    sibling = re.compile(r"Js_(?!formula-validator)[a-z]")
    for path in shipped:
        text = _read(path)
        low = text.lower()
        for word in ("bridge", "partner", "fv-bridge"):
            assert word not in low, (
                f"{path.name} uses {word!r}; this skill is standalone and "
                "must not reference or integrate with any other skill")
        m = sibling.search(text)
        assert m is None, (
            f"{path.name} names another skill ({m.group(0)!r}); this skill "
            "is standalone")
