"""Top-level orchestration for the document-evolution-tracker.

Ties together :mod:`versioning`, :mod:`align`, :mod:`lineage` and
:mod:`report` behind a single :func:`track_evolution` entry point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Union

from .align import align_versions
from .config import EvoConfig, load_config
from .diff_blocks import BlockDiff
from .lineage import build_lineage
from .report import write_timeline
from .versioning import Version, discover_versions

__all__ = [
    "EvolutionResult",
    "track_evolution",
    "run_config",
]


@dataclass
class EvolutionResult:
    tracking_id: str
    versions: List[str]
    diffs: List[BlockDiff]
    lineage: Dict[str, List]
    out_dir: Path

    def summary(self) -> Dict:
        return {
            "tracking_id": self.tracking_id,
            "versions": self.versions,
            "diff_count": len(self.diffs),
            "concepts": list(self.lineage.keys()),
            "out_dir": str(self.out_dir),
        }


def track_evolution(
    versions_dir: Path,
    naming: str = "sequential",
    granularity: str = "paragraph",
    concepts: List[str] | None = None,
) -> Dict:
    """Discover, align, and lineage-track a version family.

    Returns a dict with ``versions`` (ordered ids), ``texts``, ``diffs``,
    and ``lineage``.
    """
    versions = discover_versions(versions_dir, naming)
    texts = {v.version_id: v.path.read_text(encoding="utf-8") for v in versions}
    diffs = align_versions(versions, granularity)
    lineage = build_lineage(versions, texts, concepts=concepts, auto_detect_headings=concepts is None)
    return {
        "versions": [v.version_id for v in versions],
        "texts": texts,
        "diffs": diffs,
        "lineage": lineage,
    }


def run_config(config: Union[str, Path, EvoConfig], concepts: List[str] | None = None) -> EvolutionResult:
    """Load a config (path or object), run the tracker, and write the report."""
    if isinstance(config, EvoConfig):
        cfg = config
    else:
        cfg = load_config(config)

    result = track_evolution(
        versions_dir=cfg.versions_dir,
        naming=cfg.version_naming,
        granularity=cfg.granularity,
        concepts=concepts,
    )

    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_timeline(
        versions=result["versions"],
        diffs=result["diffs"],
        lineage=result["lineage"],
        out_dir=out_dir,
        tracking_id=cfg.tracking_id,
    )

    return EvolutionResult(
        tracking_id=cfg.tracking_id,
        versions=result["versions"],
        diffs=result["diffs"],
        lineage=result["lineage"],
        out_dir=out_dir,
    )
