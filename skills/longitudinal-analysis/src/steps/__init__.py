"""Pipeline step modules.

Each submodule exposes a single :func:`run` function with the signature::

    def run(df, config, cfg) -> Path | list[Path]

so the orchestrator can dispatch uniformly by step type.
"""

from . import descriptive, lmm, mediation, manipulation, sensitivity

__all__ = [
    "descriptive",
    "lmm",
    "mediation",
    "manipulation",
    "sensitivity",
]
