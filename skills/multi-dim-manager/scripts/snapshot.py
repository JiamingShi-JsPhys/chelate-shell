"""Content-addressed snapshots of declared critical paths.

The manager does NOT snapshot the whole working directory. Instead the user
declares a list of *critical paths* (the files whose integrity matters, e.g.
cleaned CSVs, model results). For each path we store its content under a
content-addressed store (``<hash>`` files) and record a manifest mapping
relative path -> content hash. Unchanged files are stored only once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from .common import sha256
from .errors import ManagerError


@dataclass
class Manifest:
    """A map of critical-path -> content hash for one round/phase."""

    round_no: int
    phase: str  # "pre" | "post"
    files: Dict[str, str] = field(default_factory=dict)
    store_dir: Path = field(default_factory=Path)

    def to_dict(self) -> dict:
        return {
            "round_no": self.round_no,
            "phase": self.phase,
            "files": dict(self.files),
        }

    @classmethod
    def from_dict(cls, data: dict, store_dir: Path) -> "Manifest":
        return cls(
            round_no=int(data.get("round_no", 0)),
            phase=str(data.get("phase", "post")),
            files=dict(data.get("files", {})),
            store_dir=Path(store_dir),
        )


def _store(store_dir: Path, data: bytes) -> str:
    """Store *data* content-addressed; return its hash."""
    h = sha256(data)
    target = Path(store_dir) / h
    if not target.exists():
        target.write_bytes(data)
    return h


def snapshot(
    workdir: Path,
    critical_paths: list,
    store_dir: Path,
    round_no: int,
    phase: str,
) -> Manifest:
    """Snapshot every existing critical path; store content-addressed.

    Missing paths are silently skipped (the plugin may not have produced them
    yet), so a manifest only lists files that actually existed.
    """
    workdir = Path(workdir)
    store_dir = Path(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(round_no=round_no, phase=phase, store_dir=store_dir)
    for rel in critical_paths:
        p = workdir / rel
        if p.exists() and p.is_file():
            h = _store(store_dir, p.read_bytes())
            manifest.files[str(rel)] = h
    return manifest


def restore(manifest: Manifest, target_dir: Path) -> Path:
    """Restore a manifest's files into *target_dir* (created if missing).

    Returns the resolved target directory. The operation is additive: it only
    writes the files named in the manifest and never deletes others.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    for rel, h in manifest.files.items():
        src = Path(manifest.store_dir) / h
        if not src.exists():
            raise ManagerError(
                f"snapshot content missing for {rel!r} (hash {h}); the store "
                "may have been deleted or tampered with."
            )
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    return target
