"""Documentation contract tests for multi-dim-manager.

These guard the conventions the agent-skills repository enforces: bilingual
READMEs, zero-CJK English README, version tri-consistency, CRLF changelog, and
self-containment (no references to sibling skills).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "multi-dim-manager"
NAV_LINE = "[English](README.md) · [中文说明](README_zh.md)"

README = ROOT / "README.md"
README_ZH = ROOT / "README_zh.md"
SKILL = ROOT / "SKILL.md"
CHANGELOG = ROOT / "CHANGELOG.md"
INIT = ROOT / "scripts" / "__init__.py"
GITIGNORE = ROOT / ".gitignore"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _has_cjk(text: str) -> bool:
    return any(
        ("\u4e00" <= ch <= "\u9fff")
        or ("\u3000" <= ch <= "\u303f")
        or ("\uff00" <= ch <= "\uffef")
        for ch in text
    )


def _frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    block = text[3:end]
    out = {}
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def _collected_test_count() -> int:
    count = 0
    for f in (ROOT / "tests").glob("test_*.py"):
        count += len(re.findall(r"^\s*def test_", f.read_text(encoding="utf-8"), re.M))
    return count


# --- README.md conventions ------------------------------------------------- #
def test_readme_has_nav_link():
    assert NAV_LINE in _read(README)


def test_readme_is_zero_cjk_except_nav():
    for line in _read(README).splitlines():
        if line.strip() == NAV_LINE:
            continue
        assert not _has_cjk(line), f"README.md contains CJK: {line!r}"


def test_readme_has_no_version_number():
    # The English README must not advertise a semantic version.
    assert not re.search(r"\d+\.\d+\.\d+", _read(README))


def test_readme_has_limitations():
    assert "## Limitations" in _read(README)


def test_readme_test_count_matches():
    m = re.search(r"covers (\d+) cases", _read(README))
    assert m, "README must state 'covers N cases'"
    assert int(m.group(1)) == _collected_test_count()


# --- README_zh.md conventions ----------------------------------------------- #
def test_readme_zh_has_nav_link():
    assert _read(README_ZH).splitlines()[0].strip() == NAV_LINE


def test_readme_zh_locked_phrases():
    text = _read(README_ZH)
    for phrase in ("快照", "回滚", "审计", "关键路径", "非破坏性"):
        assert phrase in text, f"README_zh.md missing locked phrase {phrase!r}"


# --- SKILL.md conventions -------------------------------------------------- #
def test_skill_frontmatter_name_matches_dir():
    fm = _frontmatter(_read(SKILL))
    assert fm.get("name") == SKILL_NAME


def test_skill_has_mandatory_workflow():
    assert "MANDATORY WORKFLOW" in _read(SKILL)


def test_skill_body_action_oriented():
    assert "Never compute the result yourself" in _read(SKILL)


def test_skill_no_cross_skill_references():
    text = _read(SKILL) + _read(README) + _read(README_ZH)
    for name in ("task-organizer", "formula-validator"):
        assert name not in text, f"cross-skill reference to {name!r} is forbidden"


# --- Version tri-consistency ------------------------------------------------ #
def test_version_consistency():
    fm = _frontmatter(_read(SKILL))
    skill_ver = fm.get("version")
    init_ver = re.search(r'__version__\s*=\s*"([^"]+)"', _read(INIT)).group(1)
    assert skill_ver == init_ver, "SKILL.md version != scripts/__init__.__version__"
    assert re.search(rf"\[{re.escape(skill_ver)}\]", _read(CHANGELOG)), \
        "CHANGELOG must document the version"


def test_changelog_is_crlf():
    data = CHANGELOG.read_bytes()
    assert b"\r\n" in data
    # After removing CRLF sequences, no bare LF should remain.
    assert b"\n" not in data.replace(b"\r\n", b"")


# --- Release hygiene ------------------------------------------------------- #
def test_release_assets_gitignored():
    text = _read(GITIGNORE)
    assert "output/" in text
