"""Unified debug logging for every Chelate Shell entry point.

One switch, two shapes:

    CHELATE_DEBUG=1   environment variable; inherited by skill subprocesses,
                      so it reaches every adapter and legacy CLI
    --debug           CLI flag on cli.py and core/router.py; calls enable()
                      so child processes inherit the same switch

All debug output goes to stderr with a "[chelate:debug]" prefix, so it can
never be confused with the single stdout JSON line of the adapter contract.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

ENV_VAR = "CHELATE_DEBUG"
PREFIX = "[chelate:debug]"

_TRUTHY = {"1", "true", "yes", "on"}


def enabled(env: Optional[dict] = None) -> bool:
    """True when the debug switch is on in `env` (default: os.environ)."""
    env = os.environ if env is None else env
    return str(env.get(ENV_VAR, "")).strip().lower() in _TRUTHY


def enable(env: Optional[dict] = None) -> None:
    """Turn the switch on (mutates os.environ unless `env` is given)."""
    if env is None:
        os.environ[ENV_VAR] = "1"
    else:
        env[ENV_VAR] = "1"


def flag(flag_value: bool, env: Optional[dict] = None) -> bool:
    """Combine a --debug CLI flag with the environment variable.

    When the flag is set it also enables the environment variable, so
    subprocesses spawned later inherit debug logging.
    """
    if flag_value:
        enable(env)
        return True
    return enabled(env)


def log(message: str, env: Optional[dict] = None) -> None:
    """Print one debug line to stderr when the switch is on."""
    if enabled(env):
        print(f"{PREFIX} {message}", file=sys.stderr)
