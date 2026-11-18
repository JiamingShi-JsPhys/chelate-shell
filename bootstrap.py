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


def _sha256_file(path: str) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_rel(root: str, path: str) -> str:
    """Key a gate uses for *path*: workspace-relative, or ``external:`` + absolute.

    A bare basename for an outside file would be wrong twice: two different
    files called ``data.csv`` would collapse onto one key, and the freshness
    check would later look for the file inside the workspace and call it
    missing. An explicit prefix keeps both facts.
    """
    absolute = os.path.abspath(path)
    try:
        rel = os.path.relpath(absolute, os.path.abspath(root))
    except ValueError:  # different drive on Windows
        return f"external:{absolute}"
    if rel.startswith(".."):
        return f"external:{absolute}"
    return rel.replace(os.sep, "/")


def declared_inputs(root: str, argv=None) -> dict:
    """Hash every existing file named on this process's command line.

    This is what makes a gate answerable to the question "which bytes did you
    actually read?".  Only *files* count: `--root <dir>` and other directory
    or flag values are skipped, and nothing is invented when a flag points at
    a file the adapter never opens.  A missing or unreadable file is recorded
    as such instead of being dropped, so a later deletion cannot silently
    shrink the set.
    """
    import sys as _sys
    args = list(_sys.argv[1:] if argv is None else argv)
    found: dict = {}
    for token in args:
        if token.startswith("-") or not token:
            continue
        if not os.path.isfile(token):
            continue
        rel = _workspace_rel(root, token)
        try:
            size = os.path.getsize(token)
            if size > _LARGE_INPUT_BYTES:
                # A 2 GB video does not need to be hashed on every gate write;
                # its size is recorded and checked instead, and the marker
                # says so rather than pretending the bytes were digested.
                found[rel] = f"large:{size}"
            else:
                found[rel] = _sha256_file(token)
        except OSError:
            found[rel] = "unreadable"
    return found


# Inputs above this size are bound by size instead of by digest; see
# declared_inputs().  Hashing a multi-gigabyte video on every gate write
# would cost more than the check is worth.
_LARGE_INPUT_BYTES = 256 * 1024 * 1024

_SKIP_DIRS = frozenset({"__pycache__", ".pytest_cache", "_reports", "tests",
                        ".git", "node_modules"})


def _skill_dir(skill: str) -> str:
    """The running skill's directory, falling back to the repository layout."""
    import sys as _sys
    try:
        argv0 = os.path.dirname(os.path.abspath(_sys.argv[0]))
    except (AttributeError, ValueError):
        argv0 = ""
    if argv0 and os.path.isfile(os.path.join(argv0, "manifest.json")):
        return argv0
    candidate = os.path.join(_REPO_ROOT, "skills", skill)
    return candidate if os.path.isdir(candidate) else ""


def skill_provenance(skill: str) -> dict:
    """Version and code digest of the skill that produced a gate.

    The digest covers the skill's own Python and its manifest, not its tests
    or generated reports: those cannot change a verdict, and hashing them
    would make every test run look like a code change.
    """
    import hashlib
    skill_dir = _skill_dir(skill)
    if not skill_dir:
        return {}
    version = ""
    manifest = os.path.join(skill_dir, "manifest.json")
    try:
        with open(manifest, encoding="utf-8") as fh:
            version = str(json.load(fh).get("version", ""))
    except (OSError, ValueError):
        pass
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(skill_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if not name.endswith(".py") and name not in ("manifest.json",
                                                         "SKILL.md"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, skill_dir).replace(os.sep, "/")
            try:
                digest.update(rel.encode("utf-8"))
                digest.update(bytes.fromhex(_sha256_file(full)))
            except OSError:
                continue
    return {"skill_version": version,
            "skill_digest": digest.hexdigest()[:32],
            "gate_contract": 2}


def write_gate(root: str, gate) -> str:
    """Serialize `gate` to process/gates/<skill>_<ts>.json; return the path.

    The filename skill prefix comes from the GateResult.skill field, so the
    signature no longer needs a separate skill argument.

    Provenance is attached here, at the one place every skill's gate is
    serialized, so a new adapter cannot forget it: the digests of the files
    named on this process's command line, the skill's version and a digest of
    its code.  Without them a PASS says "some check passed, some time", and
    nothing can tell whether the input it judged is still the input at hand.
    """
    if root:
        if not getattr(gate, "inputs", None):
            try:
                gate.inputs = declared_inputs(root)
            except Exception:  # provenance must never fail a gate
                gate.inputs = {}
        if not getattr(gate, "provenance", None):
            try:
                gate.provenance = skill_provenance(getattr(gate, "skill", ""))
            except Exception:
                gate.provenance = {}
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


# The tail / last-JSON helpers are shared with the adapter toolkit, which
# owns the canonical implementations; re-exported at module level so the
# public API (`bootstrap.tail`, `bootstrap.last_json`) stays unchanged.
from lib.chelate_core.adapter import last_json, tail  # noqa: E402


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
