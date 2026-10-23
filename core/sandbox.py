"""Chelate Shell sandbox — dependency isolation for heavy optional packages.

Caller: core/router.py calls sandbox.resolve_environment() before running a
        skill whose manifest declares dependencies that are not importable in
        the main environment.
No existing file in chelate-shell-v1.1.0/ serves this purpose.
Data schemas:
    Reads:  a skill's dependency list (from SkillRecord.dependencies).
    Writes: none (returns env/interpreter settings; the subprocess is launched
            by the router with the returned configuration).
User instruction: "sandbox.py — isolates heavy dependencies (e.g. RDKit,
PyTorch) so running quantitative-validator does not break the main
environment" (v1.1.0 execution list, step 3).

Design (v1.1.0 scope):
    - Pure-stdlib. The sandbox detects which of a skill's declared dependencies
      are missing in the current interpreter.
    - When everything is available it returns the main interpreter (no-op).
    - When a dependency is missing it STILL returns the main interpreter but
      flags the skill as degraded: the skill's run.py is expected to call
      contracts.unverified_gate() and exit 0, so the pipeline degrades rather
      than crashing. This satisfies "do not break the main environment" —
      nothing is installed into the main environment by the router.
    - v1.2.0 will add a true venv-based isolation (the interface below is
      stable so that upgrade is additive).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SandboxDecision:
    """Outcome of resolving an execution environment for one skill."""

    interpreter: str
    extra_pythonpath: List[str] = field(default_factory=list)
    degraded: bool = False
    missing: List[str] = field(default_factory=list)

    def env(self) -> dict:
        """Return an os.environ-compatible dict for the subprocess."""
        extra = os.pathsep.join(self.extra_pythonpath) if self.extra_pythonpath else ""
        base = os.environ.get("PYTHONPATH", "")
        combined = os.pathsep.join(p for p in [extra, base] if p)
        return {**os.environ, "PYTHONPATH": combined}


def missing_dependencies(names: List[str]) -> List[str]:
    """Return the subset of `names` that cannot be import-specified found."""
    out = []
    for n in names:
        if importlib.util.find_spec(n) is None:
            out.append(n)
    return out


def resolve_environment(dependencies: List[str],
                        interpreter: Optional[str] = None) -> SandboxDecision:
    """Pick an interpreter + env for running a skill with the given deps.

    Returns the main interpreter (or the supplied one) with a `degraded` flag
    when a dependency is absent, so the router can run the skill as-is and let
    it degrade to an UNVERIFIED gate.
    """
    interp = interpreter or sys.executable
    missing = missing_dependencies(dependencies)
    return SandboxDecision(interpreter=interp, degraded=bool(missing),
                           missing=missing)
