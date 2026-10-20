# -*- coding: utf-8 -*-
"""ai-trace-remover CLI.

Usage:
    python -m src.cli <file|-> [--json] [-o report.md]
    python -m src.cli <file|-> --score-only

    cat 稿件.md | python -m src.cli -

The engine only *detects and quantifies*; it never rewrites. The agent reads
the report, rewrites by hand following ``references/``, then re-runs to verify.

Exit codes:
    0  clean (no blocking hard-bans; zh human-index >= 85)
    1  blocking hard-ban present, or zh human-index < 85
    2  input read / parse failure
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from . import __version__
from .core import engine
from .core.engine import Hit, TraceReport


def _force_utf8_stdio() -> None:
    """Keep stdout/stderr UTF-8 even under a legacy Windows console.

    The Chinese report contains CJK level labels (e.g. 微 AI 味); on a
    Windows single-file exe the console defaults to cp1252, which would
    crash ``print``. Rebinding to UTF-8 makes output portable. No-op when
    the stream already is UTF-8 (normal POSIX / piped use).
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and stream.encoding != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass



# --------------------------------------------------------------------------- #
# input
# --------------------------------------------------------------------------- #


def _read_input(path: str) -> tuple[str, str]:
    """Return (text, source_label)."""
    if path == "-":
        return sys.stdin.read(), "<stdin>"
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"输入不存在: {path}")
    try:
        return p.read_text(encoding="utf-8"), str(p)
    except UnicodeDecodeError:
        # 非 UTF-8 文本（如 GBK）：换 encoding 再试一次
        return p.read_text(encoding="gb18030"), str(p)


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def _hit_preview(text: str, width: int = 24) -> str:
    text = text.replace("|", "\\|").strip()
    return text if len(text) <= width else text[:width] + "…"


def _suggestion_block(suggestions: list[str]) -> str:
    out = ["## 改写建议（按优先级）", ""]
    for i, s in enumerate(suggestions, 1):
        out.append(f"{i}. {s}")
    out.append("")
    return "\n".join(out)


def _sound_block(sound: dict) -> str:
    if not sound:
        return ""
    labels = {
        "S1": "具体数字", "S2": "具体名词", "S3": "不确定性",
        "S4": "节奏变化", "S5": "说话人在场",
    }
    out = ["## 声音五条（需人工核对）", "",
           "| 项 | 达标 | 详情 |", "|---|---|---|"]
    for code in ("S1", "S2", "S3", "S4", "S5"):
        cell = "[pass]" if sound[code]["pass"] else "[fail]"
        note = "（仅参考）" if code == "S4" else ""
        out.append(f"| {labels[code]} | {cell} {note} | {sound[code]['detail']} |")
    out.append("")
    out.append("> 第 4 条（节奏）仅供参考；S1–S3、S5 全过才算「有人味」。")
    out.append("")
    return "\n".join(out)


def _render_md(rep: TraceReport) -> str:
    lines: list[str] = []
    lines.append("# AI 痕迹检测报告")
    lines.append("")
    lines.append(f"**稿件：** `{rep.source}`")
    lines.append(f"**语种判定：** {rep.language}")

    if rep.language in ("zh", "mixed"):
        lines.append(f"## 人话指数：**{rep.score} / 100**  {rep.level_emoji} {rep.level}")
    else:
        lines.append(f"## AI 味指数：**{rep.ai_taste_score} / 100**  {rep.level_emoji} {rep.level}")

    if rep.language == "en":
        verdict = "可以交稿。" if rep.can_ship() else "不可交稿（见硬禁项）。"
    elif rep.hard_failures:
        verdict = f"不可交稿 —— 硬禁项 {len(rep.hard_failures)} 处未清零。"
    elif (rep.score or 0) < 85:
        verdict = f"建议再改一轮 —— 硬禁项已清零，但人话指数 {rep.score} 仍 < 85。"
    else:
        verdict = "可以交稿。"
    lines.append(f"**判定：** {verdict}")
    lines.append("")

    # hard bans
    lines.append("## 一、硬禁项（必须清零）")
    if rep.hard_failures:
        for item in rep.hard_failures[:40]:
            lines.append(f"- {item}")
        if len(rep.hard_failures) > 40:
            lines.append(f"\n*（还有 {len(rep.hard_failures) - 40} 处未显示）*")
        lines.append("")
    else:
        lines.append("- 无。硬禁令已清零。")
        lines.append("")

    # top hits
    lines.append("## 二、命中 Top 10")
    if rep.hits:
        lines.append("| # | 类别 | 命中 | 位置 | 严重度 | 扣分 |")
        lines.append("|---|---|---|---|---|---|")
        for i, h in enumerate(sorted(rep.hits, key=lambda h: -h.penalty)[:10], 1):
            lines.append(
                f"| {i} | {h.code} {h.name} | `{_hit_preview(h.text)}` | "
                f"第 {h.line} 行 | {h.severity} | -{h.penalty} |"
            )
        lines.append("")
    else:
        lines.append("未命中词面模式。注意：词面干净不等于有人味，仍需过「声音五条」。")
        lines.append("")

    # suggestions
    lines.extend(_suggestion_block(rep.suggestions).split("\n"))

    # sound rules
    if rep.sound:
        lines.extend(_sound_block(rep.sound).split("\n"))

    # warnings
    if rep.warnings:
        lines.append("## 需要人工判断")
        for item in rep.warnings[:20]:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## 下一步")
    lines.append("1. 先清「硬禁项」，对照 `references/ai-patterns-zh.md` 的成稿硬禁令。")
    lines.append("2. 再按上方优先级改 Top 命中（对照 `references/revision.md`）。")
    lines.append("3. 改完重跑本 CLI，直到硬禁项为零且人话指数 ≥ 85。")
    lines.append("4. 长稿另走完七遍改稿 + 冷读四问。")
    lines.append("")
    return "\n".join(lines)


def _render_json(rep: TraceReport) -> str:
    payload = {
        "version": __version__,
        "source": rep.source,
        "language": rep.language,
        "score": rep.score,
        "ai_taste_score": rep.ai_taste_score,
        "level": rep.level,
        "level_emoji": rep.level_emoji,
        "can_ship": rep.can_ship(),
        "hard_failures": rep.hard_failures,
        "warnings": rep.warnings,
        "sound": rep.sound,
        "deductions": {
            "lexical": rep.lexical_deduction,
            "structural": rep.structural_deduction,
        },
        "stats": rep.stats,
        "suggestions": rep.suggestions,
        "hits": [asdict(h) for h in rep.hits],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ai-trace-remover —— 检测并量化文本中的 AI 痕迹（不代改）"
    )
    p.add_argument("path", help="稿件路径，或 '-' 从 stdin 读取")
    p.add_argument("-o", "--output", help="报告写入文件（默认 stdout）")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.add_argument(
        "--score-only", action="store_true",
        help="只打印一行：分数/等级/can_ship（供流水线）"
    )
    p.add_argument("--version", action="version", version=f"ai-trace-remover {__version__}")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_stdio()
    args = _build_parser().parse_args(argv)

    try:
        text, source = _read_input(args.path)
    except SystemExit:
        return 2
    except OSError as exc:
        print(f"无法读取稿件：{exc}", file=sys.stderr)
        return 2

    rep = engine.scan(text, source)

    if args.score_only:
        if rep.language in ("zh", "mixed"):
            print(f"score: {rep.score}/100  level: {rep.level}  "
                  f"hard_bans={len(rep.hard_failures)}  can_ship={'yes' if rep.can_ship() else 'no'}")
        else:
            print(f"ai_taste: {rep.ai_taste_score}/100  level: {rep.level}  "
                  f"hard_bans={len(rep.hard_failures)}  can_ship={'yes' if rep.can_ship() else 'no'}")
        return 0 if rep.can_ship() else 1

    body = _render_json(rep) if args.json else _render_md(rep)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        tag = f"人话指数 {rep.score}" if rep.language in ("zh", "mixed") else f"AI味 {rep.ai_taste_score}"
        print(f"已写入 {out}（{tag}，硬禁项 {len(rep.hard_failures)} 处）")
    else:
        print(body)

    return 0 if rep.can_ship() else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
