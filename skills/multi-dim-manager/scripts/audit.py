"""Append-only audit log and run metadata.

Every round produces one JSONL record carrying the parameter combination,
input/output hashes, timestamps, status, and the two snapshots (pre/post
manifests). Rollback actions are also recorded, so the whole experiment is
reproducible and auditable after the fact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import now_iso
from .snapshot import Manifest


@dataclass
class RoundRecord:
    """One audited round (or a rollback action)."""

    round_no: int
    status: str  # success|failed|error|pending|rolledback
    params: dict = field(default_factory=dict)
    input_hash: str = ""
    output_hash: str = ""
    timestamp: str = ""
    plugin_exit: int = -1
    out_file: str = ""
    snapshot_pre: dict = field(default_factory=dict)
    snapshot_post: dict = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "round_no": self.round_no,
            "status": self.status,
            "params": self.params,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "timestamp": self.timestamp,
            "plugin_exit": self.plugin_exit,
            "out_file": self.out_file,
            "snapshot_pre": self.snapshot_pre,
            "snapshot_post": self.snapshot_post,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoundRecord":
        return cls(
            round_no=int(data.get("round_no", 0)),
            status=str(data.get("status", "pending")),
            params=data.get("params", {}) or {},
            input_hash=data.get("input_hash", ""),
            output_hash=data.get("output_hash", ""),
            timestamp=data.get("timestamp", ""),
            plugin_exit=int(data.get("plugin_exit", -1)),
            out_file=data.get("out_file", ""),
            snapshot_pre=data.get("snapshot_pre", {}) or {},
            snapshot_post=data.get("snapshot_post", {}) or {},
            note=data.get("note", ""),
        )


class AuditLog:
    """An append-only JSONL log of round records."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def record(self, rec: RoundRecord) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

    def entries(self) -> List[RoundRecord]:
        out: List[RoundRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(RoundRecord.from_dict(json.loads(line)))
        return out

    def rounds(self) -> List[RoundRecord]:
        """Return only the per-round records (exclude rollback actions)."""
        return [r for r in self.entries() if r.status != "rolledback"]

    def get(self, round_no: int) -> Optional[RoundRecord]:
        for r in self.rounds():
            if r.round_no == round_no:
                return r
        return None

    def last_successful(self) -> Optional[RoundRecord]:
        succ: Optional[RoundRecord] = None
        for r in self.rounds():
            if r.status == "success":
                succ = r
        return succ


def write_metadata(path: Path, meta: dict) -> None:
    """Write the run metadata JSON (space, plugin, timing)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
