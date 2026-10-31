"""Deterministic audit logging and seed handling for reproducibility.

Every pipeline step is logged with an input / output hash so a run can be
reproduced bit-for-bit (modulo R's own stochastic bootstrap, which is
controlled via a fixed seed).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "hash_payload",
    "log_step",
    "set_seed",
    "now_iso",
]


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string (second precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_payload(payload: Any) -> str:
    """Stable SHA-256 hash of a JSON-serialisable payload.

    Keys are sorted so ordering never changes the digest.
    """
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def set_seed(seed: int) -> None:
    """Seed the Python / NumPy / R random generators for reproducibility."""
    random.seed(seed)
    os.environ["R_SEED"] = str(seed)
    try:
        import numpy as np  # type: ignore[import-not-found]

        np.random.seed(seed)
    except ImportError:  # pragma: no cover - numpy optional
        pass


def log_step(step: str, payload: Dict[str, Any], result: Any, log_path: Path) -> Dict[str, Any]:
    """Append one audit entry for a finished step and return it.

    The entry carries the step name, wall-clock timestamp, the configured
    seed, and SHA-256 digests of both the input payload and the result.
    """
    entry = {
        "step": step,
        "timestamp": now_iso(),
        "seed": payload.get("seed"),
        "input_hash": hash_payload(payload),
        "output_hash": hash_payload(result),
    }
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_audit_log(log_path: Path) -> Optional[list]:
    """Read back an audit log as a list of dicts (empty if missing)."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    out = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out
