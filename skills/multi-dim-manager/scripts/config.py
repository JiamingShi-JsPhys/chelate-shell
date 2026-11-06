"""Experiment configuration loading.

A full experiment config bundles the parameter space, the list of critical
paths to snapshot, the plugin command template, and runtime options. It can be
supplied as a ``.json``/``.yaml`` file or a raw dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .errors import ConfigError
from .param_space import ParamSpace, load_space


@dataclass
class Config:
    """Resolved experiment configuration."""

    space: ParamSpace
    critical_paths: list = field(default_factory=list)
    plugin_command: str = ""
    timeout: Optional[float] = None
    workdir: Path = field(default_factory=lambda: Path("./work"))
    output: Path = field(default_factory=lambda: Path("./output"))
    auto_rollback: bool = True

    def param_keys(self) -> list[str]:
        """Return the dimension names (used as report columns)."""
        return self.space.names


def _as_path(value: Any, default: str) -> Path:
    if value is None:
        return Path(default)
    return Path(str(value))


def load_config(source) -> Config:
    """Build a :class:`Config` from a file path, JSON string, or dict."""
    if isinstance(source, Config):
        return source
    if isinstance(source, dict):
        raw = source
    else:
        p = Path(str(source))
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read config {p}: {exc}") from exc
        if p.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise ConfigError(
                    "YAML config requires PyYAML: `pip install pyyaml`."
                ) from exc
            raw = yaml.safe_load(text)
        else:
            import json

            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"config is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")

    space = load_space(raw)
    plugin = raw.get("plugin", {}) or {}
    if isinstance(plugin, str):
        plugin_command = plugin
    else:
        plugin_command = str(plugin.get("command", ""))

    if not plugin_command:
        raise ConfigError("plugin command is required (plugin.command)")
    if "{OUT}" not in plugin_command:
        raise ConfigError("plugin command must contain the {OUT} placeholder")

    top_timeout = raw.get("timeout")
    if isinstance(plugin, dict):
        top_timeout = plugin.get("timeout", top_timeout)
    timeout = float(top_timeout) if top_timeout is not None else None

    critical = raw.get("critical_paths", []) or []
    if not isinstance(critical, list):
        raise ConfigError("critical_paths must be a list of relative paths")

    return Config(
        space=space,
        critical_paths=[str(c) for c in critical],
        plugin_command=plugin_command,
        timeout=timeout,
        workdir=_as_path(raw.get("workdir"), "./work"),
        output=_as_path(raw.get("output"), "./output"),
        auto_rollback=bool(raw.get("auto_rollback", True)),
    )
