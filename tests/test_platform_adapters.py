"""Cross-platform rule-file adapters.

Besides the four plugin manifests (`.claude-plugin`, `.codebuddy-plugin`,
`.codex-plugin`, `.dsh-plugin`), the repo ships one agent-facing rule file per
mainstream host so the orchestrator contract reaches agents that only read
their own rules directory. These files are documentation for the host agent,
not executable code, but they must exist and stay pinned to the shipped
version and the real entry points.

Caller: pytest only. No other file imports this module.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads(
    (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
)["version"]

ADAPTER_FILES = [
    "AGENTS.md",
    ".cursor/rules/chelate-shell.mdc",
    ".windsurf/rules/chelate-shell.md",
    ".clinerules/chelate-shell.md",
    ".roo/rules/chelate-shell.md",
    ".continue/rules/chelate-shell.md",
    ".github/copilot-instructions.md",
]


@pytest.mark.parametrize("rel", ADAPTER_FILES)
def test_adapter_file_exists_and_pins_version(rel):
    path = REPO_ROOT / rel
    assert path.is_file(), f"missing platform adapter: {rel}"
    text = path.read_text(encoding="utf-8")
    assert VERSION in text, f"{rel} does not mention the shipped version {VERSION}"


@pytest.mark.parametrize("rel", ADAPTER_FILES)
def test_adapter_file_points_at_real_entry_points(rel):
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "cli.py" in text, f"{rel} must mention the CLI entry point"
    assert "ORCHESTRATOR.md" in text, f"{rel} must point at the full contract"
    assert "task-organizer" in text, f"{rel} must mention the workspace entry skill"
