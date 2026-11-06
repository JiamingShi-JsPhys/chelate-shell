"""Version alignment: order a version family and compute pairwise diffs.

Given an ordered list of :class:`versioning.Version` records, this module
reads each file and produces the sequence of pairwise :class:`BlockDiff`
results that make up the evolution timeline.
"""

from __future__ import annotations

from typing import List

from .diff_blocks import BlockDiff, diff_blocks
from .versioning import Version

__all__ = [
    "align_versions",
]


def align_versions(versions: List[Version], granularity: str = "paragraph") -> List[BlockDiff]:
    """Return the pairwise diffs between consecutive versions.

    The input list must be in the intended evolution order (ascending).
    A family of N versions yields N-1 diffs.
    """
    if len(versions) < 2:
        return []
    diffs: List[BlockDiff] = []
    for old, new in zip(versions, versions[1:]):
        old_text = old.path.read_text(encoding="utf-8")
        new_text = new.path.read_text(encoding="utf-8")
        diffs.append(
            diff_blocks(
                old_text,
                new_text,
                granularity=granularity,
                old_label=old.label,
                new_label=new.label,
            )
        )
    return diffs
