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


class TestSkillDocs:
    """The documentation is part of the product - guard it."""

    def test_frontmatter_version_matches_package(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert _frontmatter_value(text, "version") == __version__

    def test_mandatory_workflow_present_and_first(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "MANDATORY WORKFLOW" in text
        # the workflow must come before the reference sections, so an agent
        # reads "what to do" before "what the tool is"
        assert text.index("MANDATORY WORKFLOW") < text.index("## When to use")

    def test_workflow_covers_the_pathless_request(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # "set up a task workspace" with no path must have a defined action
        assert "gave no path" in text
        assert "ask for it" in text
        assert "propose a concrete default" in text

    def test_workflow_forbids_description_only_reply(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "failure mode" in text
        assert "RUN the tool via Bash" in text

    def test_workflow_covers_both_entry_points(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "scripts.run init" in text
        assert "scripts.run organize" in text
        assert "mark-downloaded" in text

    def test_description_claims_folder_signal_trigger(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        desc = _frontmatter_value(text, "description")
        # "folder referenced / attached + task start" is a trigger class now
        assert "names/attaches one" in desc
        # ...and its semantics are propose-first, not act-first
        assert "PROPOSE one init" in desc
        assert "confirms" in desc
        assert "never reorganize a referenced folder uninvited" in desc

    def test_workflow_opens_with_session_start_structure_check(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # the session-start structure check (doctor) is step 1: a read-only
        # scan that runs before any confirmation because it changes nothing
        assert "Session-start structure check" in text
        assert "doctor" in text
        # the proposal gate must come before path resolution, so an agent
        # reads "propose first" before "resolve the path and run"
        assert text.index("Session-start structure check") < text.index(
            "Resolve the target root path"
        )
        # nothing that changes the folder may run before the user confirms
        assert "Do **not** run any command" in text
        assert "until the user confirms" in text
        # ...but doctor is explicitly carved out as read-only / always safe
        assert "read-only and always safe" in text

    def test_session_start_check_is_always_on(self):
        # the "every conversation starts tidy" rule must live in the
        # always-on layer, not as an optional feature
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "At session start (the structure check)" in text
        # the check is cheap and idempotent: it repairs nothing when the
        # folder is already healthy
        assert "read-only, zero-cost" in text
        assert "idempotent" in text

    def test_workflow_proposal_has_example_and_decline_path(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # the proposal gate offers a concrete setup line to the user
        assert "three-tier structure before we start" in text
        # a declined proposal ends the proposing, it does not stall the task
        assert "declines" in text
        assert "at most once per folder" in text

    def test_content_production_runs_directly_no_proposal(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        # the compound "produce + keep tidy" request is already an explicit
        # organize intent - it must not be routed through the proposal gate
        assert "no folder-signal proposal" in text

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
        text = SKILL_MD.read_text(encoding="utf-8")
        desc = _frontmatter_value(text, "description")
        # the broadcast index is a first-class trigger surface and the
        # read-order contract (read the index first, open only what you need)
        assert "broadcast index" in desc
        assert "context-compression" in desc or "index" in desc
        # token-saving read-order promise: read the index, open only what you need
        assert "open only" in desc
        assert "bookend loop" in desc or "init" in desc

    def test_description_covers_content_production_shape(self):
        # The observed failure: a "read these files and write a report"
        # request never entered the candidate set because the description
        # only advertised the "organize a folder" shape.  The trigger
        # surface must name the read-then-write shapes explicitly.
        text = SKILL_MD.read_text(encoding="utf-8")
        desc = _frontmatter_value(text, "description")
        assert "reading files" in desc
        assert "ANY deliverable" in desc
        assert "summary" in desc
        # the session-start structure check is on the trigger surface too,
        # so "every conversation starts tidy" survives the selection layer
        assert "SESSION-START" in desc
        assert "doctor" in desc

    def test_skill_md_has_broadcast_section_with_guarantees(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "## Broadcast center" in text
        # read-only semantics must be spelled out, not implied
        assert "renamed or modified" in text
        assert "The only writes are the two files in `_broadcast/`" in text
        # tool-owned protection + standalone usage
        assert "tool-owned" in text
        assert "standalone command" in text
        # long-context routing: build first, read the index before originals
        assert "long-context task" in text

    def test_skill_md_has_read_order_protocol(self):
        # G-tier: a later session must have a mandatory, ordered read
        # protocol so the index actually saves tokens (read the directory,
        # open only the matching originals, skim the rest from the digest).
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "READ-ORDER protocol" in text
        assert "Read the directory first" in text
        assert "Open only the matching originals" in text
        # the token-saving rationale is spelled out, not implied
        assert "save tokens" in text
        assert "cheap layer" in text
        # and the stale/absent path routes through doctor + broadcast
        assert "doctor" in text
        assert "build it first" in text

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
        # the "always-on" model: task-start build + final-delivery rebuild are
        # unconditional, not a separate match trigger
        assert "Always-on" in text
        assert "no separate trigger" in text or "cannot be missed" in text
        # the two bookends are spelled out as always-on
        assert "At task start" in text
        assert "At final delivery" in text

    def test_content_production_is_a_hard_constraint(self):
        # 1.0.1 contract: producing a deliverable inside a task folder MUST
        # be paired with the bookend loop - the wording that makes this
        # non-negotiable must survive future doc edits.
        text = SKILL_MD.read_text(encoding="utf-8")
        # the explicit "hard constraint" phrasing in the content-production
        # section (the section that closes the missed-trigger gap)
        section = text[text.find("Content-production scenarios"):]
        section = section[:section.find("## Broadcast center")]
        assert "hard constraint" in section.lower(), \
            "the hard-constraint wording was diluted or removed"
        # the loop is named and the skip is forbidden
        assert "bookend loop" in section
        assert "skippable" in section and "deferrable" in section
        # leaving the folder loose after a write is framed as a failure
        assert "failure" in section and "loose" in section
        # the 'When to use' matched trigger repeats the hard-constraint rule
        when = text[text.find("## When to use"):]
        assert "hard constraint" in when.lower(), \
            "the When-to-use content-production bullet lost its hard-constraint note"

    def test_description_states_general_trigger_principle(self):
        # The trigger must be a general, situational rule - a workspace folder
        # plus any file activity - NOT a checklist of output types.  No keyword
        # list can enumerate every phrasing (new ones keep appearing), so the
        # description must lead with the situation and say the examples are
        # illustrative, not exhaustive.
        text = SKILL_MD.read_text(encoding="utf-8")
        desc = _frontmatter_value(text, "description")
        assert "ANY deliverable" in desc
        assert "ANY file" in desc
        assert "not exhaustive" in desc
        # the "When to use" content-production bullet repeats the general rule
        when = text[text.find("## When to use"):]
        cp = when[when.find("Content production"):]
        cp = cp[:cp.find("Folder signal")]
        assert "any deliverable" in cp.lower()

    def test_description_trigger_is_step_count_independent(self):
        # The "single-target task, fewer than 3 steps" misjudgment must not
        # suppress the trigger.  The description must state the trigger is a
        # workspace folder + a deliverable, independent of how many steps.
        text = SKILL_MD.read_text(encoding="utf-8")
        desc = _frontmatter_value(text, "description")
        assert "independent of how many steps" in desc, \
            "the description should state the trigger is step-count independent"
        assert "single write" in desc

