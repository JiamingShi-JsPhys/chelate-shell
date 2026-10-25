"""Granular document diffing: split into blocks and produce add/remove/modify.

The diff is *structural*: it operates on a list of blocks (lines / paragraphs
/ sentences) and reports which blocks were added, removed, or changed between
two versions. ``difflib`` is used for the sequence alignment; no external
library.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List

from .config import Granularity

__all__ = [
    "Change",
    "BlockDiff",
    "split_blocks",
    "diff_blocks",
]

_WS = re.compile(r"\s+")


@dataclass
class Change:
    """A single block-level change between two versions."""

    tag: str  # "added" | "removed" | "modified"
    new_block: str = ""
    old_block: str = ""

    def to_dict(self) -> Dict:
        return {"tag": self.tag, "new_block": self.new_block, "old_block": self.old_block}


@dataclass
class BlockDiff:
    """The full diff result between two versions."""

    old_label: str
    new_label: str
    changes: List[Change] = field(default_factory=list)
    added: int = 0
    removed: int = 0
    modified: int = 0

    def to_dict(self) -> Dict:
        return {
            "old": self.old_label,
            "new": self.new_label,
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
            "changes": [c.to_dict() for c in self.changes],
        }


def _split_line(text: str) -> List[str]:
    return [ln.rstrip() for ln in text.splitlines() if ln.strip()]


def _split_paragraph(text: str) -> List[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts


def _split_sentence(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def split_blocks(text: str, granularity: str = Granularity.PARAGRAPH) -> List[str]:
    """Split a document into blocks at the requested granularity."""
    g = granularity
    if g == Granularity.LINE:
        return _split_line(text)
    if g == Granularity.SENTENCE:
        return _split_sentence(text)
    return _split_paragraph(text)


def _normalize(block: str) -> str:
    """Whitespace-collapse a block for stable comparison."""
    return _WS.sub(" ", block.strip())


def diff_blocks(
    old_text: str,
    new_text: str,
    granularity: str = Granularity.PARAGRAPH,
    old_label: str = "old",
    new_label: str = "new",
) -> BlockDiff:
    """Diff two documents at the given granularity.

    Returns a :class:`BlockDiff` whose ``changes`` list records, per aligned
    block, whether it was added, removed, or modified (a block that is
    neither identical nor present in the other side is treated as modified
    when the alignment pairs it with a differing block).
    """
    old_blocks = split_blocks(old_text, granularity)
    new_blocks = split_blocks(new_text, granularity)

    old_norm = [_normalize(b) for b in old_blocks]
    new_norm = [_normalize(b) for b in new_blocks]

    sm = difflib.SequenceMatcher(a=old_norm, b=new_norm, autojunk=False)
    changes: List[Change] = []
    added = removed = modified = 0

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if op == "delete":
            for b in old_blocks[i1:i2]:
                changes.append(Change("removed", old_block=b))
                removed += 1
        elif op == "insert":
            for b in new_blocks[j1:j2]:
                changes.append(Change("added", new_block=b))
                added += 1
        elif op == "replace":
            old_chunk = old_blocks[i1:i2]
            new_chunk = new_blocks[j1:j2]
            for b in old_chunk:
                changes.append(Change("removed", old_block=b))
                removed += 1
            for b in new_chunk:
                changes.append(Change("added", new_block=b))
                added += 1
            modified = max(len(old_chunk), len(new_chunk))

    return BlockDiff(old_label, new_label, changes, added, removed, modified)
