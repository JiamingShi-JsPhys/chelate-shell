"""Tests for :mod:`scripts.rules` -- YAML placement-rule configuration .



The rules module ships its own dependency-free mini-YAML reader, so these

tests validate both the parser and the fallback behaviour.

"""

from __future__ import annotations



from pathlib import Path



import pytest



from scripts import rules





# ---------------------------------------------------------------------------

# Built-in rules

# ---------------------------------------------------------------------------





def test_builtin_rules_have_placement_and_default() -> None:

    b = rules.builtin_rules()

    assert len(b.placement) >= 1

    #: the fallback is `process` (assistant output), NOT the

    # user-reserved `material/initial`.

    assert b.default_target == "process"





def test_builtin_target_for_known_keywords() -> None:

    b = rules.builtin_rules()

    assert b.target_for("my_draft_v1.txt") == "process"

    assert b.target_for("final_report.pdf") == "results"





def test_builtin_target_for_unknown_falls_back_to_default() -> None:

    b = rules.builtin_rules()

    assert b.target_for("notes.txt") == "process"





def test_builtin_chinese_deliverable_keywords() -> None:

    """the keyword fallback understands Chinese deliverable names.



    A live test showed ``综述_xxx.txt`` / ``报告_xxx.docx`` falling through

    to ``process/`` because only English ``final``/``deliverable`` were

    recognised -- the finished article never reached ``results/``.

    """

    b = rules.builtin_rules()

    assert b.target_for("综述_西方计划性繁荣.txt") == "results"

    assert b.target_for("报告_2026.docx") == "results"

    assert b.target_for("定稿_v3.md") == "results"

    assert b.target_for("最终版数据.xlsx") == "results"

    # a live failure showed 总结/终稿 landing in process/ - both are
    # finished deliverables, not drafts
    assert b.target_for("总结.md") == "results"

    assert b.target_for("终稿.docx") == "results"

    assert b.target_for("研究课题可行性报告.md") == "results"

    assert b.target_for("调研小结.txt") == "results"





def test_builtin_chinese_draft_keywords() -> None:

    """Chinese draft words route to process/ as well."""

    b = rules.builtin_rules()

    assert b.target_for("草稿_01.txt") == "process"

    assert b.target_for("临时 Notes.md") == "process"





def test_builtin_no_chinese_download_keyword() -> None:

    """The removal still holds: 下载 in a name is not provenance."""

    b = rules.builtin_rules()

    assert b.target_for("下载的资料.pdf") == rules.BUILTIN_DEFAULT_TARGET





def test_builtin_has_no_download_keyword_rule() -> None:

    """'download' is a provenance, not a filename pattern."""

    targets = {t for _p, _k, t in rules.builtin_rules().placement}

    assert "material/downloaded" not in targets





def test_target_for_helper_with_none_rules_uses_builtin() -> None:

    # rules.target_for(name, None) must use the built-in table.

    assert rules.target_for("draft.txt", None) == "process"





# ---------------------------------------------------------------------------

# YAML parsing (block style)

# ---------------------------------------------------------------------------





def test_load_rules_from_block_yaml(tmp_path: Path) -> None:

    cfg = tmp_path / "cfg.yml"

    cfg.write_text(

        "placement:\n"

        "  - priority: 1\n"

        "    keywords: [spec, memo]\n"

        "    target: results\n"

        "  - priority: 2\n"

        "    keywords: [log, data]\n"

        "    target: process\n"

        "defaults:\n"

        "  target: material/initial\n",

        encoding="utf-8",

    )

    r = rules.load_rules(root=tmp_path, extra_path=cfg)

    assert r.target_for("spec_sheet.md") == "results"

    assert r.target_for("raw_log.txt") == "process"

    assert r.target_for("whatever.txt") == "material/initial"





def test_load_rules_inline_keywords(tmp_path: Path) -> None:

    # Inline flow lists must be parsed into keyword lists.

    cfg = tmp_path / "cfg.yml"

    cfg.write_text(

        "placement:\n"

        "  - priority: 1\n"

        "    keywords: [alpha, gamma]\n"

        "    target: results\n",

        encoding="utf-8",

    )

    r = rules.load_rules(root=tmp_path, extra_path=cfg)

    assert r.target_for("alpha.txt") == "results"

    assert r.target_for("gamma.txt") == "results"

    # A keyword not in the table must fall back to the default.

    assert r.target_for("beta.txt") == rules.BUILTIN_DEFAULT_TARGET





def test_load_rules_no_config_uses_builtin(tmp_path: Path) -> None:

    # No .task-organizer.yml anywhere -> built-in rules.

    r = rules.load_rules(root=tmp_path)

    assert r.default_target == rules.BUILTIN_DEFAULT_TARGET





def test_load_rules_malformed_falls_back_to_builtin(tmp_path: Path) -> None:

    # A tab character is explicitly unsupported and must not crash.

    bad = tmp_path / ".task-organizer.yml"

    bad.write_text("placement:\n\t- priority: 1\n", encoding="utf-8")

    r = rules.load_rules(root=tmp_path)

    # Fallback to built-ins (never raises).

    assert r.default_target == rules.BUILTIN_DEFAULT_TARGET





def test_comment_only_config_is_silent_builtin(tmp_path: Path) -> None:

    # `init` writes a comment-only template; loading it must NOT raise and

    # must NOT emit an "empty document" warning -- it silently uses the

    # built-in rules, so deliverable keywords (报告/final -> results) still work.

    cfg = tmp_path / ".task-organizer.yml"

    cfg.write_text(

        "# task-organizer placement rules\n# defaults:\n#   target: material/initial\n",

        encoding="utf-8",

    )

    r = rules.load_rules(root=tmp_path)

    assert r.default_target == rules.BUILTIN_DEFAULT_TARGET

    # Built-in placement is present (keywords resolve), not an empty table.

    assert r.target_for("开题报告.md") == "results"

    assert r.target_for("draft_notes.txt") == "process"





# ---------------------------------------------------------------------------

# Search precedence

# ---------------------------------------------------------------------------





def test_extra_path_wins_over_root(tmp_path: Path) -> None:

    root_cfg = tmp_path / ".task-organizer.yml"

    root_cfg.write_text(

        "placement:\n  - priority: 1\n    keywords: [a]\n    target: results\n",

        encoding="utf-8",

    )

    extra = tmp_path / "extra.yml"

    extra.write_text(

        "placement:\n  - priority: 1\n    keywords: [b]\n    target: process\n",

        encoding="utf-8",

    )

    r = rules.load_rules(root=tmp_path, extra_path=extra)

    # extra_path takes top priority.

    assert r.target_for("b.txt") == "process"

    assert r.target_for("a.txt") == rules.BUILTIN_DEFAULT_TARGET  # 'a' no longer in table





def test_home_config_searched_when_root_absent(tmp_path: Path, monkeypatch) -> None:

    # Point Path.home() at an empty tmp dir -> no home config -> built-ins.

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    r = rules.load_rules(root=tmp_path)

    assert r.default_target == rules.BUILTIN_DEFAULT_TARGET





# ---------------------------------------------------------------------------

# Domain profiles 

# ---------------------------------------------------------------------------



_PHARMA_CONFIG = """\

default_profile: pharma



profiles:

  general:

    placement:

      - priority: 1

        keywords: [final, deliverable]

        target: results

    defaults:

      target: process



  pharma:

    placement:

      - priority: 1

        keywords: ["原始数据", raw, 实验数据]

        target: material/initial

      - priority: 2

        keywords: [最终版, 定稿, final]

        target: results

      - priority: 3

        keywords: [临床报告, 病例, clinical]

        target: results

    defaults:

      target: process

"""





def _write(tmp_path: Path, text: str) -> Path:

    cfg = tmp_path / ".task-organizer.yml"

    cfg.write_text(text, encoding="utf-8")

    return cfg





def test_default_profile_is_selected(tmp_path: Path) -> None:

    _write(tmp_path, _PHARMA_CONFIG)

    r = rules.load_rules(root=tmp_path)

    assert r.name == "pharma"

    assert r.target_for("raw_data.csv") == "material/initial"

    assert r.target_for("实验数据_01.xlsx") == "material/initial"

    assert r.target_for("最终版报告.docx") == "results"

    assert r.target_for("clinical_trial_notes.txt") == "results"

    # Unmatched -> the profile's own default, not the built-in one.

    assert r.target_for("scratch.txt") == "process"





def test_explicit_profile_overrides_default(tmp_path: Path) -> None:

    _write(tmp_path, _PHARMA_CONFIG)

    r = rules.load_rules(root=tmp_path, profile="general")

    assert r.name == "general"

    assert r.target_for("final_report.pdf") == "results"

    # The pharma-only keywords are inert under the general profile.

    assert r.target_for("raw_data.csv") == "process"





def test_unknown_profile_falls_back_to_builtin(tmp_path: Path) -> None:

    _write(tmp_path, _PHARMA_CONFIG)

    r = rules.load_rules(root=tmp_path, profile="nope")

    assert r.name == "builtin"

    assert r.default_target == rules.BUILTIN_DEFAULT_TARGET





def test_profile_requested_without_profiles_key(tmp_path: Path) -> None:

    # A flat config declares no profiles -> asking for one is

    # a config error, which must degrade to built-ins rather than crash.

    _write(

        tmp_path,

        "placement:\n  - priority: 1\n    keywords: [a]\n    target: results\n",

    )

    r = rules.load_rules(root=tmp_path, profile="general")

    assert r.name == "builtin"





def test_flat_config_still_works(tmp_path: Path) -> None:

    """Backward compatibility: a flat config is honoured unchanged."""

    _write(

        tmp_path,

        "placement:\n"

        "  - priority: 1\n"

        "    keywords: [spec, memo]\n"

        "    target: results\n"

        "defaults:\n"

        "  target: material/initial\n",

    )

    r = rules.load_rules(root=tmp_path)

    assert r.name == "config"

    assert r.target_for("spec_sheet.md") == "results"

    assert r.target_for("whatever.txt") == "material/initial"





def test_available_profiles_lists_names(tmp_path: Path) -> None:

    _write(tmp_path, _PHARMA_CONFIG)

    assert rules.available_profiles(root=tmp_path) == ["general", "pharma"]





def test_available_profiles_empty_without_config(tmp_path: Path, monkeypatch) -> None:

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")

    assert rules.available_profiles(root=tmp_path) == []





def test_no_default_profile_uses_flat_layout(tmp_path: Path) -> None:

    """Profiles declared but no ``default_profile`` and none requested."""

    _write(

        tmp_path,

        "placement:\n"

        "  - priority: 1\n"

        "    keywords: [alpha]\n"

        "    target: results\n"

        "profiles:\n"

        "  other:\n"

        "    placement:\n"

        "      - priority: 1\n"

        "        keywords: [beta]\n"

        "        target: process\n",

    )

    r = rules.load_rules(root=tmp_path)

    assert r.target_for("alpha_notes.md") == "results"

    # The profile's keyword is inert while the flat layout is in charge.

    assert r.target_for("beta_notes.md") == rules.BUILTIN_DEFAULT_TARGET





def test_no_default_profile_picks_first_alphabetically(tmp_path: Path) -> None:

    _write(

        tmp_path,

        "profiles:\n"

        "  beta:\n"

        "    placement:\n"

        "      - priority: 1\n"

        "        keywords: [beta]\n"

        "        target: results\n"

        "  alpha:\n"

        "    placement:\n"

        "      - priority: 1\n"

        "        keywords: [alpha]\n"

        "        target: process\n",

    )

    r = rules.load_rules(root=tmp_path)

    assert r.name == "alpha"

    assert r.target_for("alpha_notes.md") == "process"

