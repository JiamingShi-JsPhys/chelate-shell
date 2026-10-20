"""Top-level orchestration: load config, extract facts, detect, report.

This module ties together :mod:`extract`, :mod:`rules` and :mod:`report`
behind a single :func:`detect_conflicts` entry point used by both the CLI
and the tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Union

from .config import ConflictDetectorConfig, load_config
from .detect import Conflict
from .extract import Fact, extract_facts
from .report import write_report
from .rules import run_detection

__all__ = ["DetectionResult", "detect_conflicts", "run_config"]


@dataclass
class DetectionResult:
    """Outcome of a conflict-detection run."""

    run_id: str
    documents: List[str]
    conflicts: List[Conflict]
    counts: Dict[str, int]

    def to_summary(self) -> Dict:
        return {
            "run_id": self.run_id,
            "documents": self.documents,
            "total_conflicts": len(self.conflicts),
            "by_level": self.counts,
        }


def detect_conflicts(
    documents: Dict[str, str],
    levels: List[str],
    key_aliases: Dict[str, str],
    numeric_tolerance: float = 1e-6,
) -> List[Conflict]:
    """Extract facts from each document and run cross-document detection.

    Parameters
    ----------
    documents:
        Mapping of document id to its raw content (text or JSON string).
    levels:
        Detection levels to run (subset of entity / clause / argument).
    key_aliases:
        Optional alias -> canonical-key map for :mod:`normalize`.
    numeric_tolerance:
        Absolute tolerance for numeric comparisons.
    """
    facts_by_doc = {
        doc_id: extract_facts(doc_id, content) for doc_id, content in documents.items()
    }
    return run_detection(facts_by_doc, levels, key_aliases, numeric_tolerance)


def run_config(
    config: Union[str, Path, ConflictDetectorConfig],
    key_aliases: Dict[str, str] | None = None,
    fmt: str = "json",
) -> DetectionResult:
    """Load a config (path or object), run detection, and write the report."""
    if isinstance(config, ConflictDetectorConfig):
        cfg = config
    else:
        cfg = load_config(config)

    documents: Dict[str, str] = {}
    for src in cfg.documents:
        documents[src.id] = src.load()

    conflicts = detect_conflicts(
        documents,
        cfg.levels,
        key_aliases or {},
        cfg.numeric_tolerance,
    )

    counts: Dict[str, int] = {"entity": 0, "clause": 0, "argument": 0}
    for c in conflicts:
        counts[c.level] = counts.get(c.level, 0) + 1

    result = DetectionResult(
        run_id=cfg.run_id,
        documents=[s.id for s in cfg.documents],
        conflicts=conflicts,
        counts=counts,
    )
    write_report(conflicts, cfg.output_dir, fmt=fmt, run_id=cfg.run_id)
    return result
