"""Tests for core.subagent_manager (v1.3.0 task #126).

Focus: agent discovery + parsing, permission isolation (skill whitelist and
fail-closed path guard), lifecycle (max_steps / terminate), and the deferred
security-shield scan hook. The executor is injected so no real subprocess is
spawned — the suite stays fast and deterministic.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.subagent_manager import (  # noqa: E402
    AgentSession,
    AgentSpec,
    PathDenied,
    PermissionDenied,
    STATUS_DENIED,
    STATUS_DONE,
    STATUS_FAILED,
    SubAgentManager,
    _manual_frontmatter,
    _parse_agent_md,
    load_default_manager,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _write_agent(tmp_path, name, body):
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    p = agents / f"{name}.md"
    p.write_text(body, encoding="utf-8")
    return p


AGENT_MD = """\
---
name: visual_agent
role: multimodal scientific figure generation and review
allowed_skills: [sci-visualizer, latex-exporter]
allowed_paths: [assets, process, results]
sandbox: true
timeout_seconds: 120
max_steps: 8
---

# Visual Agent

Generates and reviews scientific figures. Prose body.
"""

AGENT_MD_NO_PATHS = """\
---
name: scratch_agent
role: sandbox-only agent
allowed_skills: [sci-visualizer]
sandbox: false
---

No allowed_paths -> fail-closed.
"""


# --------------------------------------------------------------------------- #
# Frontmatter / parsing
# --------------------------------------------------------------------------- #

def test_manual_frontmatter_parses_list_and_scalars():
    text = "---\nname: x\nallowed_skills: [a, b, c]\nsandbox: false\n" \
           "timeout_seconds: 90\n---\nbody\n"
    fm = _manual_frontmatter(text)
    assert fm["name"] == "x"
    assert fm["allowed_skills"] == ["a", "b", "c"]
    assert fm["sandbox"] is False
    assert fm["timeout_seconds"] == 90


def test_manual_frontmatter_empty_when_no_block():
    assert _manual_frontmatter("just prose") == {}


def test_parse_agent_md_basic():
    import tempfile
    d = tempfile.mkdtemp()
    p = _write_agent(__import__("pathlib").Path(d), "visual_agent", AGENT_MD)
    spec, errors = _parse_agent_md(str(p))
    assert spec is not None
    assert errors == []
    assert spec.name == "visual_agent"
    assert spec.role.startswith("multimodal")
    assert spec.allowed_skills == ["sci-visualizer", "latex-exporter"]
    assert spec.allowed_paths == ["assets", "process", "results"]
    assert spec.sandbox is True
    assert spec.timeout_seconds == 120
    assert spec.max_steps == 8
    assert "Generates and reviews" in spec.description


def test_parse_agent_md_missing_name():
    import tempfile
    d = tempfile.mkdtemp()
    p = _write_agent(__import__("pathlib").Path(d), "bad",
                     "---\nrole: x\n---\nbody\n")
    spec, errors = _parse_agent_md(str(p))
    assert spec is None
    assert any("missing 'name'" in e for e in errors)


def test_parse_agent_md_filename_mismatch_recorded():
    import tempfile
    d = tempfile.mkdtemp()
    p = _write_agent(__import__("pathlib").Path(d), "wrong_name", AGENT_MD)
    spec, errors = _parse_agent_md(str(p))
    assert spec is not None
    assert any("does not match filename" in e for e in errors)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

def test_discover_loads_multiple_agents(tmp_path):
    _write_agent(tmp_path, "visual_agent", AGENT_MD)
    _write_agent(tmp_path, "scratch_agent", AGENT_MD_NO_PATHS)
    mgr = SubAgentManager(repo_root=str(tmp_path)).discover()
    assert set(mgr.names()) == {"visual_agent", "scratch_agent"}
    assert mgr.get("visual_agent").sandbox is True
    assert mgr.get("scratch_agent").allowed_paths == []


def test_discover_ignores_non_md_and_missing_dir(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    (agents / "notes.txt").write_text("ignore me")
    mgr = SubAgentManager(repo_root=str(tmp_path)).discover()
    assert mgr.names() == []
    assert mgr.errors == []


# --------------------------------------------------------------------------- #
# Permission isolation — skills
# --------------------------------------------------------------------------- #

def _spec_with(skills, paths=None, max_steps=8):
    return AgentSpec(name="t", role="t", allowed_skills=list(skills),
                     allowed_paths=list(paths or []), max_steps=max_steps)


def _mgr_for(tmp_path):
    mgr = SubAgentManager(repo_root=str(tmp_path))
    return mgr


def test_permission_denies_unlisted_skill(tmp_path):
    calls = []
    mgr = _mgr_for(tmp_path)
    spec = _spec_with(["sci-visualizer"])
    sess = AgentSession(spec, mgr,
                        executor=lambda s, t: (calls.append(t) or
                                               {"status": STATUS_DONE}))
    out = sess.run_task({"skill": "ml-auditor"})
    assert out["status"] == STATUS_DENIED
    assert "not in allowed_skills" in out["reason"]
    assert calls == []  # executor never invoked


def test_permission_allows_listed_skill(tmp_path):
    calls = []
    mgr = _mgr_for(tmp_path)
    spec = _spec_with(["sci-visualizer"])
    sess = AgentSession(spec, mgr,
                        executor=lambda s, t: (calls.append(t) or
                                               {"status": STATUS_DONE,
                                                "reason": "ok"}))
    out = sess.run_task({"skill": "sci-visualizer", "args": ["--x"]})
    assert out["status"] == STATUS_DONE
    assert calls == [{"skill": "sci-visualizer", "args": ["--x"]}]
    assert sess.steps == 1
    assert sess.status == "done"


# --------------------------------------------------------------------------- #
# Lifecycle — max_steps / terminate
# --------------------------------------------------------------------------- #

def test_max_steps_enforced(tmp_path):
    mgr = _mgr_for(tmp_path)
    spec = _spec_with(["sci-visualizer"], max_steps=1)
    sess = AgentSession(spec, mgr,
                        executor=lambda s, t: {"status": STATUS_DONE})
    assert sess.run_task({"skill": "sci-visualizer"})["status"] == STATUS_DONE
    second = sess.run_task({"skill": "sci-visualizer"})
    assert second["status"] == STATUS_DENIED
    assert "max_steps" in second["reason"]


def test_terminate_blocks_further_tasks(tmp_path):
    mgr = _mgr_for(tmp_path)
    spec = _spec_with(["sci-visualizer"])
    sess = AgentSession(spec, mgr,
                        executor=lambda s, t: {"status": STATUS_DONE})
    sess.terminate()
    assert sess.status == "terminated"
    out = sess.run_task({"skill": "sci-visualizer"})
    assert out["status"] == STATUS_DENIED
    assert "terminated" in out["reason"]


def test_spawn_returns_session_and_is_registered(tmp_path):
    _write_agent(tmp_path, "visual_agent", AGENT_MD)
    mgr = SubAgentManager(repo_root=str(tmp_path)).discover()
    sess = mgr.spawn("visual_agent")
    assert isinstance(sess, AgentSession)
    assert mgr.session(sess.id) is sess
    assert os.path.isdir(sess.scratch)


# --------------------------------------------------------------------------- #
# Permission isolation — paths (fail-closed)
# --------------------------------------------------------------------------- #

def test_path_guard_fail_closed_without_allowed_paths(tmp_path):
    mgr = _mgr_for(tmp_path)
    spec = _spec_with(["sci-visualizer"], paths=[])  # no allowed_paths
    sess = AgentSession(spec, mgr)
    with pytest.raises(PathDenied):
        sess.assert_path_allowed(str(tmp_path / "secret" / "x.png"))
    # scratch is always allowed
    sess.assert_path_allowed(sess.scratch)


def test_path_guard_allows_declared_root(tmp_path):
    mgr = _mgr_for(tmp_path)
    spec = _spec_with(["sci-visualizer"], paths=["assets"])
    sess = AgentSession(spec, mgr)
    allowed = tmp_path / "assets" / "fig.png"
    sess.assert_path_allowed(str(allowed))
    with pytest.raises(PathDenied):
        sess.assert_path_allowed(str(tmp_path / "process" / "p.json"))


# --------------------------------------------------------------------------- #
# Security-shield hook (deferred import; pluggable in #127)
# --------------------------------------------------------------------------- #

def test_external_text_blocked_by_shield(tmp_path):
    mgr = _mgr_for(tmp_path)
    spec = _spec_with(["sci-visualizer"])
    sess = AgentSession(spec, mgr,
                        executor=lambda s, t: {"status": STATUS_DONE})
    # Simulate the #127 shield returning a block verdict.
    sess._scan_external_text = lambda text: {  # type: ignore[assignment]
        "blocked": True, "reason": "injection pattern detected"}
    out = sess.run_task({"skill": "sci-visualizer", "text": "DROP TABLE"})
    assert out["status"] == STATUS_DENIED
    assert "security shield" in out["reason"]


def test_external_text_passes_when_shield_absent(tmp_path):
    mgr = _mgr_for(tmp_path)
    spec = _spec_with(["sci-visualizer"])
    sess = AgentSession(spec, mgr,
                        executor=lambda s, t: {"status": STATUS_DONE})
    # Default _scan_external_text returns None (no shield module yet).
    out = sess.run_task({"skill": "sci-visualizer", "text": "hello"})
    assert out["status"] == STATUS_DONE


# --------------------------------------------------------------------------- #
# Default executor delegation (no subprocess; uses a fake registry)
# --------------------------------------------------------------------------- #

def test_default_executor_rejects_unknown_skill(tmp_path):
    from core.subagent_manager import _dispatch_via_router

    class _FakeReg:
        def get(self, name):
            return None

    mgr = _mgr_for(tmp_path)
    mgr.registry = _FakeReg()
    spec = _spec_with(["sci-visualizer"])
    sess = AgentSession(spec, mgr)
    with pytest.raises(PermissionDenied):
        _dispatch_via_router(sess, {"skill": "ghost-skill"})


# --------------------------------------------------------------------------- #
# Real-repo smoke test
# --------------------------------------------------------------------------- #

def test_load_default_manager_on_real_repo():
    mgr = load_default_manager()
    assert isinstance(mgr, SubAgentManager)
    assert os.path.isdir(mgr.agents_dir)
    # Two agent specs ship with v1.3.0 (spatial_agent, visual_agent);
    # discovery must find exactly those two by name.
    assert set(mgr.names()) == {"spatial_agent", "visual_agent"}
