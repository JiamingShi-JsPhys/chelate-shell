"""Tests for the skill documentation contract.

regression guard: SKILL.md used to be pure reference material, so an
agent triggered by the skill could answer with a *description* of the tool
instead of *running* it, and a request with no explicit path ("set up a task
workspace") had no defined behaviour - nothing happened, no folder was
created. The mandatory workflow section is what makes the skill act; these
tests keep it from silently disappearing again.

guard (folder-signal trigger + broadcast center): referencing a folder
and starting a task on it did not trigger the skill either, because the
description only claimed explicit organize intents. The workflow now opens
with a folder-signal check that PROPOSES one init and waits for
confirmation; these tests keep the propose-first semantics from silently
disappearing again. This release integrates the broadcast center
(context-compression index), guarded below.
"""

from pathlib import Path

from scripts import __version__

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
CN_MD = SKILL_DIR / "README_zh.md"
CHANGELOG_MD = SKILL_DIR / "CHANGELOG.md"


def _frontmatter_value(text: str, key: str):
    # key may appear at column 0 (top-level) or indented under metadata:
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(f"{key}:"):
            indent = len(line) - len(stripped)
            if indent <= 2:  # top-level or one-level indent (metadata block)
                return stripped.split(":", 1)[1].strip().strip('"')
    return None


def _description() -> str:
    """The frontmatter `description`, joined when it is a `>` block scalar.

    v1.3 writes the description as a folded block, so a naive `key: value`
    split returns ">" and every content assertion would fail for the wrong
    reason.
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    fm = text.split("---", 2)[1]
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("description:"):
            value = line.split(":", 1)[1].strip()
            if value not in (">", "|"):
                return value
            block = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt.startswith(" "):
                    break
                block.append(nxt.strip())
            return " ".join(block)
    return ""


class TestSkillDocs:
    """The documentation is part of the product - guard it."""

    def test_frontmatter_version_matches_package(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert _frontmatter_value(text, "version") == __version__

    def test_mandatory_workflow_present_and_first(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # v1.3 renamed "MANDATORY WORKFLOW" to "Quick Execution"; the section
        # must still come before the reference material, so an agent reads
        # "what to do" before "what the tool is".
        assert "## Quick Execution" in text
        assert text.index("## Quick Execution") < text.index("## When to use")

    def test_workflow_covers_the_pathless_request(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        flat = " ".join(text.split())  # SKILL.md is hard-wrapped
        # "set up a task workspace" with no path must have a defined action:
        # a folder that was merely referenced gets exactly one proposal
        assert "merely referenced" in flat
        assert "propose it once and wait for a yes" in flat

    def test_workflow_forbids_description_only_reply(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "failure mode, not a result" in text
        assert "Act, do not summarize" in text

    def test_workflow_covers_both_entry_points(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "`init`" in text
        assert "`organize`" in text
        assert "mark-downloaded" in text

    def test_description_claims_folder_signal_trigger(self):
        desc = _description()
        # "folder referenced / attached + task start" is a trigger class
        assert "named or attached" in desc
        assert "work starts inside it" in desc
        # ...and its semantics are propose-first, not act-first
        assert "proposes `init` once" in desc
        assert "never reorganizes one uninvited" in desc

    def test_workflow_opens_with_session_start_structure_check(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        flat = " ".join(text.split())  # SKILL.md is hard-wrapped
        # the session-start structure check (doctor) runs before anything that
        # changes the folder, because it changes nothing itself
        assert "Run it before asking the user anything" in flat
        assert "read-only and always safe" in flat
        assert flat.index("read-only and always safe") < flat.index(
            "propose it once and wait for a yes")

    def test_session_start_check_is_always_on(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # the "every conversation starts tidy" rule is in the always-on list
        assert "At session start on a known task folder" in text
        # the check is cheap and repairs nothing when the folder is healthy
        assert "writes nothing" in text

    def test_workflow_proposal_has_example_and_decline_path(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # a declined proposal ends the proposing, it does not stall the task
        assert "declined the `init` proposal" in text
        assert "at most one proposal per folder" in text

    def test_content_production_runs_directly_no_proposal(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # the proposal gate is scoped to a merely referenced folder: an
        # explicit "produce this deliverable" request runs directly
        assert "when the folder was merely referenced" in text
        assert "Act, do not summarize" in text

    def test_chinese_doc_has_the_workflow(self):
        text = CN_MD.read_text(encoding="utf-8")
        # The workflow is folded into the core-features section as a brief
        # note (repository structure: design principles & core features ->
        # download and install -> quick start -> the rest); the full agent
        # contract lives in SKILL.md's MANDATORY WORKFLOW.  These assertions
        # keep the brief note from silently disappearing again.
        assert "触发后必须执行的工作流" in text
        core = text.find("## 设计原则与核心特征")
        assert core != -1, "README_zh.md must carry the merged core-features section"
        end = text.find("\n## ", core + 1)
        core_block = text[core:end if end != -1 else len(text)]
        assert "触发后必须执行的工作流" in core_block, (
            "the workflow note must sit inside the core-features section, "
            "not as a standalone section before it")
        # a description-only reply is an explicit failure mode, not a shortcut
        assert "任务失败" in text
        assert "必须运行工具" in text

    def test_chinese_doc_mirrors_folder_signal_proposal(self):
        text = CN_MD.read_text(encoding="utf-8")
        assert "文件夹信号检测" in text
        # nothing that changes the folder may run before the user confirms
        # (the read-only doctor check is explicitly exempt and runs first)
        assert "用户确认前不运行任何会改动文件夹的命令" in text
        assert "跳过提议" in text
        # propose-first discipline is spelled out in the workflow section
        assert "先提议，再动手" in text
        # the session-start structure check is documented as step 1
        assert "会话开局结构检查" in text
        assert "doctor" in text

    def test_chinese_doc_documents_deliverable_keywords(self):
        text = CN_MD.read_text(encoding="utf-8")
        # the Chinese deliverable keyword set is listed, including the
        # words a live test showed falling through to process/
        for kw in ("定稿", "最终版", "终稿", "综述", "报告", "总结", "小结"):
            assert kw in text

    def test_changelog_documents_current_version(self):
        text = CHANGELOG_MD.read_text(encoding="utf-8")
        assert f"## [{__version__}]" in text

    def test_changelog_documents_broadcast_and_folder_signal(self):
        text = CHANGELOG_MD.read_text(encoding="utf-8")
        # both headline features must be
        # documented in its entry (the old [Unreleased] section is gone)
        head = text.split("## Version history")[0]
        assert "## [Unreleased]" not in head
        assert "broadcast center" in head
        assert "folder-signal" in head

    def test_description_claims_broadcast_center(self):
        desc = _description()
        # the broadcast index is on the trigger surface, and the read-order
        # promise (one summary instead of every original) is explicit
        assert "`_broadcast/` index" in desc
        assert "one summary instead of every original" in desc

    def test_description_covers_content_production_shape(self):
        desc = _description()
        # the read-then-write shape must be on the trigger surface, not only
        # the "organize a folder" shape
        assert "every deliverable" in desc
        assert "whatever the deliverable" in desc
        assert "however many steps" in desc

    def test_skill_md_has_broadcast_section_with_guarantees(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # the index is a declared output, with its role spelled out
        assert "`_broadcast/INDEX.md`" in text
        assert "context-compression index" in text

    def test_skill_md_has_read_order_protocol(self):
        # a later session must be told to read the index before the originals,
        # otherwise the index saves nothing
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "Read it before opening any original" in text
        assert "saves tokens" in text
        assert "doctor" in text

    def test_skill_md_documents_doctor_subcommand(self):
        # C-tier: the read-only diagnostics command must be discoverable in
        # the docs, with its "next step" purpose stated.  The executable
        # check (that `doctor` actually dispatches) lives in test_doctor.
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "doctor" in text
        assert "read-only" in text.lower()

    def test_chinese_doc_mirrors_broadcast(self):
        text = CN_MD.read_text(encoding="utf-8")
        assert "广播中心" in text
        assert "只读" in text
        # the final-delivery bookend: rebuild the broadcast index before handing off
        assert "重建广播索引" in text
        # the broadcast index is mandatory in a workspace task, not optional
        assert "是强制的、不是可选项" in text

    def _has_cjk(self, text: str) -> bool:
        return any("\u4e00" <= c <= "\u9fff" for c in text)

    def test_skill_md_is_pure_english(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # user-facing docs are strict English; no Chinese triggers left behind
        assert not self._has_cjk(text), "SKILL.md contains CJK characters"

    def test_readme_md_is_pure_english(self):
        text = (SKILL_DIR / "README.md").read_text(encoding="utf-8")
        # The bilingual nav link at the top of the file carries the Chinese
        # label "中文说明" by repository convention; it is exempted, so the
        # CJK scan runs on the body only. Drop the nav link wherever it
        # appears (the first line, possibly wrapped in a blockquote).
        nav = "[English](README.md) · [中文说明](README_zh.md)"
        assert nav in text, "README must carry the bilingual nav link"
        body = text.replace(nav, "")
        assert not self._has_cjk(body), \
            "README.md body contains CJK characters (nav link exempted)"

    def test_no_task_specific_examples(self):
        for path in (SKILL_MD, SKILL_DIR / "README.md"):
            text = path.read_text(encoding="utf-8")
            low = text.lower()
            for marker in (
                "bilibili", "b站", "新质生产力", "西方经济",
                "this release", "newly added", "added in this",
                "new in this version", "this version adds",
            ):
                assert marker not in low, (
                    f"{path.name} contains version/示例 marker: {marker!r}"
                )

    def test_skill_md_documents_always_on_behaviour(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "At session start on a known task folder — run `doctor` first" in text
        assert "named or attached" in _description()

    def test_content_production_is_a_hard_constraint(self):
        # producing a deliverable inside a task folder MUST be paired with the
        # bookend loop; the wording that makes this non-negotiable must
        # survive future doc edits
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "Content production is a hard constraint" in text
        section = text[text.index("Content production is a hard constraint"):]
        assert "bookend" in section[:400]

    def test_description_states_general_trigger_principle(self):
        # the trigger is a situation (a task folder plus file activity), not a
        # checklist of output types; the description must lead with it
        desc = _description()
        assert "Fires whenever a task folder is named or attached" in desc
        assert "whatever the deliverable" in desc

    def test_description_trigger_is_step_count_independent(self):
        # a "single-target task, fewer than 3 steps" misjudgment must not
        # suppress the trigger: the description says so explicitly
        desc = _description()
        assert "however many steps" in desc
        assert "whatever the deliverable" in desc

