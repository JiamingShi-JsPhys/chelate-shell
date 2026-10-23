"""Thin-adapter toolkit — every skill's root run.py is wired through here.

Two flows, one contract:

1. `dispatch()` for skills whose logic lives in lib/chelate_core (the five
   v1.1.0 skills). run.py only declares argparse flags and handler
   functions; handlers return a verdict dict and this module emits the
   GateResult plus the single stdout JSON line the Router parses.

2. `run_legacy()` for the nine migrated v1.0.0 skills. Their code stays
   untouched inside the skill folder; this module imports the legacy entry
   module in-process, runs it with the right argv shape and cwd, and maps
   the outcome onto the same gate contract.

Handler contract (flow 1):
    handler(args) -> {
        "status": "PASS" | "FAIL" | "UNVERIFIED",
        "evidence_level": "EXACT" | "SYMBOLIC" | "EMPIRICAL" | "UNVERIFIED",
        "reason": str,
        "artifacts": [paths],          # optional
        "data": {...},                 # optional extra payload fields
    }
Controlled outcomes raise Degraded() (-> UNVERIFIED, e.g. missing optional
dependency) or Failed() (-> FAIL, e.g. bad input). Unexpected exceptions
become FAIL/UNVERIFIED with a traceback tail — a crash never passes a gate.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import pathlib
import sys
import traceback
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import debug, paths, yamlmini


# --------------------------------------------------------------------------
# controlled outcomes
# --------------------------------------------------------------------------

class Degraded(Exception):
    """Skill cannot run here (missing dependency, unreadable input format).

    Maps to an UNVERIFIED gate: the pipeline continues, nothing is faked.
    """

    def __init__(self, reason: str, evidence_level: str = "UNVERIFIED",
                 artifacts: Optional[List[str]] = None):
        super().__init__(reason)
        self.evidence_level = evidence_level
        self.artifacts = list(artifacts or [])


class Failed(Exception):
    """Hard, attributable failure. Maps to a FAIL gate (pipeline stops)."""

    def __init__(self, reason: str, evidence_level: str = "UNVERIFIED",
                 artifacts: Optional[List[str]] = None):
        super().__init__(reason)
        self.evidence_level = evidence_level
        self.artifacts = list(artifacts or [])


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

def repo_root() -> str:
    return paths.repo_root()


def ensure_repo_on_path() -> str:
    """Put the repository root on sys.path so `import bootstrap` works."""
    root = paths.repo_root()
    paths.ensure_on_syspath(root)
    return root


def skill_root(dunder_file: str) -> str:
    """Skill directory that owns the calling run.py."""
    return paths.skill_root(dunder_file)


def bootstrap():
    """Import (once) the repo-root bootstrap module."""
    ensure_repo_on_path()
    import bootstrap as _bootstrap  # noqa: WPS433 (runtime import by design)
    return _bootstrap


def probe_deps(modules: Sequence[str]) -> List[str]:
    """Subset of `modules` not importable in this interpreter."""
    import importlib.util
    return [m for m in modules if importlib.util.find_spec(m) is None]


def require_deps(modules: Sequence[str], what: str) -> None:
    """Raise Degraded when any of `modules` is missing."""
    missing = probe_deps(modules)
    if missing:
        raise Degraded(f"degraded: missing dependencies {missing}; {what} "
                       f"unavailable")


def load_config(skill_dir: str,
                defaults: Optional[Dict] = None) -> Dict:
    """Merge <skill_dir>/assets/config.yaml over `defaults`."""
    return yamlmini.merge(defaults, yamlmini.load_config(skill_dir))


def add_common_args(ap: argparse.ArgumentParser,
                    default_action: str,
                    action_help: str = "") -> None:
    """Add the uniform --root / --action / --debug pair every adapter exposes."""
    ap.add_argument("--root", required=True, help="workspace root")
    ap.add_argument("--action", default=default_action,
                    help=action_help or f"action (default: {default_action})")
    ap.add_argument("--debug", action="store_true",
                    help="verbose stderr diagnostics (same as CHELATE_DEBUG=1)")


def _emit(root: str, skill: str, status: str, evidence: str, reason: str,
          artifacts: Optional[List[str]] = None,
          data: Optional[Dict] = None) -> Dict:
    """Write the gate and print the adapter's stdout contract line."""
    bs = bootstrap()
    payload = bs.emit_gate(root, skill, status, evidence, reason,
                           artifacts=artifacts)
    debug.log(f"{skill}: gate -> {payload['gate']} "
              f"[{status}/{evidence}] {reason}")
    payload = {"status": status, "evidence_level": evidence, "reason": reason,
               "artifacts": list(artifacts or [])}
    if data:
        payload.update(data)
    return payload


# --------------------------------------------------------------------------
# flow 1 — thin adapters over lib/chelate_core
# --------------------------------------------------------------------------

# Generic stage actions the Router passes to every skill of a stage; an
# adapter maps them onto its own default action (same behavior as the
# v1.0.0 adapters, which accepted any action and defaulted safely).
STAGE_ACTION_ALIASES = frozenset({"workspace", "ingest", "gate", "process"})


def dispatch(skill: str,
             configure: Optional[Callable[[argparse.ArgumentParser], None]],
             handlers: Dict[str, Callable[[argparse.Namespace], Dict]],
             argv: Optional[List[str]] = None,
             description: str = "") -> int:
    """Parse args, run handlers[args.action], emit the gate, print JSON."""
    ensure_repo_on_path()
    ap = argparse.ArgumentParser(prog=skill, description=description)
    add_common_args(ap, next(iter(handlers)))
    if configure:
        configure(ap)
    args = ap.parse_args(argv)
    debug.flag(args.debug)  # --debug flag or CHELATE_DEBUG env, one switch
    debug.log(f"{skill}: argv={argv if argv is not None else sys.argv[1:]} "
              f"handlers={sorted(handlers)}")

    action = args.action
    if action not in handlers:
        if action in STAGE_ACTION_ALIASES:
            action = next(iter(handlers))  # generic stage action -> default
            debug.log(f"{skill}: stage action {args.action!r} -> {action!r}")
        else:
            _emit(args.root, skill, "FAIL", "UNVERIFIED",
                  f"unknown action {args.action!r}; expected one of "
                  f"{sorted(handlers)}")
            return 0
    handler = handlers[action]
    debug.log(f"{skill}: running handler {handler.__name__} for "
              f"action={action!r}")
    try:
        result = handler(args) or {}
        status = result.get("status", "PASS")
        evidence = result.get("evidence_level", "UNVERIFIED")
        reason = result.get("reason", "")
        artifacts = result.get("artifacts") or []
        data = result.get("data") or {}
        _emit(args.root, skill, status, evidence, reason,
              artifacts=artifacts, data=data)
    except Degraded as exc:
        _emit(args.root, skill, "UNVERIFIED", exc.evidence_level, str(exc),
              artifacts=exc.artifacts)
    except Failed as exc:
        _emit(args.root, skill, "FAIL", exc.evidence_level, str(exc),
              artifacts=exc.artifacts)
    except Exception as exc:  # unexpected: fail closed, never pass a gate
        tail = " | ".join(traceback.format_exc().splitlines()[-3:])
        _emit(args.root, skill, "FAIL", "UNVERIFIED",
              f"adapter error: {type(exc).__name__}: {exc} [{tail}]")
    return 0


# --------------------------------------------------------------------------
# flow 2 — declarative runner for migrated legacy CLIs
# --------------------------------------------------------------------------

# argv builder modes understood by _legacy_argv():
#   "sub"        [subcommand] + legacy args
#   "nosub"      legacy args only
#   "rootsub"    [subcommand, root] + legacy args
#   "subrootflag"[subcommand] + legacy args + ["--root", root]

def run_legacy(skill: str,
               actions: Dict[str, Tuple[str, str, str]],
               argv: Optional[List[str]] = None,
               description: str = "",
               extra_paths: Sequence[str] = (),
               default_action: Optional[str] = None,
               skill_dir: Optional[str] = None,
               dependencies: Sequence[str] = (),
               dep_purpose: str = "",
               gate_map: Optional[Callable[[int, str, str], Tuple[str, str, str]]]
               = None,
               verdict_hook: Optional[Callable[
                   [int, str, str, List[str]], Tuple[str, str, str, List[str]]]]
               = None) -> int:
    """Run a legacy CLI subcommand and report it as a gate result.

    `actions` maps an adapter action name to
    (module, entry_function, argv_mode). `extra_paths` are additional
    sys.path entries (e.g. the skill's scripts/ dir for bare modules).
    `skill_dir` is used as cwd while the legacy CLI runs (legacy CLIs
    resolve example configs and outputs relative to their own directory).
    `dependencies` are probed first; a missing one degrades to UNVERIFIED
    before the legacy import is attempted.     `gate_map(rc, stdout, sub)` ->
    (status, evidence, reason) overrides the default rc==0 -> PASS/EXACT.
    `verdict_hook(rc, stdout, sub, legacy_argv)` -> (status, evidence,
    reason, artifacts) replaces the mapping entirely (used by
    formula-validator to merge its pint unit layer). A legacy argparse
    usage error (non-zero rc with "usage:" on stderr) means the invocation
    was incomplete — the legacy code never examined the data — so it is
    reported as UNVERIFIED, never as a FAIL that blocks the pipeline.
    """
    ensure_repo_on_path()
    ap = argparse.ArgumentParser(prog=f"{skill}-adapter", description=description)
    add_common_args(ap, default_action or next(iter(actions)),
                    "legacy subcommand")
    ap.add_argument("legacy", nargs=argparse.REMAINDER,
                    help="arguments forwarded to the legacy CLI")
    args = ap.parse_args(argv)
    raw_legacy = [a for a in (args.legacy or []) if a != "--"]
    # --debug belongs to the adapter; never forward it to the legacy CLI
    debug.flag(args.debug or "--debug" in raw_legacy)
    legacy_argv = [a for a in raw_legacy if a != "--debug"]
    sub = args.action if args.action in actions else (default_action
                                                      or next(iter(actions)))
    module_name, fn_name, mode = actions[sub]
    debug.log(f"{skill}: action={args.action!r} -> {module_name}.{fn_name} "
              f"mode={mode!r} legacy_argv={legacy_argv}")

    if dependencies:
        missing = probe_deps(dependencies)
        if missing:
            debug.log(f"{skill}: degraded, missing dependencies {missing}")
            _emit(args.root, skill, "UNVERIFIED", "UNVERIFIED",
                  f"degraded: missing dependencies {missing}"
                  + (f"; {dep_purpose}" if dep_purpose else ""))
            return 0

    module = _import_legacy(module_name, extra_paths)
    if module is None:
        _emit(args.root, skill, "FAIL", "UNVERIFIED",
              f"legacy import failed: module {module_name!r} not found")
        return 0
    entry = getattr(module, fn_name, None)
    if not callable(entry):
        _emit(args.root, skill, "FAIL", "UNVERIFIED",
              f"legacy entry {module_name}.{fn_name} not callable")
        return 0

    call = _legacy_argv(mode, sub, str(pathlib.Path(args.root)), legacy_argv)
    buf = io.StringIO()
    errbuf = io.StringIO()
    rc = 0
    bs = bootstrap()
    try:
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(errbuf), _maybe_cwd(bs, skill_dir):
            rc = entry(call)
    except SystemExit as exc:
        rc = int(exc.code or 0)
    except Exception as exc:
        _emit(args.root, skill, "FAIL", "UNVERIFIED",
              f"legacy CLI crashed: {type(exc).__name__}: {exc}")
        return 0

    out = buf.getvalue()
    err = errbuf.getvalue()
    if err:
        # keep the legacy CLI's stderr visible to the caller (direct runs)
        sys.stderr.write(err)
    if int(rc or 0) != 0 and "usage:" in err:
        debug.log(f"{skill}: legacy usage error rc={int(rc or 0)}")
        _emit(args.root, skill, "UNVERIFIED", "UNVERIFIED",
              f"legacy CLI invocation incomplete (rc={rc}): {_tail(err)}")
        return 0
    if verdict_hook is not None:
        debug.log(f"{skill}: verdict_hook rc={int(rc or 0)} sub={sub!r}")
        status, evidence, reason, artifacts = verdict_hook(
            int(rc or 0), out, sub, legacy_argv)
        _emit(args.root, skill, status, evidence, reason, artifacts=artifacts)
        return 0
    if gate_map is not None:
        debug.log(f"{skill}: gate_map rc={int(rc or 0)} sub={sub!r}")
        status, evidence, reason = gate_map(int(rc or 0), out, sub)
    elif int(rc or 0) == 0:
        status, evidence, reason = "PASS", "EXACT", f"subcommand {sub!r} completed"
    else:
        status, evidence, reason = ("FAIL", "EXACT",
                                    f"subcommand {sub!r} exited rc={rc}: "
                                    f"{_tail(out)}")
    _emit(args.root, skill, status, evidence, reason)
    return 0


@contextlib.contextmanager
def _maybe_cwd(bs, skill_dir):
    """chdir into the skill directory while the legacy CLI runs."""
    if skill_dir:
        with bs.legacy_cwd(skill_dir):
            yield
    else:
        yield


def _import_legacy(module_name: str, extra_paths: Sequence[str]):
    """Import a legacy entry module with skill paths on sys.path."""
    paths.ensure_on_syspath(*[p for p in extra_paths if p])
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _legacy_argv(mode: str, sub: str, root: str,
                 legacy_argv: List[str]) -> List[str]:
    if mode == "nosub":
        return list(legacy_argv)
    if mode == "rootsub":
        return [sub, root] + list(legacy_argv)
    if mode == "subrootflag":
        return [sub] + list(legacy_argv) + ["--root", root]
    return [sub] + list(legacy_argv)  # "sub"


def tail(text: str, n: int = 2, limit: int = 240) -> str:
    """Last n non-empty lines of `text`, joined and length-capped."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return " | ".join(lines[-n:])[:limit]


# backward-compatible private alias
_tail = tail


def last_json(text: str) -> Optional[Dict]:
    """Last JSON object embedded in `text` (legacy CLIs print summaries)."""
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None
