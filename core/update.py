"""Update checking and host-driven updates for an installed copy.

A plugin is installed by a *host* (ZCode, Claude Code, ...) into a cache of
its own, so the copy a user runs is frozen at the moment they installed it.
Nothing in this repository can rewrite that cache from inside the copy, and a
stale copy is exactly how a fixed bypass keeps running: during development the
ZCode cache still held the pre-fix code after several commits had landed.

Two things are therefore here instead:

``check()``
    asks the repository on ``main`` whether the files this copy is running
    still match, and says so in one line. Version numbers are not enough --
    a workspace like this one keeps editing during a release window -- so the
    comparison is over file contents.

``apply()``
    runs the host's own update command for every host that actually has the
    plugin installed. It shells out to ``zcode`` / ``claude`` as an argument
    list, never through a shell.

Both are best-effort: an offline machine, a missing host CLI or a proxy that
eats the request all end as "unknown", never as an error that stops a run.
``CHELATE_UPDATE_OFF=1`` silences the automatic notice entirely.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

REPO = "JiamingShi-JsPhys/chelate-shell"
BRANCH = "main"
PLUGIN = "chelate-shell"
RAW = "https://raw.githubusercontent.com/{repo}/{branch}/".format(
    repo=REPO, branch=BRANCH)

# Enough to tell whether this copy is the published one: the manifest every
# host reads, and the file most behaviour lives in.
TRACKED = ("package.json", "core/router.py")
CACHE_TTL_SECONDS = 24 * 3600
# A machine that cannot read the repository should not pay the timeout on
# every run; that answer is worth keeping for an hour.
OFFLINE_TTL_SECONDS = 3600
FETCH_TIMEOUT = 4.0
_OFF_ENV = "CHELATE_UPDATE_OFF"


def local_root() -> Path:
    return Path(__file__).resolve().parents[1]


def cache_path() -> Path:
    """Where the last answer is kept, next to the approval keys."""
    root = os.environ.get("CHELATE_KEY_ROOT")
    if root:
        base = Path(root).parent
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA")
                    or str(Path.home() / "AppData" / "Local")) / "chelate"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME")
                    or str(Path.home() / ".local" / "share")) / "chelate"
    return base / "update-check.json"


def _fetch(path: str, timeout: float = FETCH_TIMEOUT) -> Optional[bytes]:
    """Bytes of *path* on the published branch, or None if it cannot be read."""
    url = RAW + path
    request = urllib.request.Request(url, headers={
        "User-Agent": f"{PLUGIN}-update-check"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def check(force: bool = False) -> Dict[str, object]:
    """Compare this copy with the published one.

    Returns ``{"reachable", "different", "files", "local_version",
    "remote_version", "checked_at", "cached"}``. ``reachable`` false means the
    question could not be asked, which is not the same as "up to date".
    """
    cached = _read_cache()
    if cached and not force:
        age = time.time() - _as_float(cached.get("checked_at"))
        ttl = CACHE_TTL_SECONDS if cached.get("reachable") else OFFLINE_TTL_SECONDS
        if 0 <= age < ttl:
            cached["cached"] = True
            return cached

    root = local_root()
    local_version = _version(root / "package.json")
    different: List[str] = []
    reachable = False
    remote_version = None
    for rel in TRACKED:
        remote = _fetch(rel)
        if remote is None:
            break  # no point spending another timeout on the next file
        reachable = True
        if rel == "package.json":
            remote_version = _version_bytes(remote)
        local = root / rel
        try:
            here = local.read_bytes()
        except OSError:
            different.append(rel)
            continue
        # Line endings differ between a checkout and a raw download; the
        # question here is whether the code is the same, not the bytes on disk.
        if here.replace(b"\r", b"") != remote.replace(b"\r", b""):
            different.append(rel)

    result: Dict[str, object] = {
        "reachable": reachable,
        "different": bool(different),
        "files": different,
        "local_version": local_version,
        "remote_version": remote_version,
        "checked_at": time.time(),
        "cached": False,
    }
    _write_cache(result)
    return result


def _version(path: Path) -> Optional[str]:
    try:
        return _version_bytes(path.read_bytes())
    except OSError:
        return None


def _version_bytes(raw: bytes) -> Optional[str]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return str(data.get("version")) if isinstance(data, dict) else None


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _read_cache() -> Optional[Dict[str, object]]:
    try:
        with open(cache_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_cache(result: Dict[str, object]) -> None:
    path = cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False)
    except OSError:
        pass


# ------------------------------------------------------------------- hosts

def installed_hosts() -> List[Dict[str, str]]:
    """Hosts that have this plugin installed, with the id their CLI expects.

    Only hosts with a real update verb are listed; ``dsh`` installs through
    pnpm into a profile this module cannot name, so it is reported by hand.
    """
    found: List[Dict[str, str]] = []
    if shutil.which("zcode"):
        try:
            out = subprocess.run(["zcode", "plugins", "list"],
                                 capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            out = None
        if out and out.returncode == 0:
            for line in out.stdout.splitlines():
                line = line.strip()
                if line.startswith(f"- {PLUGIN}@") and "[enabled]" in line:
                    plugin_id = line.split()[1]
                    marketplace = plugin_id.split("@", 1)[1]
                    found.append({"host": "zcode", "plugin": plugin_id,
                                  "marketplace": marketplace})
    if shutil.which("claude"):
        try:
            out = subprocess.run(["claude", "plugin", "list"],
                                 capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            out = None
        if out and out.returncode == 0 and PLUGIN in out.stdout:
            found.append({"host": "claude", "plugin": PLUGIN,
                          "marketplace": ""})
    return found


def update_commands(host: Dict[str, str]) -> List[List[str]]:
    """The exact argv a host needs, in order."""
    if host["host"] == "zcode":
        return [["zcode", "plugins", "marketplace", "update",
                 host["marketplace"]],
                ["zcode", "plugins", "update", host["plugin"]]]
    if host["host"] == "claude":
        return [["claude", "plugin", "update", host["plugin"]]]
    return []


def apply(hosts: Optional[List[Dict[str, str]]] = None,
          timeout: int = 600) -> List[Dict[str, object]]:
    """Run each host's update command; return what ran and how it went."""
    results: List[Dict[str, object]] = []
    for host in (hosts if hosts is not None else installed_hosts()):
        for argv in update_commands(host):
            record: Dict[str, object] = {"host": host["host"],
                                         "command": " ".join(argv)}
            try:
                proc = subprocess.run(argv, capture_output=True, text=True,
                                      timeout=timeout)
                record["returncode"] = proc.returncode
                record["output"] = (proc.stdout or "").strip()[-400:]
                if proc.returncode != 0:
                    record["error"] = (proc.stderr or "").strip()[-400:]
            except (OSError, subprocess.SubprocessError) as exc:
                record["returncode"] = None
                record["error"] = f"{type(exc).__name__}: {exc}"
            results.append(record)
            if record.get("returncode") not in (0,):
                break  # the second command depends on the first
    return results


def notice(enabled: Optional[bool] = None) -> Optional[str]:
    """One line for a run's stderr, or None when there is nothing to say.

    Never raises: a machine with no network must not be told it is wrong.
    """
    if enabled is None:
        enabled = os.environ.get(_OFF_ENV, "") not in ("1", "true", "yes")
    if not enabled:
        return None
    try:
        result = check()
    except Exception:  # noqa: BLE001 - a notice must never break a run
        return None
    if not result.get("reachable"):
        return None
    if result.get("different"):
        return (f"{PLUGIN}: this copy differs from {BRANCH} -- "
                f"run `python cli.py update --apply` to refresh the host cache")
    return None
