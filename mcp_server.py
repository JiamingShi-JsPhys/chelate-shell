"""Chelate Shell — MCP server over stdio.

Caller: an MCP host (Claude Code, Codex, any client that speaks the protocol).
        Entry point: `python mcp_server.py`.
Data schemas:
    Reads:  newline-delimited JSON-RPC 2.0 on stdin.
    Writes: newline-delimited JSON-RPC 2.0 on stdout. Logs go to stderr, so a
            host that treats stdout as the channel is never corrupted.
Design: stdio only, standard library only.

    Four tools, and the list is the security boundary as much as the feature
    list. Every one of them goes through `core.runtime`, so the MCP surface
    inherits whatever the selected backend enforces:

    ====================  =====================================
    chelate_status        read-only census
    chelate_run_skill     runs one skill; `publish=False`
    chelate_start_recipe  runs a recipe serially; publishes nothing
    chelate_audit         read-only: what is in results/ and why
    chelate_memory        read-only: workspace notes + chain check
    ====================  =====================================

    There is deliberately no `approve` and no `promote` tool. An MCP client
    is an agent, and an agent that can approve its own promotion is not
    gated at all — the token exists to require a person, and a tool that
    mints one would hand that person's decision to the process being
    supervised. `chelate_run_skill` therefore passes `publish=False`: a
    skill runs into `process/`, and publishing stays a CLI act with a token.

    `chelate_memory` is read-only for the same reason: memory is replayed
    to a later session as data, so the process being supervised must not
    be able to write what that session will read. Adding an entry is a CLI
    act a person types.

    The server opens no socket except the stdio pair it was given. It does
    not read credentials, and it does not write `results/`.
"""
from __future__ import annotations

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core import memory as memory_mod  # noqa: E402
from core import recipes as recipes_mod  # noqa: E402
from core import runtime as runtime_mod  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "chelate-shell"

TOOLS = [
    {
        "name": "chelate_status",
        "description": "Report the active runtime, its containment label, and "
                       "the gates a promotion would rest on.",
        "inputSchema": {
            "type": "object",
            "properties": {"root": {"type": "string",
                                    "description": "workspace path"}},
            "required": ["root"],
        },
    },
    {
        "name": "chelate_run_skill",
        "description": "Run one registered skill into process/. Never "
                       "publishes: promotion needs a human token.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string"},
                "skill": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["root", "skill"],
        },
    },
    {
        "name": "chelate_start_recipe",
        "description": "Run a workspace recipe serially, stopping at the "
                       "first failing step. Never publishes.",
        "inputSchema": {
            "type": "object",
            "properties": {"root": {"type": "string"},
                           "name": {"type": "string"}},
            "required": ["root", "name"],
        },
    },
    {
        "name": "chelate_audit",
        "description": "Name everything in results/ that no promotion "
                       "accounts for.",
        "inputSchema": {
            "type": "object",
            "properties": {"root": {"type": "string"}},
            "required": ["root"],
        },
    },
    {
        "name": "chelate_memory",
        "description": "Read this workspace's memory notes (`brief` for the "
                       "block a session should read, `list` for entries, "
                       "`verify` for the hash chain). Read-only: there is no "
                       "way to add or remove an entry over MCP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string"},
                "op": {"type": "string",
                       "enum": ["brief", "list", "verify"],
                       "description": "default: brief"},
                "all": {"type": "boolean",
                        "description": "list: include withdrawn and "
                                       "expired entries"},
            },
            "required": ["root"],
        },
    },
]


def _message(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}],
            "isError": is_error}


def _call_tool(name: str, arguments: dict) -> dict:
    root = os.path.abspath(str(arguments.get("root", "")))
    try:
        backend = runtime_mod.select()
        if name == "chelate_status":
            payload = backend.status(root)
        elif name == "chelate_run_skill":
            skill = str(arguments.get("skill", ""))
            if not skill:
                raise ValueError("skill is required")
            args = arguments.get("args") or []
            if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                raise ValueError("args must be a list of strings")
            payload = backend.run_skill(root, skill, args=args, publish=False)
        elif name == "chelate_start_recipe":
            payload = recipes_mod.run(root, str(arguments.get("name", "")),
                                      runtime=backend)
        elif name == "chelate_audit":
            payload = backend.audit(root)
        elif name == "chelate_memory":
            op = str(arguments.get("op") or "brief")
            if op == "brief":
                payload = {"brief": memory_mod.brief(root)}
            elif op == "list":
                payload = {"entries": memory_mod.entries(
                    root, include_all=bool(arguments.get("all")))}
            elif op == "verify":
                payload = memory_mod.verify(root)
            else:
                raise ValueError(f"op must be brief, list or verify, not {op!r}")
        else:
            raise ValueError(f"unknown tool {name!r}")
    except Exception as exc:  # the client gets the reason, not a traceback
        return _message(f"{exc.__class__.__name__}: {exc}", is_error=True)
    return _message(json.dumps(payload, ensure_ascii=False, indent=2,
                               default=str))


def handle(request: dict):
    """Return the response object, or None for a notification."""
    method = request.get("method")
    request_id = request.get("id")
    if request_id is None and method and method.startswith("notifications/"):
        return None

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": _version()},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = request.get("params") or {}
        result = _call_tool(str(params.get("name", "")),
                            dict(params.get("arguments") or {}))
    else:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": f"unknown method {method!r}"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _version() -> str:
    try:
        with open(os.path.join(_REPO_ROOT, "package.json"), encoding="utf-8") as fh:
            return str(json.load(fh).get("version", ""))
    except (OSError, ValueError):
        return ""


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
