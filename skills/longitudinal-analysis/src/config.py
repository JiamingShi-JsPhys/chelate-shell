"""Configuration dataclasses and loader for the longitudinal-analysis pipeline.

The config is a YAML file (JSON also accepted via :func:`load_config`). It
describes an input dataset, the column layout (subject / time / condition
columns), the ordered list of analysis steps, and the output locations.

Pure standard library; PyYAML is used only when the file ends in ``.yaml`` /
``.yml``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Union

__all__ = [
    "Step",
    "AnalysisConfig",
    "load_config",
]

# Valid step types understood by the pipeline.
VALID_STEP_TYPES = frozenset(
    {"descriptive", "anova", "lmm", "mediation", "sensitivity"}
)


@dataclass
class Step:
    """A single analysis step in the pipeline."""

    name: str
    type: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def validate(self) -> None:
        if not self.name:
            raise ValueError("step name is required")
        if self.type not in VALID_STEP_TYPES:
            raise ValueError(
                f"step '{self.name}': unknown type '{self.type}'; "
                f"valid types: {sorted(VALID_STEP_TYPES)}"
            )


@dataclass
class AnalysisConfig:
    """Top-level analysis configuration."""

    version: str
    analysis_id: str
    data_input: Path
    id_column: str
    time_column: str
    condition_columns: List[str]
    steps: List[Step]
    outputs: Dict[str, str]
    seed: int = 42

    def validate(self) -> None:
        if not self.analysis_id:
            raise ValueError("analysis_id is required")
        if not self.id_column:
            raise ValueError("id_column is required")
        if not self.time_column:
            raise ValueError("time_column is required")
        for step in self.steps:
            step.validate()
        for key in ("tables", "figures", "logs"):
            if key not in self.outputs:
                raise ValueError(f"outputs.{key} is required")

    def step(self, name: str) -> Step:
        for s in self.steps:
            if s.name == name:
                return s
        raise KeyError(f"no step named '{name}'")


def _parse_steps(raw: Any) -> List[Step]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("steps must be a list of {name, type, config}")
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"step entry must be a mapping, got {type(entry).__name__}")
        out.append(
            Step(
                name=str(entry.get("name", "")),
                type=str(entry.get("type", "")),
                config=dict(entry.get("config", {}) or {}),
                enabled=bool(entry.get("enabled", True)),
            )
        )
    return out


def load_config(source: Union[str, Path]) -> AnalysisConfig:
    """Load and validate an analysis config from a file path.

    Parameters
    ----------
    source:
        Path to a YAML or JSON config file.

    Returns
    -------
    AnalysisConfig
        A validated configuration object.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the config is malformed.
    """

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

    data = raw.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("'data' section must be a mapping")

    out_dir = raw.get("outputs", {})
    if not isinstance(out_dir, dict):
        raise ValueError("'outputs' section must be a mapping")

    cfg = AnalysisConfig(
        version=str(raw.get("version", "1.0.0")),
        analysis_id=str(raw.get("analysis_id", "")),
        data_input=Path(data.get("input", "")),
        id_column=str(data.get("id_column", "")),
        time_column=str(data.get("time_column", "")),
        condition_columns=[str(c) for c in (data.get("condition_columns") or [])],
        steps=_parse_steps(raw.get("steps")),
        outputs=dict(out_dir),
        seed=int(raw.get("seed", 42)),
    )
    cfg.validate()
    return cfg
