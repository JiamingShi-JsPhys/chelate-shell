# -*- coding: utf-8 -*-
"""声音五条的可自动检查部分（对应 references/revision.md §2）。

「有没有人味」最终由人判，但五条里有四条可量化：

- S1 具体数字：每 300 字至少 1 个阿拉伯数字。
- S2 具体名词：每 300 字至少 1 个「专有名词类」词（人名/地名/产品/型号/年份/文件名）。
  用启发式：含大写字母开头的专有词、含「年/号/型/文件」等量词、或带下划线/小数点的标识。
- S3 不确定性：全文至少 1 处（其实、不过、我不确定、还在想、可能、或许）。
- S5 说话人在场：全文至少 2 处（我/我们 + 附近出现具体身份或动作词）。

S4 节奏变化（段落长度比）也可算，但易误判，默认只在报告里给参考值，不判 pass/fail。

短稿（< 300 字）只核 S3、S5；S1、S2 有一条即可。
"""
from __future__ import annotations

import re
from typing import NamedTuple


class SoundRule(NamedTuple):
    code: str        # "S1".."S5"
    name: str
    description: str


SOUND_RULES: list[SoundRule] = [
    SoundRule("S1", "具体数字", "每 300 字至少 1 个数字（金额/时长/百分比/数量/日期）"),
    SoundRule("S2", "具体名词", "每 300 字至少 1 个专有名词（人名/地名/产品/型号/文件名）"),
    SoundRule("S3", "不确定性", "全文至少 1 处不确定性（其实/不过/我不确定/还在想/可能/或许）"),
    SoundRule("S4", "节奏变化", "连续 5 段内最长段不超过最短段 4 倍（仅参考，不判 fail）"),
    SoundRule("S5", "说话人在场", "全文至少 2 处能看出谁在说（我/我们 + 具体身份或动作）"),
]

UNCERTAINTY = re.compile(r"其实|不过|我不(太)?确定|还在想|可能|或许|说不准|未必|不一定|没准")
FIRST_PERSON = re.compile(r"我(们)?")
# 具体名词启发式：首字母大写的英文专有词、年份、带标识符的词、含量词的中文
PROPER_NOUN = re.compile(
    r"\b[A-Z][a-z]{2,}\b"                      # 英文专有名词（Person, OpenAI...）
    r"|\d{4}年"                                  # 中文年份
    r"|[\u4e00-\u9fff]{1,6}(号|型|文件|版本|接口|模块|引擎)"  # 型号/文件名类
    r"|\b[a-z]{2,}[_-][a-z]{2,}\b"               # 带连字符的标识符
    r"|[\u4e00-\u9fff]{1,4}(市|省|县|区)"          # 地名
)
ACTION_WORDS = re.compile(
    r"我(们)?(读|看|算|写|跑|测|做|试|改|补|查|问|想|决定|发现|遇到|踩|翻|查|核)"
)


def check_sound(text: str) -> dict:
    """返回 {code: {"pass": bool, "detail": str}}，供报告人工核对。"""
    total = len(text)
    per_300 = max(1, total // 300)
    short_doc = total < 300

    digits = re.findall(r"\d+", text)
    s1_pass = (len(digits) >= per_300) if not short_doc else (len(digits) >= 1)

    proper = PROPER_NOUN.findall(text)
    s2_pass = (len(proper) >= per_300) if not short_doc else (len(proper) >= 1)

    s3_pass = bool(UNCERTAINTY.search(text))
    s5_pass = len(ACTION_WORDS.findall(text)) >= 2

    # S4 仅参考
    paras = [p for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    if len(paras) >= 2:
        lengths = [len(p) for p in paras]
        s4_ratio = (max(lengths) / min(lengths)) if min(lengths) else 0
    else:
        s4_ratio = None

    return {
        "S1": {"pass": s1_pass, "detail": f"数字 {len(digits)} 个（需 ≥{per_300}）" if not short_doc else f"数字 {len(digits)} 个"},
        "S2": {"pass": s2_pass, "detail": f"专有名词 {len(proper)} 个（需 ≥{per_300}）" if not short_doc else f"专有名词 {len(proper)} 个"},
        "S3": {"pass": s3_pass, "detail": "找到不确定性表达" if s3_pass else "未找到不确定性（补 1 处）"},
        "S4": {"pass": s4_ratio is not None and s4_ratio <= 4, "detail":
               (f"段长比 {s4_ratio:.1f}" if s4_ratio is not None else "段落 <2，跳过")},
        "S5": {"pass": s5_pass, "detail": f"说话人在场 {len(ACTION_WORDS.findall(text))} 处（需 ≥2）"},
    }
