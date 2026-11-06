# -*- coding: utf-8 -*-
"""中文 AI 味词库（A1–A10 词面 + B1–B7 结构提示）。

每条模式：``(code, name, regex, penalty, severity, weighted, note)``。
``weighted`` 为 ``"head"``（A1，文首 20% 行命中 ×1.5）、``"tail"``（A4，
文末 20% 行命中 ×1.5）或 ``""``（全文）。

本表是「精华提炼」后的可扫描子集；词库全量与 before/after 对照见
``references/ai-patterns-zh.md``，评分规则见 ``references/scoring-rubric.md``。
纯 stdlib，无第三方依赖。
"""
from __future__ import annotations

from typing import NamedTuple


class ZHPattern(NamedTuple):
    code: str      # e.g. "A1"
    name: str      # e.g. "开头套话"
    regex: str
    penalty: int   # 单次基础扣分（绝对值）
    severity: str  # high / mid / low
    weighted: str = ""   # "head" | "tail" | ""
    note: str = ""


# 头部加权（文首 20% 行命中 ×1.5）
HEAD: list[ZHPattern] = [
    ZHPattern("A1", "开头套话", r"在当今(社会|时代)", 8, "high", "head"),
    ZHPattern("A1", "开头套话", r"随着[^，。]{2,30}的(发展|日益|不断)", 8, "high", "head"),
    ZHPattern("A1", "开头套话", r"众所周知[，,]", 7, "high", "head"),
    ZHPattern("A1", "开头套话", r"毋庸置疑[，,]|不可否认[，,]", 7, "high", "head"),
    ZHPattern("A1", "开头套话", r"近年来[^，。]{0,15}日益", 6, "high", "head"),
    ZHPattern("A1", "开头套话", r"伴随着[^，。]{2,30}的(快速|迅猛)", 8, "high", "head"),
    ZHPattern("A1", "开头套话", r"在[^，。]{2,20}的背景下", 5, "mid", "head"),
    ZHPattern("A1", "开头套话", r"一直以来[^，。]{2,20}都", 4, "low", "head"),
    ZHPattern("A10", "模板口水", r"大家好[，,]", 6, "high", "head"),
    ZHPattern("A10", "模板口水", r"本文将从[^，。]{0,30}个方面", 7, "high", "head"),
    ZHPattern("A10", "模板口水", r"希望本文(能够|可以)", 5, "mid", "head"),
    ZHPattern("A10", "模板口水", r"如(有不当|有疏漏|有错误)[，,]", 4, "low", "head"),
]

# 全文
BODY: list[ZHPattern] = [
    # A2 转折连接
    ZHPattern("A2", "转折连接", r"此外[，,]", 2, "low"),
    ZHPattern("A2", "转折连接", r"与此同时[，,]", 2, "low"),
    ZHPattern("A2", "转折连接", r"不仅如此[，,]", 2, "low"),
    ZHPattern("A2", "转折连接", r"综上所述[，,]", 4, "mid"),
    ZHPattern("A2", "转折连接", r"总而言之[，,]", 4, "mid"),
    ZHPattern("A2", "转折连接", r"一方面[^，。]{1,15}[，,另一方面]", 3, "low"),
    ZHPattern("A2", "转折连接", r"既[^，。]{1,12}又[^，。]{1,12}还", 3, "low"),
    ZHPattern("A2", "转折连接", r"无可厚非", 4, "mid"),
    ZHPattern("A2", "转折连接", r"瑕不掩瑜", 4, "mid"),
    # A3 官腔形容词
    ZHPattern("A3", "官腔形容词", r"至关重要", 5, "high"),
    ZHPattern("A3", "官腔形容词", r"举足轻重", 5, "high"),
    ZHPattern("A3", "官腔形容词", r"不可或缺", 4, "mid"),
    ZHPattern("A3", "官腔形容词", r"深入(探讨|分析|研究)", 5, "high"),
    ZHPattern("A3", "官腔形容词", r"高度重视", 5, "high"),
    ZHPattern("A3", "官腔形容词", r"深入推进", 5, "high"),
    ZHPattern("A3", "官腔形容词", r"扎实开展", 5, "high"),
    ZHPattern("A3", "官腔形容词", r"积极探索", 4, "mid"),
    ZHPattern("A3", "官腔形容词", r"有效落实", 4, "mid"),
    ZHPattern("A3", "官腔形容词", r"持续优化", 4, "mid"),
    ZHPattern("A3", "官腔形容词", r"凝聚共识", 5, "high"),
    ZHPattern("A3", "官腔形容词", r"汇聚合力", 5, "high"),
    ZHPattern("A3", "官腔形容词", r"协同推进", 4, "mid"),
    ZHPattern("A3", "官腔形容词", r"全方位(提升|推进|优化)", 4, "mid"),
    ZHPattern("A3", "官腔形容词", r"多角度(分析|审视)", 4, "mid"),
    ZHPattern("A3", "官腔形容词", r"立体化", 3, "low"),
    # A5 排比三段式
    ZHPattern("A5", "排比三段式", r"这不仅[^，。]{2,20}[，,][^，。]{2,15}也[^，。]{2,15}[，,更]?", 6, "high"),
    ZHPattern("A5", "排比三段式", r"从[^，。]{2,15}到[^，。]{2,15}[，,从][^，。]{2,15}到", 4, "mid"),
    # A6 营销黑话
    ZHPattern("A6", "营销黑话", r"赋能", 5, "high"),
    ZHPattern("A6", "营销黑话", r"加持", 5, "high"),
    ZHPattern("A6", "营销黑话", r"引爆", 5, "high"),
    ZHPattern("A6", "营销黑话", r"破圈", 5, "high"),
    ZHPattern("A6", "营销黑话", r"一站式", 4, "mid"),
    ZHPattern("A6", "营销黑话", r"全链路", 4, "mid"),
    ZHPattern("A6", "营销黑话", r"闭环", 4, "mid"),
    ZHPattern("A6", "营销黑话", r"抓手", 5, "high"),
    ZHPattern("A6", "营销黑话", r"底层逻辑", 5, "high"),
    ZHPattern("A6", "营销黑话", r"顶层设计", 5, "high"),
    ZHPattern("A6", "营销黑话", r"(打造|构建|重塑)[^，。]{2,15}(方案|生态|体系|平台)", 3, "low"),
    ZHPattern("A6", "营销黑话", r"拉通|对齐|复盘", 3, "low"),
    # A7 模糊归因
    ZHPattern("A7", "模糊归因", r"专家指出", 5, "high"),
    ZHPattern("A7", "模糊归因", r"业内人士表示", 5, "high"),
    ZHPattern("A7", "模糊归因", r"据相关(研究|调查|数据)表明", 5, "high"),
    ZHPattern("A7", "模糊归因", r"大量数据表明", 5, "high"),
    ZHPattern("A7", "模糊归因", r"有学者认为", 4, "mid"),
    ZHPattern("A7", "模糊归因", r"专家(普遍|一致)认为", 4, "mid"),
    ZHPattern("A7", "模糊归因", r"大家普遍认为", 3, "low"),
    # A8 伪深度
    ZHPattern("A8", "伪深度", r"(是|为)[^，。]{2,15}的(体现|证明|象征)", 5, "high"),
    ZHPattern("A8", "伪深度", r"彰显了[^，。]{2,20}(意义|价值|精神)", 5, "high"),
    ZHPattern("A8", "伪深度", r"凸显了[^，。]{2,20}(意义|价值)", 5, "high"),
    ZHPattern("A8", "伪深度", r"反映了更深(层次)的", 4, "mid"),
    # A9 假大空成语
    ZHPattern("A9", "假大空成语", r"博大精深", 4, "mid"),
    ZHPattern("A9", "假大空成语", r"源远流长", 4, "mid"),
    ZHPattern("A9", "假大空成语", r"历久弥新", 4, "mid"),
    ZHPattern("A9", "假大空成语", r"与时俱进", 3, "low"),
    ZHPattern("A9", "假大空成语", r"开拓创新", 3, "low"),
    ZHPattern("A9", "假大空成语", r"锐意进取", 3, "low"),
    ZHPattern("A9", "假大空成语", r"举世(瞩目|无双)", 4, "mid"),
    # A10 模板口水
    ZHPattern("A10", "模板口水", r"感谢(您的)?(观看|阅读|支持)", 5, "high"),
    ZHPattern("A10", "模板口水", r"以上就是[^，。]{2,30}(全部)?内容", 5, "high"),
    ZHPattern("A10", "模板口水", r"欢迎(指正|交流|留言)", 4, "mid"),
    # A11 文学 / 赛博痕迹（写诗、散文、文艺文案时高频）
    ZHPattern("A11", "赛博痕迹", r"多巴胺|辣椒素|鎏金|熵增|坍缩(成|了)", 3, "mid"),
    ZHPattern("A11", "赛博痕迹", r"泪腺的(剖白|形状)|流动的琥珀|褶皱的褶皱|古老的密码", 3, "mid"),
    ZHPattern("A11", "赛博痕迹", r"凌晨[^，。]{0,6}(点|时)[^，。]{0,4}分", 2, "low"),
    # A13 社交腔 / 过度亲和（聊天、私信、相亲场景高频）
    ZHPattern("A13", "社交腔", r"睡眼惺忪|一听名字就|太健康了吧|也太(健康|可爱|棒)了吧", 3, "mid"),
    ZHPattern("A13", "社交腔", r"先苦后甜|苦是暂时的|人生(都|总)是先苦后甜", 3, "mid"),
    ZHPattern("A13", "社交腔", r"[呀哦呢][～~！!]?\b(好|真|超)", 2, "low"),
]

# 尾部加权（文末 20% 行命中 ×1.5）
TAIL: list[ZHPattern] = [
    ZHPattern("A4", "结尾升华", r"让我们(共同|一起)", 8, "high", "tail"),
    ZHPattern("A4", "结尾升华", r"未来可期", 6, "high", "tail"),
    ZHPattern("A4", "结尾升华", r"任重道远", 6, "high", "tail"),
    ZHPattern("A4", "结尾升华", r"砥砺前行|扬帆远航", 5, "high", "tail"),
    ZHPattern("A4", "结尾升华", r"在[^，。]{2,20}的道路上(不断)?前行", 6, "high", "tail"),
    ZHPattern("A4", "结尾升华", r"为[^，。]{2,15}贡献(自己)?的?力量", 6, "high", "tail"),
    ZHPattern("A4", "结尾升华", r"谱写[^，。]{2,15}新篇章", 6, "high", "tail"),
    ZHPattern("A4", "结尾升华", r"展望未来", 4, "mid", "tail"),
]

ALL: list[ZHPattern] = HEAD + BODY + TAIL

# 改写优先级：先改影响最大的（见 references/scoring-rubric.md §3）
PRIORITY = ["A4", "A3", "A6", "A7", "A1", "A8", "A10", "A2", "A5", "A9", "A11", "A13"]

TIPS = {
    "A1": "开头套话 — 删掉“在当今社会”等模板开头，直接说事实",
    "A2": "转折词 — 用句号断开，靠上下文自然过渡",
    "A3": "官腔形容词 — 换成大白话或具体数字",
    "A4": "结尾升华 — 删掉“让我们共同”等空话，给具体计划",
    "A5": "排比三段式 — 砍到两项或四项，别硬凑三段",
    "A6": "营销黑话 — 改为具体动词，如“做了一个工具”",
    "A7": "模糊归因 — 给具体名字 / 出处 / 数字",
    "A8": "伪深度 — 删除“是 XX 的体现/证明”句式",
    "A9": "假大空成语 — 用白话翻译一遍",
    "A10": "模板口水 — 删掉口水句，直接进入正文",
    "A11": "赛博痕迹 — 删科学词/自造意象，写具体身体感受与场景",
    "A13": "社交腔 — 删空泛赞美与鸡汤，接住对方具体情绪",
}
