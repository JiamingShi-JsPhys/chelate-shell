"""Loader for a skill's assets/config.yaml.

PyYAML is an optional dependency: when it is importable the file is parsed
with it; otherwise a small built-in parser handles the flat subset the
chelate config files use (scalars, inline lists, one level of nesting).
A missing file or a parse problem degrades to the caller's defaults —
configuration must never crash a pipeline.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional


def _mini_parse(text: str) -> Dict[str, Any]:
    """Parse the flat YAML subset: `key: value`, inline `[a, b]` lists,
    and one nesting level via two-space indentation."""
    root: Dict[str, Any] = {}
    stack = [(-1, root)]
    for raw in (text or "").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1] if stack else root
        if value == "":
            child: Dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _scalar(value)
    return root


def _scalar(value: str) -> Any:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_scalar(v.strip()) for v in inner.split(",") if v.strip()] if inner else []
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~", ""):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def load_config(skill_root: str, name: str = "config.yaml",
                subdir: str = "assets") -> Dict[str, Any]:
    """Load <skill_root>/<subdir>/<name>; return {} when absent or unreadable.

    Never raises: a broken config degrades to defaults by design.
    """
    path = os.path.join(skill_root, subdir, name)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return {}
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
    except ImportError:
        data = _mini_parse(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def merge(defaults: Optional[Dict[str, Any]],
          override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Shallow-merge `override` onto `defaults` (None-tolerant)."""
    out = dict(defaults or {})
    out.update(override or {})
    return out


def config_path(skill_root: str, name: str = "config.yaml",
                subdir: str = "assets") -> str:
    """Path of the config file (may not exist)."""
    return os.path.join(skill_root, subdir, name)
