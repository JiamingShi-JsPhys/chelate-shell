"""Chelate Shell contracts — ActionManifest, the only thing a run may submit.

Caller: `core/runtime.py` (`Runtime.submit`), and through it every surface —
        MCP server, hooks, recipes. The broker accepts a manifest and nothing
        else, so this module is the entire vocabulary of "please publish".
Data schemas:
    Reads:  none (pure definition module).
    Writes: none. The caller serialises `to_dict()`.
Design: pure stdlib, fail-closed validation. `problems()` returns a list;
        empty means publishable, any entry means refuse. A manifest never
        repairs itself — a field that cannot be understood is a reason to
        stop, not a default to fall back to.

Fields:
    action:            presently only ``publish_artifact_set``. A broker that
                       does not recognise the verb must refuse it.
    workspace:         absolute path, and the real one. A manifest naming a
                       symlinked workspace is refused, because "the same
                       workspace" must not be two different directories.
    snapshot_id:       content id of the frozen inputs (``.chelate/snapshots``),
                       or empty when the run declared no inputs.
    inputs/outputs:    [{path, sha256}] with workspace-relative paths. Outputs
                       are what the human was shown before approving; the
                       broker re-hashes them and compares.
    skill_lock_sha256: digest of the skill set that produced the outputs, so a
                       different skill version cannot inherit an approval.
    runtime:           ``policy`` or ``broker``. A manifest approved under one
                       runtime is not silently honoured under the other.
    broker_version:    version that will consume the manifest (empty in policy
                       mode).
    expires_at:        ISO-8601 UTC; an expired manifest is refused.
    nonce:             the approval nonce this manifest belongs to.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KNOWN_ACTIONS = ("publish_artifact_set",)
KNOWN_RUNTIMES = ("policy", "broker")
_HEX = set("0123456789abcdef")
_WINDOWS_DEVICES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)})


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and set(value.lower()) <= _HEX


def _check_rel_path(path: str) -> Optional[str]:
    """Return why *path* is not a safe workspace-relative name, or None."""
    if not path or not isinstance(path, str):
        return "empty path"
    if os.path.isabs(path) or (len(path) > 1 and path[1] == ":"):
        return f"{path!r} is absolute; manifest paths are workspace-relative"
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        return f"{path!r} escapes the workspace"
    if any(part == "" for part in parts):
        return f"{path!r} has an empty segment"
    # Windows reads ":" as an alternate-data-stream separator and a bare
    # device name as a device rather than a file. "report.md:evil" and "NUL"
    # both end up somewhere other than the workspace, and neither is a file
    # this tool ever means to publish.
    if ":" in path:
        return f"{path!r} contains ':', a stream separator on Windows"
    for part in parts:
        if part.split(".", 1)[0].strip().lower() in _WINDOWS_DEVICES:
            return f"{path!r} names a Windows device"
    return None


def _parse_instant(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass
class ActionManifest:
    action: str = "publish_artifact_set"
    workspace: str = ""
    snapshot_id: str = ""
    inputs: List[Dict[str, str]] = field(default_factory=list)
    outputs: List[Dict[str, str]] = field(default_factory=list)
    skill_lock_sha256: str = ""
    runtime: str = "policy"
    broker_version: str = ""
    expires_at: str = ""
    nonce: str = ""

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "workspace": self.workspace,
            "snapshot_id": self.snapshot_id,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "skill_lock_sha256": self.skill_lock_sha256,
            "runtime": self.runtime,
            "broker_version": self.broker_version,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionManifest":
        data = data or {}
        return cls(
            action=str(data.get("action", "publish_artifact_set")),
            workspace=str(data.get("workspace", "")),
            snapshot_id=str(data.get("snapshot_id", "")),
            inputs=[dict(item) for item in data.get("inputs") or []],
            outputs=[dict(item) for item in data.get("outputs") or []],
            skill_lock_sha256=str(data.get("skill_lock_sha256", "")),
            runtime=str(data.get("runtime", "policy")),
            broker_version=str(data.get("broker_version", "")),
            expires_at=str(data.get("expires_at", "")),
            nonce=str(data.get("nonce", "")),
        )

    # -- validation -------------------------------------------------------
    def problems(self, now: Optional[datetime] = None) -> List[str]:
        """Every reason this manifest must be refused. Empty == publishable."""
        found: List[str] = []

        if self.action not in KNOWN_ACTIONS:
            found.append(f"unknown action {self.action!r}")
        if self.runtime not in KNOWN_RUNTIMES:
            found.append(f"unknown runtime {self.runtime!r}")

        if not self.workspace or not os.path.isabs(self.workspace):
            found.append("workspace must be an absolute path")
        elif not os.path.isdir(self.workspace):
            found.append(f"workspace {self.workspace!r} does not exist")
        else:
            # A symlinked workspace is two directories wearing one name; the
            # broker must be able to say which one it is publishing into.
            real = os.path.realpath(self.workspace)
            if os.path.normcase(real) != os.path.normcase(
                    os.path.abspath(self.workspace)):
                found.append(f"workspace {self.workspace!r} is not its real path")

        if self.snapshot_id and (
                len(self.snapshot_id) != 16
                or set(self.snapshot_id.lower()) - _HEX):
            found.append(f"snapshot_id {self.snapshot_id!r} is not 16 hex characters")

        if not self.outputs:
            found.append("a publish action with no outputs publishes nothing")

        for label, entries in (("input", self.inputs), ("output", self.outputs)):
            for index, entry in enumerate(entries):
                path = str(entry.get("path", ""))
                digest = str(entry.get("sha256", ""))
                why = _check_rel_path(path)
                if why:
                    found.append(f"{label}[{index}]: {why}")
                if not _is_sha256(digest):
                    found.append(f"{label}[{index}]: sha256 is not 64 hex characters")

        if self.expires_at:
            instant = _parse_instant(self.expires_at)
            if instant is None:
                found.append(f"expires_at {self.expires_at!r} is not ISO-8601")
            elif instant <= (now or datetime.now(timezone.utc)):
                found.append(f"manifest expired at {self.expires_at}")

        if not self.nonce:
            found.append("nonce is empty; an approval must be identifiable")

        return found

    def digest(self) -> str:
        """Canonical digest of the manifest — sorted-key JSON, not repr().

        This is what an approval is bound to and what the broker recomputes
        from the body it received, so it must depend on the values only and
        not on dict insertion order or on Python's repr format.
        """
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=True,
                             separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_workspace(cls, workspace: str, *, runtime: str = "policy",
                       broker_version: str = "",
                       skill_lock_sha256: str = "",
                       ttl_seconds: int = 900,
                       inputs: Optional[List[Dict[str, str]]] = None,
                       snapshot_id: str = "") -> "ActionManifest":
        """Describe exactly the bytes under ``process/`` at this moment.

        The set is enumerated once and never widened: what the human approves
        is this list, and what gets published is this list. Links are skipped
        rather than declared, because promotion refuses them anyway.
        """
        root = os.path.abspath(workspace)
        base = os.path.join(root, "process")
        outputs: List[Dict[str, str]] = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    continue
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                with open(full, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
                outputs.append({"path": rel, "sha256": digest})
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        return cls(
            action="publish_artifact_set",
            workspace=root,
            snapshot_id=snapshot_id,
            inputs=list(inputs or []),
            outputs=outputs,
            skill_lock_sha256=skill_lock_sha256,
            runtime=runtime,
            broker_version=broker_version,
            expires_at=expires.isoformat().replace("+00:00", "Z"),
            nonce=secrets.token_hex(16),
        )
