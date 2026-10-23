# -*- coding: utf-8 -*-
"""Core scanning engine: one :func:`scan` for both languages.

Design (mirrors the formula-validator layered approach):

1. **Lexical** -- regex hits from the pattern library. For Chinese prose the
   hits carry penalties that feed the 0-100 *human index* (higher = more
   human). For English prose the hits feed an *AI-taste* score (higher = more
   AI-flavoured); the two scales intentionally point opposite directions.
2. **Structural** -- em-dash / exclamation / number / first-person / emoji
   counts, applied to Chinese prose only when the text is long enough.
3. **Hard-ban** -- blocking failures; any hit means "cannot ship", regardless
   of score.
4. **Sound** -- the quantifiable subset of the 声音五条, reported as
   pass/fail lines the agent must answer by hand.

The engine never *rewrites* the text. Rewriting is the agent's job, driven by
the report. The script only makes the tells visible and quantified.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Iterable

from . import patterns_zh, patterns_en, hard_bans, sound_rules
from .patterns_en import ENPattern

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
DIGIT_RE = re.compile(r"\d")
FIRST_PERSON_RE = re.compile(r"[我我们]")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")


# --------------------------------------------------------------------------- #
# data structures
# --------------------------------------------------------------------------- #


@dataclass
class Hit:
    code: str
    name: str
    pattern: str
    text: str
    line: int
    column: int
    severity: str
    penalty: int
    raw_penalty: int


@dataclass
class TraceReport:
    source: str
    language: str                       # "zh" | "en" | "mixed"
    score: int | None                   # 0-100 human index (zh only)
    ai_taste_score: int | None          # 0-100, higher = more AI (en only)
    level: str
    level_emoji: str
    hits: list[Hit] = field(default_factory=list)
    lexical_deduction: int = 0
    structural_deduction: int = 0
    hard_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sound: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)

    def can_ship(self) -> bool:
        """交稿门槛：硬禁令清零 且（中文）人话指数 ≥ 85。"""
        if self.hard_failures:
            return False
        if self.language == "en":
            return not self.hard_failures
        return (self.score or 0) >= 85


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _detect_language(text: str) -> str:
    cjk = len(CJK_RE.findall(text))
    total = max(1, len(text))
    if cjk / total > 0.25:
        return "zh"
    if cjk == 0:
        return "en"
    return "mixed"


def _line_col(text: str, start: int) -> tuple[int, int]:
    line_no = text.count("\n", 0, start) + 1
    col_no = start - (text.rfind("\n", 0, start) + 1) + 1
    return line_no, col_no


def _region(text: str, start: int) -> str:
    """head = 前 20% 行字符，tail = 后 20% 行字符。"""
    lines = text.splitlines()
    head_chars = "".join(lines[: max(1, len(lines) // 5)])
    tail_chars = "".join(lines[-max(1, len(lines) // 5):])
    if start < len(head_chars):
        return "head"
    if start >= len(text) - len(tail_chars):
        return "tail"
    return "body"


# --------------------------------------------------------------------------- #
# scanning
# --------------------------------------------------------------------------- #


def _scan_zh_patterns(text: str) -> list[Hit]:
    lines = text.splitlines()
    head_len = sum(len(l) + 1 for l in lines[: max(1, len(lines) // 5)])
    tail_start = len(text) - sum(len(l) + 1 for l in lines[-max(1, len(lines) // 5):])

    hits: list[Hit] = []
    seen: dict[tuple[str, str], int] = {}
    for p in patterns_zh.ALL:
        rx = re.compile(p.regex)
        for m in rx.finditer(text):
            start = m.start()
            region = "body"
            if p.weighted == "head" and start < head_len:
                region = "head"
            elif p.weighted == "tail" and start >= tail_start:
                region = "tail"
            raw = p.penalty
            if region != "body":
                raw = int(raw * 1.5)
            key = (p.regex, m.group(0))
            n = seen.get(key, 0) + 1
            seen[key] = n
            final = raw * min(n, 3)
            line_no, col_no = _line_col(text, start)
            hits.append(
                Hit(
                    code=p.code, name=p.name, pattern=p.regex, text=m.group(0),
                    line=line_no, column=col_no, severity=p.severity,
                    penalty=final, raw_penalty=raw,
                )
            )
    return hits


def _scan_en_patterns(text: str) -> list[Hit]:
    hits: list[Hit] = []
    seen: dict[tuple[str, str], int] = {}
    for rx, code, penalty, severity, name in patterns_en.compiled():
        for m in rx.finditer(text):
            start = m.start()
            key = (rx.pattern, m.group(0))
            n = seen.get(key, 0) + 1
            seen[key] = n
            final = penalty * min(n, 3)
            line_no, col_no = _line_col(text, start)
            hits.append(
                Hit(
                    code=code, name=name, pattern=rx.pattern, text=m.group(0),
                    line=line_no, column=col_no, severity=severity,
                    penalty=final, raw_penalty=penalty,
                )
            )
    return hits


def _structural_deduction(text: str) -> int:
    """中文稿结构扣分（≥5 行才生效）。"""
    if len(text.splitlines()) < 5:
        return 0
    total_chars = len(text)
    structural = 0
    if text.count("——") >= max(3, total_chars // 200):
        structural -= 5
    if text.count("！！！") >= 1 or text.count("!!") >= 3:
        structural -= 3
    if not DIGIT_RE.search(text):
        structural -= 12
    if not FIRST_PERSON_RE.search(text):
        structural -= 8
    emoji_count = len(EMOJI_RE.findall(text))
    if emoji_count >= 3:
        structural -= min(9, (emoji_count - 2) * 3)
    return structural


def _hard_bans(text: str) -> tuple[list[str], list[str]]:
    """返回 (blocking_failures, warnings)。blocking 标志来自 hard_bans 表。"""
    failures: list[str] = []
    warnings: list[str] = []
    for hb, rx in hard_bans.compiled():
        m = rx.search(text)
        if m:
            if hb.blocking:
                failures.append(f"[{hb.code}] {hb.name}：命中「{m.group(0)}」—— {hb.reason}")
            else:
                # 非阻断：需结合语境人工判断
                warnings.append(f"[{hb.code}] {hb.name}：疑似「{m.group(0)}」，请人工判断")
    return failures, warnings


def _zh_deduction(hits: Iterable[Hit]) -> int:
    return sum(h.penalty for h in hits)


def _en_ai_taste(text: str, hits: list[Hit]) -> int:
    """英文 AI 味分：0-100，越高越 AI。基于命中密度归一化。"""
    total = max(1, len(text))
    # 每命中一次加 0.8 分（带重复衰减），归一到百分制
    raw = sum(h.penalty for h in hits) * 0.8
    per_char = raw / (total / 1000)  # 每千字命中权重
    score = min(100, int(per_char * 2.0))
    return max(0, score)


def grade_zh(score: int) -> tuple[str, str]:
    # Returns (level_label, ""); the second element is kept for API stability
    # but is always empty: the skill prints no emoji.
    if score >= 85:
        return "人话", ""
    if score >= 70:
        return "微 AI 味", ""
    if score >= 50:
        return "中度 AI 味", ""
    if score >= 30:
        return "重度 AI 味", ""
    return "完全 AI 体", ""


def grade_en(ai_taste: int) -> tuple[str, str]:
    if ai_taste < 20:
        return "接近人话", ""
    if ai_taste < 45:
        return "微 AI 味", ""
    if ai_taste < 70:
        return "中度 AI 味", ""
    return "重度 AI 味", ""


def build_suggestions(hits: list[Hit], language: str) -> list[str]:
    by_code: dict[str, list[Hit]] = {}
    for h in hits:
        by_code.setdefault(h.code, []).append(h)
    if language == "zh":
        order = patterns_zh.PRIORITY
        tips = patterns_zh.TIPS
    else:
        order = patterns_en.PRIORITY
        tips = patterns_en.TIPS
    out: list[str] = []
    for code in order:
        if code in by_code:
            n = len(by_code[code])
            out.append(f"{tips[code]}（命中 {n} 处）")
        if len(out) >= 3:
            break
    if not out:
        out.append("未发现明显 AI 模式；仍需人工过一遍「声音五条」与冷读四问")
    return out


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #


def scan(text: str, source: str = "<stdin>") -> TraceReport:
    """扫描一段文本，返回 :class:`TraceReport`。"""
    language = _detect_language(text)

    if language in ("zh", "mixed"):
        hits = _scan_zh_patterns(text)
        lexical = _zh_deduction(hits)
        structural = _structural_deduction(text)
        score = max(0, min(100, 100 - (lexical + structural)))
        level, emoji = grade_zh(score)
        ai_taste = None
        failures, warnings = _hard_bans(text)
        sound = sound_rules.check_sound(text)
        suggestions = build_suggestions(hits, "zh")
        return TraceReport(
            source=source, language=language, score=score, ai_taste_score=ai_taste,
            level=level, level_emoji=emoji, hits=hits,
            lexical_deduction=lexical, structural_deduction=structural,
            hard_failures=failures, warnings=warnings, sound=sound,
            stats={"total_chars": len(text), "total_lines": len(text.splitlines())},
            suggestions=suggestions,
        )

    # English (or pure ASCII) -- only lexical + hard bans + structural-lite
    hits = _scan_en_patterns(text)
    ai_taste = _en_ai_taste(text, hits)
    level, emoji = grade_en(ai_taste)
    failures, warnings = _hard_bans(text)
    suggestions = build_suggestions(hits, "en")
    return TraceReport(
        source=source, language=language, score=None, ai_taste_score=ai_taste,
        level=level, level_emoji=emoji, hits=hits,
        lexical_deduction=0, structural_deduction=0,
        hard_failures=failures, warnings=warnings, sound={},
        stats={"total_chars": len(text), "total_lines": len(text.splitlines())},
        suggestions=suggestions,
    )
