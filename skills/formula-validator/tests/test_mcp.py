"""MCP server contract tests.

The server is the second way to drive the checks (the CLI is the first), and
it must behave exactly like the CLI: same verdicts, same compact summary,
same refusal to guess. These tests speak the wire protocol directly over
stdio, so they also pin that stdout carries JSON-RPC and nothing else.
"""

from __future__ import annotations

import json
import subprocess
import sys

from conftest import ROOT

MCP = ROOT / "mcp_server" / "server.py"


def _mcp(messages):
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    return subprocess.run([sys.executable, str(MCP)], input=payload,
                          capture_output=True, text=True, timeout=600)


def _responses(proc):
    return [json.loads(ln) for ln in proc.stdout.strip().splitlines() if ln.strip()]


def test_mcp_handshake_and_tool_list():
    proc = _mcp([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ])
    resps = _responses(proc)
    assert resps[0]["result"]["serverInfo"]["name"] == "formula-validator"
    names = [t["name"] for t in resps[1]["result"]["tools"]]
    assert names == ["formula_validate", "formula_inspect", "formula_derive",
                     "matrix_check"]


def test_mcp_tool_surface_stays_small():
    """A large tool schema is injected into every conversation that mounts it."""
    proc = _mcp([{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}])
    tools = _responses(proc)[0]["result"]["tools"]
    assert len(tools) <= 5


def test_mcp_validates_and_inspects():
    proc = _mcp([
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "formula_validate",
                    "arguments": {"expr": "1/(x*(1+x)) = 1/x - 1/(1+x)"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "matrix_check",
                    "arguments": {"matrix": "Matrix([[0, -I], [I, 0]])"}}},
    ])
    resps = _responses(proc)
    assert json.loads(resps[0]["result"]["content"][0]["text"])["verdict"] == "pass"
    assert json.loads(resps[1]["result"]["content"][0]["text"])["verdict"] == "pass"


def test_mcp_accepts_latex_input():
    proc = _mcp([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "formula_validate",
                             "arguments": {"expr": r"\frac{1}{1-x^2} = \frac{1}{1-x}"}}}])
    payload = json.loads(_responses(proc)[0]["result"]["content"][0]["text"])
    assert payload["verdict"] == "fail"


def test_mcp_reports_unknown_tools_cleanly():
    proc = _mcp([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "does_not_exist", "arguments": {}}}])
    resps = _responses(proc)
    assert resps[0]["result"]["isError"] is True
    assert "unknown tool" in resps[0]["result"]["content"][0]["text"]


def test_mcp_tool_descriptions_mention_no_other_skill():
    """Tool descriptions are injected every turn; they advertise this tool only.

    A description that points at another skill - real or imagined - tells the
    agent to go looking for a package that may not exist.
    """
    proc = _mcp([{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}])
    for tool in _responses(proc)[0]["result"]["tools"]:
        text = tool["description"]
        for banned in ("Js_", "bridge", "partner"):
            assert banned not in text, (
                f"{tool['name']} description references {banned!r}: {text!r}")
