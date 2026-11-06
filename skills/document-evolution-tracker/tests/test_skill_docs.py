"""Contract tests for the document-evolution-tracker skill.

Locks the version three-way, the CRLF CHANGELOG, and the zero-CJK invariant
on README.md.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"
CHANGELOG_MD = SKILL_DIR / "CHANGELOG.md"
README_MD = SKILL_DIR / "README.md"


def _fm(text: str, key: str) -> str | None:
    m = re.search(rf"^\s{{0,2}}{re.escape(key)}:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip().strip('"') if m else None


def test_version_consistency() -> None:
    from src import __version__

    assert _fm(SKILL_MD.read_text(encoding="utf-8"), "version") == __version__
    assert __version__ == "1.2.0"


def test_changelog_is_crlf() -> None:
    raw = CHANGELOG_MD.read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b""), "CHANGELOG.md must be CRLF"
    assert b"\r\n" in raw


def test_readme_md_is_pure_english() -> None:
    text = README_MD.read_text(encoding="utf-8")
    body = text.replace("[中文说明](README_zh.md)", "")
    cjk = [ch for ch in body if "\u4e00" <= ch <= "\u9fff"]
    assert not cjk, f"README.md contains CJK: {cjk[:5]}"


def test_changelog_has_version_entry() -> None:
    assert "## [1.0.0]" in CHANGELOG_MD.read_text(encoding="utf-8")
