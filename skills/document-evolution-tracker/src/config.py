"""Configuration for the document-evolution-tracker.

A config points at a *version family* (a directory of versioned files, or an
explicit list of paths in order) plus the diff granularity and output
settings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Union

__all__ = [
    "Granularity",
    "EvoConfig",
    "load_config",
]


class Granularity:
    """Diff granularity levels."""

    LINE = "line"
    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"

    ALL = frozenset({LINE, PARAGRAPH, SENTENCE})


@dataclass
class EvoConfig:
    version: str
    tracking_id: str
    versions_dir: Path
    version_naming: str  # "timestamp" | "sequential"
    granularity: str
    out_dir: str

    def validate(self) -> None:
        if not self.tracking_id:
            raise ValueError("tracking_id is required")
        if self.granularity not in Granularity.ALL:
            raise ValueError(
                f"granularity must be one of {sorted(Granularity.ALL)}, got {self.granularity!r}"
            )
        if self.version_naming not in ("timestamp", "sequential"):
            raise ValueError("version_naming must be 'timestamp' or 'sequential'")


def load_config(source: Union[str, Path]) -> EvoConfig:
    """Load and validate an evolution-tracker config (YAML or JSON)."""
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml  # type: ignore[import-not-found]

        raw = yaml.safe_load(text) or {}
    else:
        raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("top-level config must be a mapping")

    cfg = EvoConfig(
        version=str(raw.get("version", "1.0.0")),
        tracking_id=str(raw.get("tracking_id", "")),
        versions_dir=Path(raw.get("versions_dir", "")),
        version_naming=str(raw.get("version_naming", "sequential")),
        granularity=str(raw.get("granularity", "paragraph")),
        out_dir=str(raw.get("out_dir", "./evolution")),
    )
    cfg.validate()
    return cfg
