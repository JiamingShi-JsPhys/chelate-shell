"""ai-trace-remover core engine.

Pure standard library. Exposes a single :func:`scan` entry that returns a
:class:`TraceReport`; the CLI in :mod:`src.cli` renders it as Markdown / JSON.

Layered checks (cheapest and most decisive first):

1. **Lexical** -- regex hits on the original pattern library
   (``patterns_zh`` / ``patterns_en``), with head/tail position weighting and
   repeat decay.
2. **Structural** -- em-dash / exclamation / number / first-person / emoji
   counts (Chinese prose only, when the text is long enough).
3. **Hard-ban** -- the "成稿硬禁令" from ``references/ai-patterns-zh.md``;
   any hit is a blocking failure, not a score penalty.
4. **Sound** -- the "声音五条" from ``references/revision.md``; reported as
   pass/fail lines the agent must answer by hand (the script cannot judge).

``score`` is the 0-100 human index for Chinese prose (higher = more human).
English prose reports an ``ai_taste_score`` instead (higher = more AI).
"""

from .engine import TraceReport, Hit, scan, grade_zh, grade_en
from . import patterns_zh, patterns_en, hard_bans, sound_rules

__all__ = [
    "TraceReport",
    "Hit",
    "scan",
    "grade_zh",
    "grade_en",
    "patterns_zh",
    "patterns_en",
    "hard_bans",
    "sound_rules",
]
