#!/usr/bin/env python
"""MCP server for formula-validator - stdio JSON-RPC, no extra packages.

Most MCP servers pull in the ``mcp`` package. This one speaks the wire protocol
directly so that mounting it needs nothing beyond the skill's own requirements
(sympy / numpy / scipy). Fewer dependencies means fewer ways for the mount to
fail on a machine that is already set up for scientific work.

Exposes four tools on purpose. A large tool surface has to be injected into
every conversation that mounts the server, and 40+ tool schemas cost more
tokens than most verification runs save.

Stdout carries JSON-RPC only; diagnostics go to stderr.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts import __version__                               # noqa: E402
from scripts.core import breakpoint as bp_mod                 # noqa: E402
from scripts.core import pipeline                             # noqa: E402
from scripts.core.errors import ParseError                    # noqa: E402
from scripts.core.matrixprops import (PROPERTIES,             # noqa: E402
                                      check_matrix, parse_matrix)
from scripts.core.parsing import parse_expr                   # noqa: E402
from scripts.core.report import render                        # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "formula-validator"
# v1.1.1: a mounted (plugin) server must never write into its own
# install/cache directory; CHELATE_WORKSPACE names the workspace, whose
# process/reports/ receives the reports instead.
REPORT_DIR = Path(os.environ.get("CHELATE_WORKSPACE") or SKILL_ROOT) / "process" / "reports"

_UNITS_DESC = ("object mapping a symbol name to a unit string understood by the "
               "registry, e.g. {\"m\": \"kg\", \"c\": \"m/s\", \"E\": \"J\"}. "
               "Products use * and powers use **. Undeclared symbols make the "
               "dimensional check abstain unless infer is true.")

TOOLS = [
    {
        "name": "formula_validate",
        "description": ("Verify an equation 'lhs = rhs' with deterministic CAS "
                        "checks: parse, dimensional analysis, limit-case "
                        "enumeration, 10k-sample numerical comparison and "
                        "symbolic identity proving. Returns a compact verdict; "
                        "the full Markdown report is written to disk."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "expr": {"type": "string",
                         "description": ("The equation, e.g. 'sqrt(k/m) = "
                                         "omega'. SymPy syntax is most reliable; "
                                         "LaTeX such as \\frac{k}{m} also works.")},
                "units": {"type": "object", "description": _UNITS_DESC},
                "samples": {"type": "integer", "default": 10000,
                            "description": "Number of random sample points."},
                "tol": {"type": "number", "default": 1e-9,
                        "description": "Relative tolerance for the numeric check."},
                "critical": {"type": "array", "items": {"type": "string"},
                             "description": ("Extra limit points to test, e.g. "
                                             "['x=1'] for a suspected pole.")},
                "infer": {"type": "boolean", "default": False,
                          "description": ("Guess units for undeclared symbols "
                                          "from a physics naming table. Off by "
                                          "default: a wrong guess creates a "
                                          "false dimensional error.")},
                "positive": {"type": "array", "items": {"type": "string"},
                             "description": ("Symbols to sample as strictly "
                                             "positive, e.g. ['m', 'k'].")},
                "symbols": {"type": "array", "items": {"type": "string"},
                            "description": ("Force these names to parse as "
                                            "plain symbols. Needed for I when it "
                                            "means current, not the imaginary "
                                            "unit.")},
                "full_report": {"type": "boolean", "default": False,
                                "description": ("Return the whole Markdown report "
                                                "instead of the compact summary. "
                                                "Costs far more tokens.")},
            },
            "required": ["expr"],
        },
    },
    {
        "name": "formula_inspect",
        "description": ("Inspect a single expression: report its dimension, "
                        "where its denominator vanishes, and its limit "
                        "behaviour. Use when there is no equation to compare, "
                        "only a result to sanity-check."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "expr": {"type": "string",
                         "description": "The expression, e.g. 'hbar**2*k**2/(2*m)'."},
                "units": {"type": "object", "description": _UNITS_DESC},
                "infer": {"type": "boolean", "default": False},
                "positive": {"type": "array", "items": {"type": "string"}},
                "symbols": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["expr"],
        },
    },
    {
        "name": "formula_derive",
        "description": ("Verify a multi-step derivation and localise the break. "
                        "Each consecutive pair of steps is compared; the first "
                        "disagreement is reported with a diagnosis that "
                        "separates a dropped dimensional factor, a wrong "
                        "coefficient, and a wrong functional form."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "steps": {"type": "array", "items": {"type": "string"},
                          "description": ("The derivation chain in order, one "
                                          "expression per entry. At least two.")},
                "units": {"type": "object", "description": _UNITS_DESC},
                "samples": {"type": "integer", "default": 10000},
                "tol": {"type": "number", "default": 1e-9},
                "infer": {"type": "boolean", "default": False},
                "positive": {"type": "array", "items": {"type": "string"}},
                "symbols": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["steps"],
        },
    },
    {
        "name": "matrix_check",
        "description": ("Check matrix properties needed in group theory and "
                        "quantum mechanics: Hermitian, unitary, orthogonal, "
                        "traceless, and more. Both a symbolic and a numerical "
                        "verdict are produced."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "matrix": {"type": "string",
                           "description": ("The matrix as Matrix([[...]]) or "
                                           "[[...]], e.g. Matrix([[0, -I], [I, 0]]).")},
                "properties": {"type": "array", "items": {"type": "string"},
                               "description": ("Properties to test. One or more "
                                               "of: " + ", ".join(PROPERTIES) +
                                               ". Defaults to hermitian and "
                                               "unitary.")},
            },
            "required": ["matrix"],
        },
    },
]


def _write_report(result: dict) -> str | None:
    try:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / "latest.md"
        path.write_text(render(result), encoding="utf-8")
        return str(path)
    except Exception:
        return None


def _text(payload) -> dict:
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=True, indent=None)
    return {"content": [{"type": "text", "text": payload}], "isError": False}


def _error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _as_list(value):
    if value is None:
        return None
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return list(value)


def _tool_validate(args: dict) -> dict:
    try:
        result = pipeline.validate_equation(
            text=args["expr"], units=args.get("units"),
            n=int(args.get("samples", 10000)), tol=float(args.get("tol", 1e-9)),
            critical=_as_list(args.get("critical")),
            auto_infer=bool(args.get("infer", False)),
            positive=set(_as_list(args.get("positive")) or ()),
            symbol_names=_as_list(args.get("symbols")))
    except ParseError as exc:
        return _text({"verdict": "parse_error", "message": exc.message,
                      "detail": exc.detail})
    path = _write_report(result)
    if args.get("full_report"):
        return _text(render(result))
    return _text(pipeline.summarize(result, path))


def _tool_inspect(args: dict) -> dict:
    try:
        result = pipeline.inspect_expression(
            args["expr"], args.get("units"), bool(args.get("infer", False)),
            set(_as_list(args.get("positive")) or ()),
            symbol_names=_as_list(args.get("symbols")))
    except ParseError as exc:
        return _text({"verdict": "parse_error", "message": exc.message,
                      "detail": exc.detail})
    path = _write_report(result)
    return _text(pipeline.summarize(result, path))


def _tool_derive(args: dict) -> dict:
    steps = args.get("steps") or []
    if len(steps) < 2:
        return _error("at least two derivation steps are required")
    symbols = _as_list(args.get("symbols"))
    parsed = []
    for i, line in enumerate(steps):
        try:
            parsed.append(parse_expr(line, symbols)[0])
        except ParseError as exc:
            return _text({"verdict": "parse_error", "step": i, "text": line,
                          "message": exc.message, "detail": exc.detail})
    bp = bp_mod.locate_breakpoint(
        parsed, declared_units=args.get("units"),
        n=int(args.get("samples", 10000)), tol=float(args.get("tol", 1e-9)),
        auto_infer=bool(args.get("infer", False)),
        positive=set(_as_list(args.get("positive")) or ()))
    result = {"mode": "derivation", "input": {"steps": steps},
              "verdict": {"pass": "pass", "fail": "fail"}.get(bp["status"],
                                                              "unknown"),
              "checks": {}, "errors": [], "caveats": [], "breakpoint": bp}
    fb = bp.get("first_break")
    if fb:
        d = fb.get("diagnosis") or {}
        result["errors"].append({
            "check": "breakpoint", "severity": "error",
            "message": (f"the chain breaks at step {fb['step']} "
                        f"({d.get('summary') or 'sides disagree'})"),
            "evidence": {"worst_point": fb.get("worst_point")}})
    return _text(pipeline.summarize(result, _write_report(result)))


def _tool_matrix(args: dict) -> dict:
    try:
        matrix = parse_matrix(args["matrix"])
    except ParseError as exc:
        return _text({"verdict": "parse_error", "message": exc.message,
                      "detail": exc.detail})
    props = _as_list(args.get("properties"))
    mres = check_matrix(matrix, props or None)
    verdict = {"pass": "pass", "fail": "fail"}.get(mres["status"], "unknown")
    result = {"mode": "matrix", "input": {"text": args["matrix"]},
              "verdict": verdict, "checks": {}, "errors": [], "caveats": [],
              "matrix": mres}
    for p in mres["failed"]:
        result["errors"].append({
            "check": "matrix", "severity": "error",
            "message": f"the matrix is not {p.replace('_', ' ')}",
            "evidence": mres["properties"][p]})
    return _text({"verdict": verdict, "shape": mres["shape"],
                  "failed": mres["failed"], "unresolved": mres["unresolved"],
                  "report": _write_report(result)})


_HANDLERS = {
    "formula_validate": _tool_validate,
    "formula_inspect": _tool_inspect,
    "formula_derive": _tool_derive,
    "matrix_check": _tool_matrix,
}


def _reply(message_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _reply_error(message_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": message_id,
            "error": {"code": code, "message": message}}


def _handle_message(message: dict):
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _reply(message_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _reply(message_id, {})
    if method == "tools/list":
        return _reply(message_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        handler = _HANDLERS.get(name)
        if handler is None:
            return _reply(message_id,
                          _error(f"unknown tool '{name}'; available: "
                                 f"{', '.join(_HANDLERS)}"))
        try:
            return _reply(message_id, handler(params.get("arguments") or {}))
        except KeyError as exc:
            return _reply(message_id, _error(f"missing argument: {exc}"))
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            return _reply(message_id, _error(f"{type(exc).__name__}: {exc}"))
    if method and method.startswith("notifications/"):
        return None
    return _reply_error(message_id, -32601, f"method not found: {method}")


def main() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except Exception as exc:
            sys.stderr.write(f"bad JSON-RPC frame: {exc}\n")
            continue
        try:
            response = _handle_message(message)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            response = _reply_error(message.get("id"), -32603, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
