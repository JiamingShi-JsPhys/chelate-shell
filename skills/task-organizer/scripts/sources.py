"""sources.py -- file provenance manifest.

Why this exists
---------------
"Which folder does a file belong in?" cannot be answered from the file
*name*. A file the user dropped in and a file the assistant fetched over
the network may carry identical names, and a user file called
``download_notes.pdf`` is still **the user's own material**.

This module records *provenance* instead of guessing:

- ``user``       -- files the user placed by hand (recorded by ``init``).
                   These are the user's initial material and must be
                   preserved **verbatim**: never renamed, never modified.
- ``downloaded`` -- files the assistant fetched during the session.

The manifest lives at ``process/sources.json`` (path-whitelisted for
verify, so it never counts as an unauthorized addition) and stores **names
only** -- no hashes, no content reads -- so maintaining it is free.

Resolution order (see :mod:`organize`)
--------------------------------------
1. registered as downloaded -> ``material/downloaded/``
2. registered as user       -> ``material/initial/`` (verbatim)
3. keyword rules            -> configured target
4. fallback                 -> ``material/initial/``
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from scripts import utils

#: Manifest file name, stored directly under ``process/``.
MANIFEST_NAME = "sources.json"

MANIFEST_SCHEMA_VERSION = 1

#: Provenance kinds.
KIND_USER = "user"
KIND_DOWNLOADED = "downloaded"


@dataclass
class SourceEntry:
    """One registered file."""

    name: str
    url: str = ""
    at: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "url": self.url, "at": self.at, "note": self.note}

    @classmethod
    def from_dict(cls, d: dict) -> "SourceEntry":
        if isinstance(d, str):  # tolerate the bare-string shorthand
            return cls(name=d)
        return cls(
            name=str(d.get("name", "")),
            url=str(d.get("url", "")),
            at=str(d.get("at", "")),
            note=str(d.get("note", "")),
        )


@dataclass
class SourceManifest:
    """The provenance manifest for one task root."""

    root: Path
    user: List[SourceEntry] = field(default_factory=list)
    downloaded: List[SourceEntry] = field(default_factory=list)

    # -- path --------------------------------------------------------------

    @property
    def path(self) -> Path:
        """``<root>/process/sources.json``."""
        return Path(self.root) / utils.TIER_PROCESS / MANIFEST_NAME

    # -- construction ------------------------------------------------------

    @classmethod
    def load(cls, root: Path) -> "SourceManifest":
        """Load the manifest; a missing/corrupt file yields an empty one."""
        man = cls(root=Path(root))
        p = man.path
        if not p.is_file():
            return man
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return man
        if not isinstance(data, dict):
            return man
        for key, kind in (("user", KIND_USER), ("downloaded", KIND_DOWNLOADED)):
            raw = data.get(key)
            if not isinstance(raw, list):
                continue
            entries = [SourceEntry.from_dict(x) for x in raw if x]
            entries = [e for e in entries if e.name]
            setattr(man, kind, entries)
        return man

    # -- queries -----------------------------------------------------------

    def names(self, kind: str) -> List[str]:
        """Return the registered file names for *kind*."""
        entries = self.user if kind == KIND_USER else self.downloaded
        return [e.name for e in entries]

    def kind_of(self, name: str) -> Optional[str]:
        """Return ``"user"`` / ``"downloaded"`` / ``None`` for a file *name*.

        Matching is on the **file name** (basename), because a user file may
        be sitting at the root, inside a legacy sub-folder, or already in a
        tier -- the manifest must recognise it in all of those places.
        """
        base = Path(name).name
        if base in self.names(KIND_DOWNLOADED):
            return KIND_DOWNLOADED
        if base in self.names(KIND_USER):
            return KIND_USER
        return None

    def is_verbatim(self, name: str) -> bool:
        """True when *name* is user material that must never be renamed."""
        return self.kind_of(name) == KIND_USER

    # -- mutation ----------------------------------------------------------

    def add(self, kind: str, name: str, url: str = "", note: str = "") -> bool:
        """Register *name* under *kind*. Returns True when something changed.

        Registering is idempotent: an already-registered name is left as-is
        (its original ``at`` stamp and URL are preserved).
        """
        entries = self.user if kind == KIND_USER else self.downloaded
        base = Path(name).name
        if base in [e.name for e in entries]:
            return False
        entries.append(
            SourceEntry(
                name=base,
                url=url,
                at=datetime.now().isoformat(),
                note=note,
            )
        )
        return True

    def remove(self, name: str) -> bool:
        """Unregister *name* from either list."""
        base = Path(name).name
        changed = False
        for entries in (self.user, self.downloaded):
            keep = [e for e in entries if e.name != base]
            if len(keep) != len(entries):
                changed = True
                entries[:] = keep
        return changed

    def record_user_files(self, paths) -> int:
        """Register every path in *paths* as user material.

        Used by ``init`` to capture the pre-existing state of a folder so
        that later runs know exactly what the user placed (and therefore
        what must be preserved verbatim). Returns the number of new
        registrations.
        """
        added = 0
        for p in paths:
            if self.add(KIND_USER, Path(p).name):
                added += 1
        return added

    # -- persistence -------------------------------------------------------

    def save(self) -> Optional[Path]:
        """Persist the manifest. Never raises."""
        try:
            utils.write_json(
                self.path,
                {
                    "schema_version": MANIFEST_SCHEMA_VERSION,
                    "root": str(Path(self.root).resolve()),
                    "user": [e.to_dict() for e in self.user],
                    "downloaded": [e.to_dict() for e in self.downloaded],
                },
            )
            return self.path
        except OSError:
            return None

    def counts(self) -> Dict[str, int]:
        return {"user": len(self.user), "downloaded": len(self.downloaded)}


def manifest_path(root: Path) -> Path:
    """Return the manifest path for *root* without loading it."""
    return SourceManifest(root=root).path


def is_manifest(rel_path: str) -> bool:
    """True when *rel_path* is the manifest document itself.

    Path-exact on purpose: a user file that merely happens to be called
    ``sources.json`` at the task root must **not** be treated as tool
    output (that would silently exclude it from integrity verification).
    """
    norm = str(rel_path).replace("\\", "/").lstrip("./")
    return norm == f"{utils.TIER_PROCESS}/{MANIFEST_NAME}"
