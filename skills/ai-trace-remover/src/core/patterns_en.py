# -*- coding: utf-8 -*-
"""English AI-writing pattern library (E1–E24 lexical + E-structure hints).

Original category design and regex, authored for this skill. Each entry is
``(code, name, regex, penalty, severity)``. No external text is copied.
The before/after demonstration sentences in the reference doc are original,
built from public-domain teaching texts and classic public-domain fiction.
English reports are scored with an ``ai_taste_score`` where higher = more
AI-flavoured (the opposite direction of the Chinese human index), to avoid
conflating the two scales.

Full before/after corpus: ``references/ai-patterns-en.md``.
"""
from __future__ import annotations

import re
from typing import NamedTuple


class ENPattern(NamedTuple):
    code: str
    name: str
    regex: str
    penalty: int
    severity: str  # high / mid / low


_PAT: list[ENPattern] = [
    # E1 significance / legacy inflation
    ENPattern("E1", "significance-inflation", r"\b(a pivotal|a crucial|a key|a vital|stands? as|serves as)\b", 3, "high"),
    ENPattern("E1", "significance-inflation", r"\btestament\b|\bindelible mark\b|\bmarking a\b", 3, "mid"),
    ENPattern("E1", "significance-inflation", r"\bevolving landscape\b|\bsetting the stage for\b|\bkey turning point\b", 3, "mid"),
    # E2 notability / media coverage
    ENPattern("E2", "notability", r"\bindependent coverage\b|\bmedia outlets?\b|\bleading expert\b", 3, "mid"),
    ENPattern("E2", "notability", r"\bactive social media presence\b|\bover \d[\d,]* (followers|readers)\b", 2, "mid"),
    # E3 superficial -ing analysis
    ENPattern("E3", "superficial-ing", r", (highlighting|underscoring|emphasizing|ensuring|reflecting|symbolizing|contributing to|showcasing|encompassing|fostering|cultivating)\b", 3, "mid"),
    # E4 promotional language
    ENPattern("E4", "promotional", r"\bboasts?\b|\bvibrant\b|\bstunning\b|\bbreathtaking\b|\brenowned\b|\bgroundbreaking\b", 3, "high"),
    ENPattern("E4", "promotional", r"\bmust-visit\b|\bcommitment to\b|\bexemplifies?\b|\bshowcase[sd]?\b", 2, "mid"),
    # E5 vague attribution / weasel words
    ENPattern("E5", "vague-attribution", r"\bexperts? (argue|believe|suggest|indicate)\b|\bobservers? have (cited|noted)\b", 4, "high"),
    ENPattern("E5", "vague-attribution", r"\bindustry reports?\b|\bseveral (sources|publications)\b|\bsome critics? argue\b", 3, "mid"),
    # E7 AI vocabulary
    ENPattern("E7", "ai-vocabulary", r"\b(delve|garner|pivotal|crucial|underscore[d]?|showcase[sd]?)\b", 2, "mid"),
    ENPattern("E7", "ai-vocabulary", r"\b(tapestry|landscape|intricate|intricacies|vibrant|enduring|valuable)\b", 2, "low"),
    ENPattern("E7", "ai-vocabulary", r"\badditionally\b", 1, "low"),
    # E8 copula avoidance
    ENPattern("E8", "copula-avoidance", r"\bserves? as\b|\bstands? as\b|\bmarks a\b|\brepresents a\b", 2, "mid"),
    # E9 negative parallelism
    ENPattern("E9", "negative-parallelism", r"\bnot only\b|\bIt'?s not (just|merely|only)\b", 3, "mid"),
    # E10 rule of three
    ENPattern("E10", "rule-of-three", r"\b[A-Za-z]+, [A-Za-z]+, and [A-Za-z]+\.", 1, "low"),
    # E11 synonym cycling / false range
    ENPattern("E11", "false-range", r"\bfrom the [A-Z]\w+ to the [A-Z]\w+\b", 2, "mid"),
    # E13 em-dash overuse
    ENPattern("E13", "em-dash", r"—|--", 2, "mid"),
    # E17 emoji in headings / bullets
    ENPattern("E17", "emoji", r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]", 2, "mid"),
    # E18 curly quotes
    ENPattern("E18", "curly-quotes", r"“|”|‘|’", 1, "low"),
    # E19 collaborative residue
    ENPattern("E19", "collaborative-residue", r"\bI hope this helps\b|\bOf course[!]?\b|\bCertainly[!]?\b", 3, "high"),
    ENPattern("E19", "collaborative-residue", r"\bYou'?re (absolutely )?right\b|\bLet me know\b|\bHere is a\b|\bWould you like\b", 3, "high"),
    # E20 knowledge-cutoff disclaimer
    ENPattern("E20", "cutoff-disclaimer", r"\bas of (20\d\d|my last training)\b|\bup to my last training update\b", 3, "high"),
    ENPattern("E20", "cutoff-disclaimer", r"\bwhile specific details (are|were) (limited|scarce)\b|\bbased on available information\b", 3, "high"),
    # E21 sycophancy
    ENPattern("E21", "sycophancy", r"\bGreat question[!]?\b|\bExcellent point\b|\bThat'?s (a )?great\b", 2, "mid"),
    # E22 filler
    ENPattern("E22", "filler", r"\bIn order to\b|\bDue to the fact that\b|\bAt this point in time\b|\bIn the event that\b", 2, "mid"),
    # E23 excessive hedging
    ENPattern("E23", "excessive-hedging", r"\bcould (potentially|possibly)\b|\bmight have (some|any) (effect|impact)\b", 2, "mid"),
    # E24 generic positive conclusion
    ENPattern("E24", "generic-conclusion", r"\bThe future looks (bright|promising)\b|\bExciting times lie ahead\b", 3, "high"),
    ENPattern("E24", "generic-conclusion", r"\bmajor step in the right direction\b|\bjourney toward excellence\b", 3, "mid"),
]

# Pre-compiled cache: (compiled, code, penalty, severity)
_COMPILED: list[tuple[re.Pattern, str, int, str]] = [
    (re.compile(p.regex), p.code, p.penalty, p.severity) for p in _PAT
]

# Public accessors (avoid reaching into module-private names elsewhere).
def compiled() -> list[tuple[re.Pattern, str, int, str, str]]:
    """Return [(regex, code, penalty, severity, name), ...] ready to run."""
    names = {p.regex: p.name for p in _PAT}
    return [(rx, code, pen, sev, names.get(rx.pattern, code)) for rx, code, pen, sev in _COMPILED]

# 改写优先级：先改影响最大的。
PRIORITY = [
    "E24", "E4", "E21", "E20", "E19", "E5", "E7", "E3", "E1", "E8",
    "E9", "E10", "E11", "E13", "E2", "E22", "E23", "E17", "E18",
]

TIPS = {
    "E1": "Significance inflation - cut “pivotal / testament / evolving landscape”; state the fact",
    "E2": "Name-dropping - drop the media list; cite one specific, dated source",
    "E3": "Superficial “-ing” - break the clause; say the concrete thing directly",
    "E4": "Promotional adjectives - replace with a measured fact or number",
    "E5": "Vague attribution - name the expert / study / figure; “experts believe” is a tell",
    "E7": "AI vocabulary - swap delve / pivotal / crucial / underscore for plain verbs",
    "E8": "Copula avoidance - say “is”, not “serves as / stands as”",
    "E9": "Negative parallelism - drop “not only… but” / “it’s not just X, it’s Y”",
    "E10": "Rule of three - keep two or four items, not a forced trio",
    "E11": "False range - list the actual items instead of “from X to Y” on different scales",
    "E13": "Em-dash overuse - split the sentence or use a comma",
    "E17": "Emojis - remove from headings and bullets",
    "E18": "Curly quotes - use straight quotes",
    "E19": "Collaborative residue - delete “I hope this helps / let me know” chat lines",
    "E20": "Cutoff disclaimer - drop “as of my last training”; give a dated source or a fact",
    "E21": "Sycophancy - remove “great question / you’re absolutely right” openers",
    "E22": "Filler - tighten “in order to / due to the fact that” to “to / because”",
    "E23": "Excessive hedging - one qualifier at most; state the claim plainly",
    "E24": "Generic upbeat ending - replace with a concrete plan or specific next step",
}
