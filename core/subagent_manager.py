"""Chelate Shell sub-agent manager — lifecycle + permission isolation.

Caller: core/router.py (future dispatch to sub-agents), cli.py,
        tests/test_subagent_manager.py.

Data schemas:
    Reads:  agents/<agent>.md — a Markdown file whose leading
            ``---``-delimited frontmatter declares the agent's
            *permission scope*:
                name:            <agent id, must match the filename>
                role:            <one-line purpose>
                allowed_skills:  [skill-a, skill-b, ...]   # whitelist
                allowed_paths:   [assets, process, results] # writable roots
                sandbox:         true | false
                timeout_seconds: 120
                max_steps:       8
            The prose after the closing ``---`` is stored as ``description``.
            Parsed by ``_parse_agent_md``.
    Writes: none — sessions are in-memory only (a per-session scratch dir
            under process/subagents/<id>/ is created on spawn for isolation).

Design (v1.3.0, task #126):
    * Discover: scan agents/*.md, build ``AgentSpec`` objects, record parse
      errors (never fatal — one broken agent cannot break the rest). Every
      spec is cross-checked against the skill registry so an agent that
      names a non-existent skill is flagged but still loaded.
    * Permission isolation (fail-closed):
        - A task's ``skill`` must be in the agent's ``allowed_skills``
          whitelist, else the run returns a DENIED outcome and the executor
          is never invoked.
        - Any write path outside ``allowed_paths`` (and outside the agent's
          own scratch dir) raises ``PathDenied``. An agent that declares no
          ``allowed_paths`` can only write to its scratch dir.
    * Lifecycle: spawn() -> AgentSession(status="idle") ->
      run_task()/run() (status="running") -> "done" | "denied" | "failed";
      terminate() flips a flag and marks the session "terminated" (cooperative
      — the per-skill sandbox circuit-breaker in core.sandbox.py bounds a
      runaway skill even without an explicit kill).
    * Execution: the default executor delegates to ``core.router.run_skill``
      (which already routes sandbox_required skills through the multiprocessing
      circuit-breaker). The executor is injectable so tests stay fast and
      deterministic.
    * Security: external text handed to a sub-agent is scanned lazily through
      ``core.security_shield`` (added in task #127); the import is deferred so
      the two modules stay decoupled and the manager degrades gracefully when
      the shield is absent.

No new hard dependency: YAML frontmatter is parsed with PyYAML when present,
otherwise a small built-in parser handles the simple ``key: value`` /
``key: [a, b]`` forms (mirrors the registry's stdlib-only philosophy).
"""
from __future__ import annotations

import os
import pathlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _REPO_ROOT not in __import__("sys").path:
    __import__("sys").path.insert(0, _REPO_ROOT)

# Outcome status values returned by a sub-agent session.
STATUS_DENIED = "DENIED"
STATUS_DONE = "DONE"
STATUS_FAILED = "FAILED"

# Default executor signature: (session, task) -> outcome dict.
Executor = Callable[["AgentSession"], Dict[str, object]]


class PermissionDenied(Exception):
    """Raised when a task requests a skill outside the agent's whitelist."""


class PathDenied(Exception):
    """Raised when a write targets a path outside the agent's allowed roots."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"path {path!r} denied: {reason}")


@dataclass
class AgentSpec:
    """A parsed sub-agent definition (the permission scope)."""

    name: str
    role: str = ""
    allowed_skills: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)
    sandbox: bool = True
    timeout_seconds: int = 120
    max_steps: int = 8
    description: str = ""
    source_path: str = ""

    def allows_skill(self, skill: str) -> bool:
        return skill in self.allowed_skills

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "role": self.role,
            "allowed_skills": list(self.allowed_skills),
            "allowed_paths": list(self.allowed_paths),
            "sandbox": self.sandbox,
            "timeout_seconds": self.timeout_seconds,
            "max_steps": self.max_steps,
            "source_path": self.source_path,
        }


# --------------------------------------------------------------------------- #
# Frontmatter parsing (YAML if available, else a tiny built-in parser)
# --------------------------------------------------------------------------- #

def _coerce_scalar(value: str):
    """Coerce a raw frontmatter value string to bool/int/list/str."""
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",") if item.strip()]
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "''", '""'):
        return None
    if v.lstrip("-").isdigit():
        return int(v)
    return v.strip().strip('"').strip("'")


def _manual_frontmatter(text: str) -> Dict[str, object]:
    """Parse a leading ``---`` block with the minimal ``key: value`` grammar.

    Returns {} when there is no frontmatter. Only the simple,
    dependency-free forms used by agent specs are supported; rich YAML
    (nested maps, multi-line strings) is delegated to PyYAML when present.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: Dict[str, object] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        if not key:
            continue
        out[key] = _coerce_scalar(raw)
    return out


def _parse_frontmatter(text: str) -> Dict[str, object]:
    """Use PyYAML when importable; fall back to the built-in parser."""
    try:  # pragma: no cover - exercised only when PyYAML is installed
        import yaml  # type: ignore
        if yaml.__version__:  # ensure the import is "used"
            pass
    except Exception:
        return _manual_frontmatter(text)
    # Re-split the frontmatter block and let yaml parse it.
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    block: List[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        block.append(line)
    try:  # pragma: no cover - exercised only when PyYAML is installed
        data = yaml.safe_load("\n".join(block)) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return _manual_frontmatter(text)


def _parse_agent_md(path: str) -> "tuple[Optional[AgentSpec], List[str]]":
    """Parse one agents/<name>.md file.

    Returns (spec, errors). On hard failure (unreadable, missing name) the
    spec is None and errors is populated; the manager records these and
    keeps running.
    """
    errors: List[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception as exc:
        return None, [f"{path}: unreadable ({exc})"]

    fm = _parse_frontmatter(text)
    name = fm.get("name")
    if not name:
        return None, [f"{path}: missing 'name' in frontmatter"]
    filename = pathlib.Path(path).stem
    if str(name) != filename:
        errors.append(
            f"{path}: name {name!r} does not match filename {filename!r}")

    # Split prose description (after the second '---').
    description = ""
    parts = text.split("---", 2)
    if len(parts) == 3:
        description = parts[2].strip()

    skills = fm.get("allowed_skills") or []
    if isinstance(skills, str):
        skills = [skills]
    paths = fm.get("allowed_paths") or []
    if isinstance(paths, str):
        paths = [paths]

    spec = AgentSpec(
        name=str(name),
        role=str(fm.get("role", "")),
        allowed_skills=[str(s) for s in skills],
        allowed_paths=[str(p) for p in paths],
        sandbox=bool(fm.get("sandbox", True)),
        timeout_seconds=int(fm.get("timeout_seconds", 120) or 120),
        max_steps=int(fm.get("max_steps", 8) or 8),
        description=description,
        source_path=str(path),
    )
    return spec, errors


# --------------------------------------------------------------------------- #
# Session (lifecycle + permission isolation)
# --------------------------------------------------------------------------- #

class AgentSession:
    """A live sub-agent instance with its own scratch dir and step budget."""

    def __init__(self, spec: AgentSpec, manager: "SubAgentManager",
                 executor: Optional[Executor] = None) -> None:
        self.spec = spec
        self.manager = manager
        self.id = uuid.uuid4().hex[:12]
        self.status = "idle"
        self.steps = 0
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.finished_at: Optional[str] = None
        self._terminated = False
        self._executor: Executor = executor or _dispatch_via_router
        self.scratch = os.path.join(
            manager.root, "process", "subagents", self.id)
        os.makedirs(self.scratch, exist_ok=True)

    # -- permission isolation -------------------------------------------- #

    def assert_path_allowed(self, path: str) -> None:
        """Raise PathDenied unless `path` is the scratch dir or an allowed root."""
        root = self.manager.root
        apath = os.path.abspath(path)
        scratch = os.path.abspath(self.scratch)
        if apath == scratch or apath.startswith(scratch + os.sep):
            return
        if not self.spec.allowed_paths:
            raise PathDenied(path, "agent declares no allowed_paths (fail-closed)")
        for allowed in self.spec.allowed_paths:
            aroot = os.path.abspath(os.path.join(root, allowed))
            if apath == aroot or apath.startswith(aroot + os.sep):
                return
        raise PathDenied(path, "outside allowed_paths whitelist")

    def _scan_external_text(self, text: str) -> Optional[Dict[str, object]]:
        """Lazily scan external text through core.security_shield (#127).

        Returns the shield verdict when the module is available, else None
        (graceful degradation — isolation still holds on skills/paths).
        """
        try:
            from core.security_shield import scan as _scan  # noqa
        except Exception:
            return None
        return _scan(text)

    # -- lifecycle -------------------------------------------------------- #

    def run_task(self, task: Dict[str, object]) -> Dict[str, object]:
        """Execute one task under the agent's permission scope.

        `task` keys: skill (str, required), action (str), args (list[str]),
        root (str), text (str, optional external text to scan).
        Returns an outcome dict with at least ``status`` and ``reason``.
        """
        if self._terminated:
            return self._out(STATUS_DENIED, "session terminated")
        if self.steps >= self.spec.max_steps:
            return self._out(STATUS_DENIED, "max_steps budget exhausted")

        skill = task.get("skill")
        if not skill:
            return self._out(STATUS_DENIED, "task missing 'skill'")
        if not self.spec.allows_skill(str(skill)):
            return self._out(
                STATUS_DENIED,
                f"skill {skill!r} not in allowed_skills {self.spec.allowed_skills}")

        # Optional anti-injection scan of any external text (#127 hook).
        if task.get("text"):
            verdict = self._scan_external_text(str(task["text"]))
            if verdict and verdict.get("blocked"):
                return self._out(
                    STATUS_DENIED,
                    f"external text blocked by security shield: "
                    f"{verdict.get('reason', '')}")

        self.steps += 1
        self.status = "running"
        try:
            outcome = dict(self._executor(self, task))
        except PermissionDenied as exc:
            self.status = "denied"
            return self._out(STATUS_DENIED, str(exc))
        except Exception as exc:  # executor failures are contained
            self.status = "failed"
            return self._out(STATUS_FAILED, f"executor error: {exc}")
        finally:
            if not self._terminated:
                self.status = "done"
            else:
                self.status = "terminated"
                self.finished_at = datetime.now(timezone.utc).isoformat()
        outcome.setdefault("status", STATUS_DONE)
        outcome.setdefault("agent", self.spec.name)
        outcome.setdefault("session", self.id)
        return outcome

    def terminate(self) -> None:
        """Cooperatively terminate: flag the session and finalize status.

        Sets the flag and marks the session "terminated" unconditionally so
        an idle (never-run) session is also cleanly closed, not left "idle".
        """
        self._terminated = True
        self.status = "terminated"
        self.finished_at = datetime.now(timezone.utc).isoformat()

    def _out(self, status: str, reason: str) -> Dict[str, object]:
        if self.finished_at is None and status != "running":
            self.finished_at = datetime.now(timezone.utc).isoformat()
        return {
            "status": status,
            "reason": reason,
            "agent": self.spec.name,
            "session": self.id,
            "steps": self.steps,
        }


# --------------------------------------------------------------------------- #
# Default executor — delegates to the existing router/sandbox pipeline
# --------------------------------------------------------------------------- #

def _dispatch_via_router(session: AgentSession,
                         task: Dict[str, object]) -> Dict[str, object]:
    """Run `task['skill']` through core.router.run_skill.

    Reuses the router's handling (including the sandbox circuit-breaker for
    sandbox_required skills) so a sub-agent inherits the same isolation the
    main pipeline has.
    """
    from core.registry import load_default_registry
    from core.router import run_skill

    reg = session.manager.registry or load_default_registry(session.manager.root)
    rec = reg.get(str(task["skill"]))
    if rec is None:
        raise PermissionDenied(f"unknown skill {task['skill']!r}")
    root = str(task.get("root") or session.manager.root)
    action = str(task.get("action", "process"))
    args = [str(a) for a in (task.get("args") or [])]
    record = run_skill(rec, root, action, args,
                       timeout=session.spec.timeout_seconds)
    return {
        "status": STATUS_DONE if record.get("status") != "FAIL" else STATUS_FAILED,
        "reason": record.get("reason", ""),
        "skill": rec.name,
        "returncode": record.get("returncode"),
        "seconds": record.get("seconds"),
        "sandbox": record.get("sandbox", False),
    }


# --------------------------------------------------------------------------- #
# Manager
# --------------------------------------------------------------------------- #

class SubAgentManager:
    """Discovers agent specs and spawns isolated sessions."""

    def __init__(self, repo_root: Optional[str] = None,
                 registry=None) -> None:
        self.root = os.path.abspath(repo_root or _REPO_ROOT)
        self.agents_dir = os.path.join(self.root, "agents")
        self.registry = registry
        self._specs: Dict[str, AgentSpec] = {}
        self.errors: List[str] = []
        self._sessions: Dict[str, AgentSession] = {}

    def discover(self) -> "SubAgentManager":
        """Scan agents/*.md and populate the in-memory spec table."""
        if not os.path.isdir(self.agents_dir):
            self.errors.append(f"agents directory not found: {self.agents_dir}")
            return self
        for md in sorted(pathlib.Path(self.agents_dir).glob("*.md")):
            spec, errs = _parse_agent_md(str(md))
            self.errors.extend(errs)
            if spec is None:
                continue
            # Cross-check whitelisted skills against the registry (non-fatal).
            if self.registry is not None:
                missing = [s for s in spec.allowed_skills
                           if s not in self.registry]
                if missing:
                    self.errors.append(
                        f"{spec.source_path}: allowed_skills not in registry: "
                        f"{missing}")
            if spec.name in self._specs:
                self.errors.append(
                    f"{spec.source_path}: duplicate agent name {spec.name!r}")
                continue
            self._specs[spec.name] = spec
        return self

    def get(self, name: str) -> Optional[AgentSpec]:
        return self._specs.get(name)

    def specs(self) -> List[AgentSpec]:
        return sorted(self._specs.values(), key=lambda s: s.name)

    def names(self) -> List[str]:
        return sorted(self._specs.keys())

    def spawn(self, name: str,
              executor: Optional[Executor] = None) -> AgentSession:
        """Create a live, isolated session for agent `name`."""
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"no such agent: {name!r} (known: {self.names()})")
        session = AgentSession(spec, self, executor=executor)
        self._sessions[session.id] = session
        return session

    def session(self, session_id: str) -> Optional[AgentSession]:
        return self._sessions.get(session_id)

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, name: str) -> bool:
        return name in self._specs


def load_default_manager(repo_root: Optional[str] = None,
                         registry=None) -> SubAgentManager:
    """Convenience: build a manager rooted at `repo_root` and discover agents."""
    if repo_root is None:
        repo_root = _REPO_ROOT
    if registry is None:
        try:
            from core.registry import load_default_registry
            registry = load_default_registry(repo_root)
        except Exception:
            registry = None
    return SubAgentManager(repo_root, registry=registry).discover()
