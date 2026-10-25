"""Parse and expand a multi-dimensional parameter space.

A *parameter space* is an ordered list of dimensions. Each dimension has a
name and a list of candidate values. The space expands to the Cartesian
product of all dimensions, yielding one concrete parameter combination per
round.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from .errors import ConfigError


@dataclass(frozen=True)
class Dimension:
    """A single iterable axis of the parameter space."""

    name: str
    values: tuple

    def __post_init__(self) -> None:
        if not self.name:
            raise ConfigError("a dimension must have a non-empty name")
        if not self.values:
            raise ConfigError(f"dimension {self.name!r} has no values")


@dataclass
class ParamSpace:
    """The full set of dimensions, expandable to concrete combinations."""

    dimensions: tuple

    @property
    def names(self) -> list[str]:
        """Return the dimension names in declaration order."""
        return [d.name for d in self.dimensions]

    @property
    def size(self) -> int:
        """Return the total number of combinations (Cartesian product)."""
        total = 1
        for dim in self.dimensions:
            total *= len(dim.values)
        return total

    def combinations(self) -> Iterator[dict]:
        """Yield every parameter combination as a ``name -> value`` dict."""
        names = [d.name for d in self.dimensions]
        value_lists = [list(d.values) for d in self.dimensions]
        for combo in itertools.product(*value_lists):
            yield dict(zip(names, combo))


def _load_raw(source: Path) -> dict:
    """Read a JSON or YAML file into a dict.

    YAML is supported only when PyYAML is importable; JSON needs no extra
    dependency. This keeps the skill dependency-free by default.
    """
    text = Path(source).read_text(encoding="utf-8")
    suffix = Path(source).suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ConfigError(
                "YAML config requires PyYAML: `pip install pyyaml` "
                "(or use a .json config to stay dependency-free)."
            ) from exc
        return yaml.safe_load(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config is not valid JSON: {exc}") from exc


def _space_from_raw(raw: dict) -> ParamSpace:
    """Build a :class:`ParamSpace` from a parsed config dict."""
    space_raw = raw.get("param_space", raw)
    dims_raw = space_raw.get("dimensions")
    if not isinstance(dims_raw, list) or not dims_raw:
        raise ConfigError("param_space.dimensions must be a non-empty list")
    dims = []
    for d in dims_raw:
        if not isinstance(d, dict) or "name" not in d:
            raise ConfigError("each dimension must be a mapping with a 'name'")
        values = d.get("values", [])
        if not isinstance(values, (list, tuple)) or not values:
            raise ConfigError(
                f"dimension {d['name']!r} must have a non-empty 'values' list"
            )
        dims.append(Dimension(name=str(d["name"]), values=tuple(values)))
    return ParamSpace(dimensions=tuple(dims))


def load_space(source) -> ParamSpace:
    """Load a parameter space from a path, a raw dict, or a JSON string.

    Args:
        source: A :class:`~pathlib.Path`/str to a ``.json``/``.yaml`` file,
            a parsed ``dict``, or a JSON ``str``.

    Returns:
        The constructed :class:`ParamSpace`.
    """
    if isinstance(source, ParamSpace):
        return source
    if isinstance(source, dict):
        raw = source
    elif isinstance(source, str):
        try:
            raw = json.loads(source)
        except json.JSONDecodeError:
            raw = _load_raw(Path(source))
    else:
        raw = _load_raw(Path(source))
    return _space_from_raw(raw)


def expand(source) -> list[dict]:
    """Convenience helper: return all combinations as a list of dicts."""
    return list(load_space(source).combinations())
