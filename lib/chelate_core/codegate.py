"""code-gate's engine — a fixed, declared set of static checks on Python.

Caller: skills/code-gate/run.py.

Data schemas:
    Reads:  any *.py under the given path inside the workspace.
    Writes: nothing here; the adapter writes process/code_report_*.json.

Design — three boundaries, stated because each is a temptation.

    **The rule set is fixed and small.** Every rule below is one AST shape
    with one sentence of justification, so a finding can be argued with.
    There is no severity slider and no "all the linters" mode: a gate whose
    rule set depends on which package happened to be installed gives two
    machines two different verdicts for the same file, and neither is wrong.

    **ruff is opt-in, and named when it runs.** `--ruff` adds its findings
    and the report records the exact command and version that produced
    them. It is off by default precisely because it is a second, versioned
    opinion.

    **This gate does not scan for dangerous calls.** `security-guard` owns
    `eval`/`exec`/`subprocess` screening; duplicating it here would create
    two answers to the same question, and the weaker one would eventually be
    the one someone quoted. The split is written down in both SKILL.md files.

    A file that cannot be parsed is a `syntax-error` finding, not a skipped
    file: an unreadable source is the one thing this gate can be certain
    about.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Tuple

from . import paths

MAX_FILES = 2000
MAX_REPORTED = 50
_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env",
    "node_modules", "build", "dist", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "process", "results",
})

RULE_TEXT = {
    "syntax-error": "the file does not parse, so nothing else about it is checked",
    "bare-except": "`except:` also catches KeyboardInterrupt and SystemExit",
    "swallowed-error": "`except ...: pass` discards the failure it caught",
    "mutable-default": "a list/dict/set default is shared by every call",
    "eq-none": "`== None` is False for any object that overrides __eq__",
    "star-import": "`from x import *` hides where a name came from",
    "long-function": "past the declared line budget a function stops being reviewable",
    "too-many-args": "past the declared argument budget a call site needs a structure",
}

RULES = tuple(RULE_TEXT)

RUFF_ARGS = ["check", "--no-cache", "--output-format=json",
             "--select", "E,F,W", "--ignore", "E501,W503"]


class CodeGateError(ValueError):
    """The target cannot be read as Python source."""


def _is_mutable_default(node: ast.AST) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp,
                         ast.DictComp, ast.SetComp)):
        return True
    if isinstance(node, ast.Call):
        name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        return name in ("list", "dict", "set", "defaultdict")
    return False


def _node_length(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None) or getattr(node, "lineno", 0)
    return max(0, int(end) - int(getattr(node, "lineno", 0)) + 1)


def check_source(source: str, path: str, max_lines: int = 80,
                 max_args: int = 7) -> List[Dict[str, Any]]:
    """Every finding in one file, sorted by line then rule."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [{"path": path, "line": int(exc.lineno or 0),
                 "rule": "syntax-error",
                 "message": f"{exc.msg} (line {exc.lineno})"}]

    findings: List[Dict[str, Any]] = []

    def add(node: ast.AST, rule: str, message: str) -> None:
        findings.append({"path": path, "line": int(getattr(node, "lineno", 0)),
                         "rule": rule, "message": message})

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                add(node, "bare-except", "bare except")
            elif not node.body or all(isinstance(item, ast.Pass)
                                      for item in node.body):
                add(node, "swallowed-error",
                    f"except {ast.unparse(node.type)}: pass")
        elif isinstance(node, ast.ImportFrom) and any(
                alias.name == "*" for alias in node.names):
            add(node, "star-import", f"from {node.module or '.'} import *")
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and \
                isinstance(node.ops[0], (ast.Eq, ast.NotEq)) and \
                isinstance(node.comparators[0], ast.Constant) and \
                node.comparators[0].value is None:
            add(node, "eq-none", f"comparison with None using "
                                 f"{'==' if isinstance(node.ops[0], ast.Eq) else '!='}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            total = (len(args.posonlyargs) + len(args.args)
                     + len(args.kwonlyargs))
            if total > max_args:
                add(node, "too-many-args",
                    f"{node.name}() takes {total} arguments (budget {max_args})")
            for default in list(args.defaults) + list(args.kw_defaults):
                if default is not None and _is_mutable_default(default):
                    add(node, "mutable-default",
                        f"{node.name}() has a mutable default argument")
            length = _node_length(node)
            if length > max_lines:
                add(node, "long-function",
                    f"{node.name}() spans {length} lines (budget {max_lines})")

    findings.sort(key=lambda item: (item["line"], item["rule"]))
    return findings


def iter_files(root: str, target: str) -> List[str]:
    """Python files under *target*, refused if it escapes the workspace."""
    raw = str(paths.resolve_input(root, target))
    if not os.path.isabs(raw):
        # A relative target that exists nowhere yet is still meant relative
        # to the workspace; resolving it against the process cwd would make
        # a typo look like an escape.
        raw = os.path.join(root, raw)
    resolved = paths.ensure_within(root, raw, what="target")
    if os.path.isfile(resolved):
        files = [resolved] if resolved.lower().endswith(".py") else []
    elif os.path.isdir(resolved):
        files = []
        for dirpath, dirnames, filenames in os.walk(resolved):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for name in sorted(filenames):
                if name.lower().endswith(".py"):
                    files.append(os.path.join(dirpath, name))
            if len(files) > MAX_FILES:
                raise CodeGateError(
                    f"more than {MAX_FILES} Python files under {target}; "
                    f"pass a narrower --input")
    else:
        raise CodeGateError(f"target not found: {target}")
    return sorted(files)


def check_tree(root: str, target: str, max_lines: int = 80,
               max_args: int = 7) -> Dict[str, Any]:
    """Run every rule over every file; report counts and the first findings."""
    files = iter_files(root, target)
    base = os.path.realpath(root)
    findings: List[Dict[str, Any]] = []
    unreadable: List[str] = []
    for path in files:
        rel = os.path.relpath(os.path.realpath(path), base).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append(f"{rel}: {exc}")
            continue
        findings.extend(check_source(source, rel, max_lines=max_lines,
                                     max_args=max_args))
    by_rule: Dict[str, int] = {}
    for item in findings:
        by_rule[item["rule"]] = by_rule.get(item["rule"], 0) + 1
    return {"files": len(files), "unreadable": unreadable,
            "findings": findings[:MAX_REPORTED],
            "finding_count": len(findings), "by_rule": by_rule,
            "rules": list(RULES), "max_lines": max_lines, "max_args": max_args,
            "ok": bool(files) and not findings and not unreadable}


def check(root: str, target: str, max_lines: int = 80, max_args: int = 7,
          ruff: bool = False) -> Dict[str, Any]:
    """check_tree plus the opt-in second opinion, merged into one report."""
    report = check_tree(root, target, max_lines=max_lines, max_args=max_args)
    extra: List[Dict[str, Any]] = []
    note = ""
    if ruff:
        extra, note = run_ruff(str(paths.resolve_input(root, target)))
        for item in extra:
            report["by_rule"][item["rule"]] = \
                report["by_rule"].get(item["rule"], 0) + 1
        report["finding_count"] += len(extra)
        report["ok"] = (bool(report["files"]) and not report["finding_count"]
                        and not report["unreadable"])
    report["ruff"] = {"enabled": bool(ruff), "note": note,
                      "findings": extra[:MAX_REPORTED], "count": len(extra)}
    return report


def _ruff_version() -> str:
    try:
        proc = subprocess.run([sys.executable, "-m", "ruff", "--version"],
                              capture_output=True, text=True, timeout=30)
        return (proc.stdout or "").strip().splitlines()[0] if proc.stdout else ""
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


def run_ruff(target: str, timeout: int = 120) -> Tuple[List[Dict[str, Any]], str]:
    """Optional second opinion. Returns (findings, note); ([], "") when absent."""
    import importlib.util
    if importlib.util.find_spec("ruff") is None:
        return [], "ruff is not installed; --ruff ignored"
    try:
        proc = subprocess.run([sys.executable, "-m", "ruff", *RUFF_ARGS,
                               str(target)], capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"ruff could not run: {exc}"
    if proc.returncode not in (0, 1):  # 1 = issues found, anything else = error
        return [], f"ruff failed (rc={proc.returncode}): {(proc.stderr or '')[:200]}"
    try:
        rows = json.loads(proc.stdout or "[]")
    except ValueError:
        return [], "ruff output was not JSON; findings ignored"
    findings = []
    for row in rows if isinstance(rows, list) else []:
        location = row.get("location") or {}
        findings.append({
            "path": str(row.get("filename") or target).replace(os.sep, "/"),
            "line": int(location.get("row") or 0),
            "rule": f"ruff:{row.get('code') or '?'}",
            "message": str(row.get("message") or "")[:240],
        })
    return findings, f"ruff {_ruff_version()} ran: {RUFF_ARGS[3]} rules"
