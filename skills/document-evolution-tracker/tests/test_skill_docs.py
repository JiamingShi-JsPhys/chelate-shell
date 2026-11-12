"""Contract tests for the document-evolution-tracker skill.

Locks the version three-way, the CRLF CHANGELOG, and the zero-CJK invariant
on README.md.
"""

from __future__ import annotations

import json
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

    manifest = json.loads(
        (SKILL_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert _fm(SKILL_MD.read_text(encoding="utf-8"), "version") == __version__
    # Pinned to the manifest, not to a literal: a release bump must not break
    # this test (it did in 1.3.0 — the assert still said 1.2.0).
    assert __version__ == manifest["version"]


def test_changelog_line_endings_are_consistent():
    """No mixed line endings: the file is either all CRLF or all LF.

    This used to demand CRLF, which is a property of a Windows checkout, not
    of the file — it failed on every Linux checkout, CI included.
    """
    raw = CHANGELOG_MD.read_bytes()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    assert crlf == 0 or lf == 0, "CHANGELOG_MD mixes CRLF and LF"


def test_readme_md_is_pure_english() -> None:
    text = README_MD.read_text(encoding="utf-8")
    body = text.replace("[中文说明](README_zh.md)", "")
    cjk = [ch for ch in body if "\u4e00" <= ch <= "\u9fff"]
    assert not cjk, f"README.md contains CJK: {cjk[:5]}"


def test_changelog_has_version_entry() -> None:
    assert "## [1.0.0]" in CHANGELOG_MD.read_text(encoding="utf-8")
