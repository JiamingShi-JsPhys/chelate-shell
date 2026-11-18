"""Content-addressed input snapshots — what a skill reads, frozen.

The gate records the digest of the bytes it judged, and promotion re-checks
that digest before copying anything.  That closes the "edited after the check"
window, but not the window *inside* the run: a skill opens its input by path,
and between the moment the router hashed that path and the moment the skill's
own ``open()`` lands, the file can change.  The check and the use are two
different reads of the same mutable path — the classic TOCTOU shape.

A snapshot removes the mutable path from the run.  Before dispatch the router
copies each declared input into ``.chelate/snapshots/<id>/files/``, where
``<id>`` is derived from the set of (path, digest) pairs, and hands the
skills *those* paths.  What a skill reads is then addressed by content, not by
a name anything else can rewrite:

* the same inputs produce the same id, so a re-run reuses the directory
  instead of accumulating copies;
* the snapshot carries a manifest naming each original path and its digest,
  so promotion can still answer "is the file the user has now the file this
  run used?";
* a snapshot is never written after it is created, which is what makes it
  evidence rather than another working copy.

Inputs above ``MAX_SNAPSHOT_BYTES`` are not copied — a multi-gigabyte video
would be duplicated for every run.  They are dispatched from their original
path and reported as ``direct``, which is honest about the weaker guarantee
rather than silently claiming one.

Pure standard library.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from typing import Dict, List, Optional

SNAPSHOT_ROOT = ".chelate/snapshots"
MANIFEST = "manifest.json"
MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_rel(root: str, path: str) -> str:
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except ValueError:  # different drive on Windows
        return os.path.basename(path)
    return os.path.basename(path) if rel.startswith("..") \
        else rel.replace(os.sep, "/")


def _snapshot_id(entries: List[dict]) -> str:
    """Stable id for a set of (original path, digest) pairs."""
    payload = json.dumps(
        sorted((e["original"], e["sha256"]) for e in entries),
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _target_name(original: str, digest: str, used: set) -> str:
    """A file name inside the snapshot that two inputs cannot collide on."""
    name = os.path.basename(original)
    if name not in used:
        return name
    stem, ext = os.path.splitext(name)
    candidate = f"{stem}-{digest[:8]}{ext}"
    while candidate in used:  # pathological: same basename and digest
        candidate = f"{stem}-{digest[:12]}{ext}"
        break
    return candidate


def materialise(root: str, paths, limit: Optional[int] = None) -> dict:
    """Copy *paths* into one snapshot under *root* and describe the mapping.

    Returns::

        {"id": "ab12…", "dir": ".chelate/snapshots/ab12…",
         "files": {<absolute original>: <absolute snapshot path>},
         "skipped": [<absolute original>, …],   # too large, or unreadable
         "manifest": ".chelate/snapshots/ab12…/manifest.json"}

    An empty *paths* yields ``{"id": "", "files": {}, …}``: nothing to freeze.
    """
    limit = MAX_SNAPSHOT_BYTES if limit is None else limit
    entries: List[dict] = []
    skipped: List[str] = []
    for raw in paths or []:
        absolute = os.path.abspath(str(raw))
        try:
            size = os.path.getsize(absolute)
            if size > limit:
                skipped.append(absolute)
                continue
            digest = _sha256_file(absolute)
        except OSError:
            skipped.append(absolute)
            continue
        entries.append({"original": _workspace_rel(root, absolute),
                        "absolute": absolute,
                        "sha256": digest})
    if not entries:
        return {"id": "", "dir": "", "files": {}, "skipped": skipped,
                "manifest": ""}

    sid = _snapshot_id(entries)
    rel_dir = f"{SNAPSHOT_ROOT}/{sid}"
    snap_dir = os.path.join(root, *rel_dir.split("/"))
    files_dir = os.path.join(snap_dir, "files")
    os.makedirs(files_dir, exist_ok=True)

    used: set = set()
    files: Dict[str, str] = {}
    for entry in entries:
        name = _target_name(entry["original"], entry["sha256"], used)
        used.add(name)
        target = os.path.join(files_dir, name)
        if not os.path.isfile(target):
            # Copy once; the digest in the id makes a stale directory
            # impossible unless someone edits a snapshot by hand, which the
            # digest check in router.stale_gates() then catches.
            shutil.copy2(entry["absolute"], target)
        entry["snapshot"] = f"files/{name}"
        files[entry["absolute"]] = target

    manifest_path = os.path.join(snap_dir, MANIFEST)
    payload = {
        "id": sid,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": [{"original": e["original"], "sha256": e["sha256"],
                   "snapshot": e["snapshot"]} for e in entries],
    }
    tmp = manifest_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, manifest_path)

    return {"id": sid, "dir": rel_dir, "files": files, "skipped": skipped,
            "manifest": f"{rel_dir}/{MANIFEST}"}


def origin_of(root: str, snapshot_rel: str) -> Optional[dict]:
    """Map a snapshot file back to ``{"original", "sha256"}``, or None.

    *snapshot_rel* is the workspace-relative path a gate recorded, e.g.
    ``.chelate/snapshots/ab12/files/model.py``.  A path that is not inside a
    snapshot returns None so callers keep their ordinary handling.
    """
    parts = str(snapshot_rel).replace("\\", "/").split("/")
    if len(parts) < 4 or parts[0] != ".chelate" or parts[1] != "snapshots":
        return None
    sid, leaf = parts[2], "/".join(parts[3:])
    manifest = os.path.join(root, ".chelate", "snapshots", sid, MANIFEST)
    try:
        with open(manifest, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    for entry in data.get("files", []):
        if str(entry.get("snapshot")) == leaf:
            return {"original": str(entry.get("original", "")),
                    "sha256": str(entry.get("sha256", ""))}
    return None


def referenced(root: str) -> set:
    """Snapshot ids the newest gates still point at.

    A gate records the snapshot path it judged. Deleting that directory would
    turn a passing, current gate into "input missing" — a false failure the
    user cannot explain. Pruning therefore protects these ids.
    """
    gates_dir = os.path.join(root, "process", "gates")
    ids: set = set()
    if not os.path.isdir(gates_dir):
        return ids
    for name in os.listdir(gates_dir):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(gates_dir, name), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        inputs = (data.get("inputs") or {})
        if not isinstance(inputs, dict):
            continue
        for rel in inputs:
            parts = str(rel).replace("\\", "/").split("/")
            if len(parts) >= 3 and parts[0] == ".chelate"                     and parts[1] == "snapshots":
                ids.add(parts[2])
    return ids


def prune(root: str, keep: int = 20, protect=None) -> int:
    """Delete all but the *keep* newest snapshots; return how many went.

    A snapshot holds a copy of the user's data. Keeping every one of them
    forever would quietly build a shadow archive of everything a workspace
    ever read — a privacy cost that no one asked for and nothing would ever
    surface. The newest *keep* survive, plus any id the current gates still
    reference (see :func:`referenced`); everything else is deleted.
    """
    base = os.path.join(root, ".chelate", "snapshots")
    if not os.path.isdir(base):
        return 0
    protected = set(protect or ())
    dirs = []
    for name in os.listdir(base):
        full = os.path.join(base, name)
        if os.path.isdir(full):
            dirs.append((os.path.getmtime(full), name, full))
    dirs.sort(reverse=True)
    keep_names = {name for _m, name, _f in dirs[:keep]}
    removed = 0
    for _mtime, name, full in dirs[keep:]:
        if name in protected or name in keep_names:
            continue
        shutil.rmtree(full, ignore_errors=True)
        removed += 1
    return removed
