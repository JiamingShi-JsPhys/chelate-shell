"""Shared bootstrap for skill run.py adapters.

Importing this module once adds the repo root to sys.path so that
`from contracts import ...` works, and exposes helpers that serialize a
GateResult to process/gates/<skill>_<ts>.json under a given workspace root.

Usage (inside a skill's root-level run.py):
    import bootstrap
    from contracts import pass_gate, unverified_gate

    def main() -> int:
        gate_path = bootstrap.write_gate(root, pass_gate(SKILL, reason=...))
        print(json.dumps({"gate": gate_path}))
        return 0

Caller: every skill's run.py imports this module.
No existing file in chelate-shell-v1.1.0/ serves this purpose.
User instruction: build the flat framework so each of the 14 skills can share
the same import + gate-write path.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def repo_root() -> str:
    """Return the chelate-shell repository root (parent of bootstrap.py)."""
    return _REPO_ROOT


def gates_dir(root: str) -> str:
    """Return process/gates under root, creating it if absent."""
    d = os.path.join(root, "process", "gates")
    os.makedirs(d, exist_ok=True)
    return d


def write_gate(root: str, gate) -> str:
    """Serialize `gate` to process/gates/<skill>_<ts>.json; return the path.

    The filename skill prefix comes from the GateResult.skill field, so the
    signature no longer needs a separate skill argument.
    """
    path = os.path.join(gates_dir(root),
                        f"{gate.skill}_{_ts()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gate.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def read_gate(path: str):
    """Load a GateResult previously written by write_gate()."""
    from contracts import GateResult
    return GateResult.from_json(path)


def results_dir(root: str) -> str:
    """Return results/ under root, creating it if absent."""
    d = os.path.join(root, "results")
    os.makedirs(d, exist_ok=True)
    return d


def write_json(dir_path: str, filename: str, payload) -> str:
    """Write `payload` as JSON into dir_path/filename; return the path."""
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def probe(module: str) -> bool:
    """Return True if `module` can be imported in this interpreter."""
    import importlib.util
    return importlib.util.find_spec(module) is not None


def probe_deps(modules) -> list:
    """Return the subset of `modules` that cannot be imported here."""
    return [m for m in modules if not probe(m)]


def emit_gate(root: str, skill: str, status: str, evidence_level: str,
              reason: str, artifacts=None) -> dict:
    """Write a GateResult and print the adapter's stdout JSON contract line.

    Returns the payload dict that was printed, so callers can inspect it.
    """
    from contracts import GateResult, GateStatus, EvidenceLevel
    gate = GateResult(skill=skill, status=GateStatus(status),
                      evidence_level=EvidenceLevel(evidence_level),
                      reason=reason, artifacts=list(artifacts or []))
    path = write_gate(root, gate)
    payload = {"gate": path, "artifacts": gate.artifacts,
               "status": gate.status.value,
               "evidence_level": gate.evidence_level.value,
               "reason": gate.reason}
    print(json.dumps(payload, ensure_ascii=False))
    return payload


def last_json(text: str):
    """Return the last JSON object embedded in `text` (or None)."""
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def tail(text: str, n: int = 2, limit: int = 240) -> str:
    """Last n non-empty lines of `text`, joined and length-capped."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return " | ".join(lines[-n:])[:limit]


@contextlib.contextmanager
def legacy_cwd(skill_root):
    """Temporarily chdir into the skill root.

    Legacy CLIs resolve their example configs and output directories
    relative to the skill directory (./config/examples/..., ./evolution).
    The adapter restores the previous cwd afterwards.
    """
    prev = os.getcwd()
    os.chdir(str(skill_root))
    try:
        yield
    finally:
        os.chdir(prev)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
