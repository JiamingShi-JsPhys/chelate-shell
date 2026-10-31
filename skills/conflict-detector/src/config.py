"""Configuration loader for the conflict-detector.

Defines the three detection levels (entity / clause / argument) and the
document source specification. Pure standard library; YAML is optional.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Union

__all__ = [
    "DocumentSource",
    "ConflictDetectorConfig",
    "load_config",
]


@dataclass
class DocumentSource:
    """Where to read a document from (a path, inline text, or inline JSON)."""

    id: str
    kind: str  # "path" | "text" | "json"
    value: Union[str, List[Dict[str, str]]] = ""

    def load(self) -> str:
        """Return the document content as text."""
        if self.kind == "path":
            return Path(str(self.value)).read_text(encoding="utf-8")
        if self.kind == "text":
            return str(self.value)
        if self.kind == "json":
            return json.dumps(self.value, ensure_ascii=False)
        raise ValueError(f"unknown source kind: {self.kind}")


@dataclass
class ConflictDetectorConfig:
    """Top-level configuration for a conflict-detection run."""

    version: str
    run_id: str
    documents: List[DocumentSource]
    levels: List[str] = field(default_factory=lambda: ["entity", "clause", "argument"])
    numeric_tolerance: float = 1e-6
    output_dir: str = "./conflicts"

    def validate(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if not self.documents:
            raise ValueError("at least one document source is required")
        valid = {"entity", "clause", "argument"}
        for lvl in self.levels:
            if lvl not in valid:
                raise ValueError(f"unknown level '{lvl}'; valid: {sorted(valid)}")


def _parse_sources(raw: Any) -> List[DocumentSource]:
    if raw is None:
        return []
    out: List[DocumentSource] = []
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            out.append(DocumentSource(id=f"doc{i}", kind="path", value=entry))
        elif isinstance(entry, dict):
            out.append(
                DocumentSource(
                    id=str(entry.get("id", f"doc{i}")),
                    kind=str(entry.get("kind", "path")),
                    value=entry.get("value", entry.get("path", "")),
                )
            )
        else:
            raise ValueError(f"document source {i} must be a str or mapping")
    return out


def load_config(source: Union[str, Path]) -> ConflictDetectorConfig:
    """Load and validate a conflict-detector config from YAML or JSON."""
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

    cfg = ConflictDetectorConfig(
        version=str(raw.get("version", "1.0.0")),
        run_id=str(raw.get("run_id", "")),
        documents=_parse_sources(raw.get("documents")),
        levels=[str(l) for l in (raw.get("levels") or ["entity", "clause", "argument"])],
        numeric_tolerance=float(raw.get("numeric_tolerance", 1e-6)),
        output_dir=str(raw.get("output_dir", "./conflicts")),
    )
    cfg.validate()
    return cfg
