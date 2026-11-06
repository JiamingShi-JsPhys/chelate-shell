# -*- coding: utf-8 -*-
"""成稿硬禁令（blocking failures，命中不得交稿）。

对应 ``references/ai-patterns-zh.md`` 的「成稿硬禁令」节与英文侧的
「绝对禁词」。每条带一个 ``blocking`` 标志：

- ``blocking=True``：命中即阻断交稿（进 ``hard_failures``）。
- ``blocking=False``：需结合语境人工判断（进 ``warnings``），分数再高也
  提示人工核一遍。

纯语义类（如"表演性抒情"）不在此自动判，由 ``sound_rules`` 的人工清单兜底。
"""
from __future__ import annotations

import re
from typing import NamedTuple


class HardBan(NamedTuple):
    code: str      # HB1..
    name: str
    regex: str
    reason: str
    blocking: bool  # True = 阻断交稿；False = 人工判断


HARD_BANS: list[HardBan] = [
    HardBan("HB1", "破折号", r"——|—|–",
            "成稿一律不用破折号", True),
    HardBan("HB2", "提示性冒号", r"(一句话总结|核心是|关键在于|重点在于)[：:]",
            "提示性冒号禁止（引人物原话、代码、网址除外）", False),
    HardBan("HB3", "口语硬停", r"说白了|说穿了|先说结论",
            "禁用口语硬停用词", True),
    HardBan("HB4", "洞察路标", r"更微妙的是|还有一层|只说对了一半|值得注意的是|需要指出的是|从某种意义上说",
            "洞察路标不做段落/句路标", False),
    HardBan("HB5", "商业黑话", r"赋能|抓手|闭环|底层逻辑|顶层设计|降本增效|全链路|组合拳",
            "商业黑话换大白话（电路/工程义除外）", True),
    HardBan("HB6", "翻案腔",
            r"不是.{1,18}(而是|才是)|并非.{1,18}(而是|才是)|与其说.{1,18}不如说|看似.{1,16}实则|不在于.{1,16}而在于|你以为.{1,18}其实|回头才发现",
            "翻案腔：先立误解再推翻，判断应从正面下", True),
    HardBan("HB7", "结尾升华", r"让我们(共同|一起)|未来可期|任重道远|谱写[^。，。]{0,15}新篇章|砥砺前行|扬帆远航",
            "结尾升华换具体计划", True),
    HardBan("HB8", "动词名词化", r"进行了(优化|提升|改进|调整)|实现了(增长|提升|突破)",
            "动词名词化：改“进行了优化”为“改顺了”", False),
    HardBan("HB9", "模板口水结尾", r"以上就是[^。，。]{0,20}(全部)?内容|希望本文(能够|可以)|如有(不当|疏漏)[，,]",
            "模板口水结尾删除", True),
    # 英文侧字面硬禁
    HardBan("HB10", "english-em-dash", r"—|----",
            "English: avoid em-dash overuse", False),
    HardBan("HB11", "english-collaborative-residue",
            r"\bI hope this helps\b|\bLet me know\b|\bOf course[!]?\b",
            "English: delete chat residue", True),
    HardBan("HB12", "english-cutoff-disclaimer",
            r"\b(as of|up to|based on) my last training\b|\bas of my (last|most recent|latest) (knowledge|training|update)\b|\bmy (last|most recent) training (update|data|cut)\b",
            "English: drop cutoff hedges", True),
    HardBan("HB13", "english-sycophancy",
            r"\bGreat question[!]?\b|\bYou'?re absolutely right\b|\bWhat a (great|wonderful) (question|point)\b",
            "English: drop sycophantic openers", True),
    # 装饰性 emoji（功能性色块不在列；正文/标题/列表里出现即阻断）
    HardBan("HB14", "decorative-emoji",
            r"[🚀💡✅⭐⚠🏄🙋😬🤔🙂😎👇👆🔥💪🎯📌📊📈📉]",
            "Prose must not use decorative emoji; express with words", True),
]

_COMPILED: list[tuple[HardBan, re.Pattern]] = [
    (hb, re.compile(hb.regex)) for hb in HARD_BANS
]


def compiled() -> list[tuple[HardBan, re.Pattern]]:
    """Return [(HardBan, compiled_regex), ...] ready to run."""
    return _COMPILED


def blocking_codes() -> set[str]:
    """Codes that block shipping (all other hits are human-judge warnings)."""
    return {hb.code for hb in HARD_BANS if hb.blocking}
