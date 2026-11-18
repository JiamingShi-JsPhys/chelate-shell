"""Reproducibility bundles — what a result was made from, in one archive.

Caller: skills/repro-bundler/run.py.
Data schemas:
    Reads:  <workspace>/process/** (the run's products), process/gates/*.json,
            and the repository's skills/*/manifest.json for versions.
    Writes: <workspace>/process/repro/<name>-<stamp>.zip, containing
            manifest.json and files/<workspace-relative path>.
Design: standard library only (zipfile + hashlib), and two rules that matter
        more than the feature.

    **Writing is deterministic.** Every entry gets the same fixed timestamp
    and mode, entries are sorted, and the manifest's only clock value is the
    one passed in. Two bundles built from unchanged inputs are byte-identical,
    which is the only version of "reproducible" that can be checked by a
    stranger: compare the hashes, not the story.

    **Reading is where the attacks are.** A bundle is a file someone else can
    hand you. Before a single byte is trusted, every entry is checked for an
    absolute path, a drive letter, a `..` component, or a symlink — the four
    ways a zip turns "extract this" into "write outside the directory". An
    archive containing any of them is refused as a whole rather than partly
    read, and nothing in this module ever extracts to disk.

    Verification compares each listed file's SHA-256 with the manifest, and
    reports missing, mismatched and unexpected entries separately — "the
    bundle is wrong" is not a useful sentence; which of the three is.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

BUNDLE_DIR = os.path.join("process", "repro")
MANIFEST_NAME = "manifest.json"
FILES_PREFIX = "files/"
MAX_BUNDLE_BYTES = 256 * 1024 * 1024
_EXCLUDED_DIRS = {"gates", "repro", "__pycache__", ".pytest_cache"}
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


class BundleError(ValueError):
    """The bundle cannot be built or must not be read."""


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(root: str, path: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def collect(root: str) -> List[Dict[str, Any]]:
    """Every regular file under process/, minus gates/, repro/ and caches."""
    base = os.path.join(root, "process")
    found: List[Dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in _EXCLUDED_DIRS)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if not os.path.isfile(full) or os.path.islink(full):
                continue
            found.append({"path": _rel(root, full),
                          "sha256": _sha256_file(full),
                          "size": os.path.getsize(full)})
    return found


def _gates(root: str) -> List[Dict[str, Any]]:
    """The gate records a bundle must carry to be checkable later."""
    base = os.path.join(root, "process", "gates")
    rows: List[Dict[str, Any]] = []
    if not os.path.isdir(base):
        return rows
    for name in sorted(os.listdir(base)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(base, name), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            rows.append({"file": name, "error": "unreadable"})
            continue
        rows.append({
            "file": name,
            "skill": data.get("skill"),
            "status": data.get("status"),
            "evidence_level": data.get("evidence_level"),
            "provenance": data.get("provenance") or {},
            "inputs": data.get("inputs") or {},
        })
    return rows


def _skills() -> List[Dict[str, str]]:
    """Skill name → declared version, from the repository the bundle came from."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skills_dir = os.path.join(os.path.dirname(here), "skills")
    rows: List[Dict[str, str]] = []
    if not os.path.isdir(skills_dir):
        return rows
    for name in sorted(os.listdir(skills_dir)):
        manifest = os.path.join(skills_dir, name, "manifest.json")
        if not os.path.isfile(manifest):
            continue
        try:
            with open(manifest, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        rows.append({"name": str(data.get("name") or name),
                     "version": str(data.get("version") or "")})
    return rows


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_FIXED_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def build(root: str, name: str, include: Optional[Iterable[str]] = None,
          now: Optional[str] = None) -> Dict[str, Any]:
    """Write a deterministic bundle; return its path and manifest summary."""
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise BundleError(f"bundle name {name!r} is not a plain file name")
    files = collect(root)
    if include:
        wanted = {item.replace("\\", "/") for item in include}
        files = [item for item in files if item["path"] in wanted]
        missing = wanted - {item["path"] for item in files}
        if missing:
            raise BundleError(f"declared file(s) not found: {sorted(missing)}")
    total = sum(item["size"] for item in files)
    if total > MAX_BUNDLE_BYTES:
        raise BundleError(
            f"bundle would be {total} bytes; limit is {MAX_BUNDLE_BYTES}. "
            f"Pass --include with the files that matter.")

    stamp = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "format": 1,
        "bundle": name,
        "created": stamp,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "workspace": os.path.basename(os.path.abspath(root)),
        "files": files,
        "gates": _gates(root),
        "skills": _skills(),
    }

    out_dir = os.path.join(root, BUNDLE_DIR)
    os.makedirs(out_dir, exist_ok=True)
    slug = stamp.replace(":", "").replace("-", "")
    out_path = os.path.join(out_dir, f"{name}-{slug}.zip")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_zip_info(MANIFEST_NAME),
                         json.dumps(manifest, ensure_ascii=False, indent=2,
                                    sort_keys=True))
        for item in sorted(files, key=lambda row: row["path"]):
            with open(os.path.join(root, *item["path"].split("/")), "rb") as fh:
                archive.writestr(_zip_info(FILES_PREFIX + item["path"]),
                                 fh.read())
    return {"path": out_path, "files": len(files), "bytes": os.path.getsize(out_path),
            "created": stamp, "manifest": manifest}


def _unsafe_reason(name: str, info: zipfile.ZipInfo) -> Optional[str]:
    parts = name.replace("\\", "/").split("/")
    if name.startswith(("/", "\\")):
        return "absolute path"
    if len(parts[0]) > 1 and parts[0][1] == ":":
        return "drive letter"
    if ".." in parts:
        return "'..' component"
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        return "symlink entry"
    return None


def inspect(path: str) -> List[Dict[str, Any]]:
    """List an archive's entries, refusing the ones that escape it."""
    if not zipfile.is_zipfile(path):
        raise BundleError(f"not a zip archive: {path}")
    entries: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            why = _unsafe_reason(info.filename, info)
            if why:
                raise BundleError(f"refusing {info.filename!r}: {why}")
            entries.append({"name": info.filename, "size": info.file_size})
    return entries


def verify(path: str) -> Dict[str, Any]:
    """Check a bundle against its own manifest. Never extracts anything."""
    entries = inspect(path)
    names = {entry["name"] for entry in entries}
    if MANIFEST_NAME not in names:
        raise BundleError("bundle has no manifest.json")
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
        declared = {FILES_PREFIX + item["path"]: item
                    for item in manifest.get("files") or []}
        missing = sorted(name for name in declared if name not in names)
        unexpected = sorted(name for name in names
                            if name != MANIFEST_NAME and name not in declared)
        mismatched: List[Dict[str, str]] = []
        for name, item in sorted(declared.items()):
            if name not in names:
                continue
            digest = hashlib.sha256(archive.read(name)).hexdigest()
            if digest != item.get("sha256"):
                mismatched.append({"path": name,
                                   "declared": str(item.get("sha256")),
                                   "actual": digest})
    problems: List[str] = []
    if missing:
        problems.append(f"{len(missing)} listed file(s) missing from the archive")
    if mismatched:
        problems.append(f"{len(mismatched)} file(s) do not match their digest")
    if unexpected:
        problems.append(f"{len(unexpected)} file(s) are not in the manifest")
    return {
        "ok": not problems,
        "bundle": manifest.get("bundle"),
        "created": manifest.get("created"),
        "files": len(declared),
        "missing": missing,
        "unexpected": unexpected,
        "mismatched": mismatched,
        "problems": problems,
    }
