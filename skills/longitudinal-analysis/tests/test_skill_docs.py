"""Contract tests for the longitudinal-analysis skill.

Covers the version consistency contract (SKILL.md frontmatter version ==
``src/__init__.__version__`` == CHANGELOG entry), CRLF line endings on the
changelog, and the pure-English / zero-CJK README invariant that every
shipped skill must satisfy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"
CN_MD = SKILL_DIR / "README_zh.md"
CHANGELOG_MD = SKILL_DIR / "CHANGELOG.md"
README_MD = SKILL_DIR / "README.md"


def _frontmatter_value(text: str, key: str) -> str | None:
    """Return the scalar value of a top-level frontmatter key."""
    m = re.search(rf"^\s{{0,2}}{re.escape(key)}:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip().strip('"').strip() if m else None


def test_version_consistency() -> None:
    """SKILL.md version must equal the package __version__."""
    from src import __version__

    fm_text = SKILL_MD.read_text(encoding="utf-8")
    assert _frontmatter_value(fm_text, "version") == __version__
    # Pinned to the manifest, not to a literal: a release bump must not break
    # this test (it did in 1.3.1 — the assert still said 1.3.0).
    manifest = json.loads((SKILL_DIR / "manifest.json").read_text(encoding="utf-8"))
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
    """README.md must be zero-CJK except the navigation line."""
    text = README_MD.read_text(encoding="utf-8")
    nav = "[中文说明](README_zh.md)"
    body = text.replace(nav, "")
    cjk = [ch for ch in body if "\u4e00" <= ch <= "\u9fff"]
    assert not cjk, f"README.md contains CJK: {cjk[:5]}"


def test_changelog_has_version_entry() -> None:
    """CHANGELOG.md must contain a [1.0.0] entry."""
    text = CHANGELOG_MD.read_text(encoding="utf-8")
    assert "## [1.0.0]" in text
