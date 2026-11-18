"""Chelate Shell security shield — anti-injection + AST static scanner.

Caller: core/subagent_manager.py (lazy ``scan(text)`` hook for external text),
        the future security-guard skill (#128), tests/test_security_shield.py.

Two independent gates:

1. Anti-injection (``scan_text``): inspects *external* text handed to a
   sub-agent for prompt-injection markers. Conservative by design — only a
   small, high-confidence pattern set blocks; everything else passes so
   legitimate scientific prose is never wrongly dropped. The pattern set is
   data, not code, so it is trivial to extend.

2. AST static scan (``scan_python_source``): parses Python source and flags
   calls that can execute arbitrary code or spawn processes from untrusted
   input (``eval``, ``exec``, ``compile``, ``__import__``, ``os.system``,
   ``os.popen``, ``subprocess.*``, ``pickle.loads``, ``marshal.loads``).
   Import aliases (``import subprocess as sp``, ``from os import system``)
   are resolved so obfuscated call sites are still caught. A syntax error in
   the scanned source is itself reported as a violation (untrusted/odd code).

Design (v1.3.0, task #127):
    * Pure standard library (``ast``, ``re``) — no new dependency.
    * Never raises on bad input: ``scan_python_source`` returns a violation
      describing the problem instead of throwing, so the caller can always
      make a deny decision.
    * The sub-agent hook expects ``scan(text) -> {"blocked": bool, "reason":
      str, "hits": [...]}``; ``scan`` is an alias of ``scan_text``.
"""
from __future__ import annotations

import ast
import base64
import os
import pathlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# --------------------------------------------------------------------------- #
# 1. Anti-injection text scan
# --------------------------------------------------------------------------- #

# High-confidence prompt-injection markers (case-insensitive, anchored on word
# boundaries where sensible). Deliberately narrow to avoid false positives on
# legitimate academic/scientific text. Extend by appending to this list.
INJECTION_PATTERNS: List[Dict[str, str]] = [
    {"id": "ignore-instructions",
     "re": r"ignore\s+(all|any|the|previous|above|prior)\s+(previous\s+)?instructions?"},
    {"id": "disregard-prompt",
     "re": r"disregard\s+(the\s+)?(previous|above|system|prior)\s+(instructions|prompt)"},
    {"id": "system-tag",
     "re": r"<\s*system\s*>"},
    {"id": "developer-mode",
     "re": r"developer\s*mode|jailbreak"},
    {"id": "override-role",
     "re": r"(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(a|an|the)?\s*(evil|unfiltered|uncensored|dm|god)"},
    {"id": "new-instructions",
     "re": r"new\s+instructions\s*[:\-]"},
    # -- v1.3.6: the English set above matched nothing in Chinese prose, and
    # -- this repository's users write Chinese.  Each pattern requires the
    # -- object of the verb to be a prompt artefact (指令/提示词/设定), so
    # -- ordinary prose such as 忽略不计 does not match.
    {"id": "zh-ignore-instructions",
     "re": r"(忽略|忽视|无视|忘记|忘掉|不要理会|别再管|抛开)\s*(掉)?\s*((之前|以上|上面|上述|前面|先前|原先|所有|全部|一切|系统|安全)\s*(的)?\s*){0,3}((说过|提到|讲到|给出|写下)\s*的?\s*)?(指令|指示|提示词|提示语|设定|要求|规则|限制)"},
    {"id": "zh-override-role",
     "re": r"(你现在是|从现在(开始|起)|接下来你是)[^。]{0,16}(不受|不必|无需|没有)\s*(任何)?\s*(限制|约束|审查)"},
    {"id": "zh-jailbreak",
     "re": r"(开发者模式|越狱模式|无限制模式|DAN\s*模式|绕过\s*(安全|内容)?\s*(限制|审核|过滤))"},
    {"id": "zh-reveal-prompt",
     "re": r"(输出|打印|显示|复述|告诉我)\s*(你的)?\s*(系统)?\s*(提示词|系统提示|初始指令)"},
    # -- English patterns the first set missed.
    {"id": "bypass-safety",
     "re": r"(ignore|disregard|bypass|override)\s+(the\s+)?(safety|security|content)\s+(rules|policy|policies|guidelines|filter)"},
    {"id": "reveal-system-prompt",
     "re": r"(reveal|print|show|repeat|leak)\s+(me\s+)?(your\s+)?(system\s+prompt|initial\s+instructions|hidden\s+prompt)"},
    {"id": "html-comment-instruction",
     "re": r"<!--[^>]{0,400}(ignore|disregard|bypass|忽略|无视|system\s*prompt)"},
]

_COMPILED = [(p["id"], re.compile(p["re"], re.IGNORECASE | re.UNICODE))
             for p in INJECTION_PATTERNS]

# Zero-width and bidi-control characters: invisible in a rendered document,
# decisive for a regex. Removed before matching, not after.
_INVISIBLE = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E,
     0x202A, 0x202B, 0x202C, 0x202D, 0x202E])

# Letters that look Latin but are not. NFKC folds full-width forms; these
# fold the Cyrillic and Greek lookalikes people use to slip past a keyword.
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p",
    "с": "c", "у": "y", "х": "x", "і": "i",
    "ѕ": "s", "ԁ": "d", "һ": "h", "т": "t",
    "α": "a", "ε": "e", "ι": "i", "ο": "o",
    "ρ": "p", "τ": "t", "ν": "v", "κ": "k",
})

# A base64 blob long enough to carry a sentence. Decoded once, scanned once:
# nobody hides an instruction in eight bytes.
_B64_BLOB = re.compile(r"[A-Za-z0-9+/]{32,}={0,2}")
_B64_LIMIT = 8
_WHITESPACE = chr(13) + chr(10) + chr(9)


def _normalise(text: str) -> str:
    """Fold away the ways a keyword can be written without looking like it."""
    folded = unicodedata.normalize("NFKC", text).translate(_INVISIBLE)
    return folded.translate(_CONFUSABLES)


def _decoded_payloads(text: str):
    """Yield the readable text hidden in base64 blobs, most blobs first."""
    for index, match in enumerate(_B64_BLOB.finditer(text)):
        if index >= _B64_LIMIT:
            return
        blob = match.group(0)
        try:
            raw = base64.b64decode(blob + "=" * (-len(blob) % 4),
                                   validate=True)
            decoded = raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        printable = sum(1 for ch in decoded
                        if ch.isprintable() or ch in _WHITESPACE)
        if len(decoded) >= 8 and printable > len(decoded) * 0.9:
            yield decoded


def scan_text(text: str) -> Dict[str, object]:
    """Scan external text for injection markers.

    Returns {"blocked": bool, "reason": str, "hits": [pattern-id, ...]}.
    """
    hits: List[str] = []
    if text:
        normalised = _normalise(str(text))
        for pid, rx in _COMPILED:
            if rx.search(normalised):
                hits.append(pid)
        if not hits:
            # Encoded instructions: an ASCII-safe wrapper changes nothing
            # about what the model would eventually read.
            for decoded in _decoded_payloads(normalised):
                decoded = _normalise(decoded)
                for pid, rx in _COMPILED:
                    if rx.search(decoded):
                        hits.append(pid + "@base64")
                        break
                if hits:
                    break
    return {
        "blocked": bool(hits),
        "reason": ("injection markers: " + ", ".join(hits)) if hits else "",
        "hits": hits,
    }


# Alias so the sub-agent hook can do `from core.security_shield import scan`.
scan = scan_text


# --------------------------------------------------------------------------- #
# 2. AST static scan of Python source
# --------------------------------------------------------------------------- #

# Bare builtin calls that execute arbitrary code / read input.
BANNED_NAMES = frozenset({"eval", "exec", "compile", "__import__", "input"})

# Qualified calls (resolved after import-alias expansion).
BANNED_QUALIFIED = frozenset({
    "os.system", "os.popen", "os.exec", "os.execv", "os.execve",
    "os.spawn", "os.spawnv",
    "subprocess.Popen", "subprocess.run", "subprocess.call",
    "subprocess.check_call", "subprocess.check_output", "subprocess.getoutput",
    "pickle.loads", "pickle.load", "marshal.loads", "marshal.load",
    "builtins.eval", "builtins.exec", "builtins.__import__",
})


@dataclass
class Violation:
    """One flagged dangerous call site (or a parse failure)."""

    line: int
    col: int
    kind: str          # "call" | "syntax" | "unknown"
    name: str          # qualified call name, or "<syntax>"
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "line": self.line, "col": self.col, "kind": self.kind,
            "name": self.name, "reason": self.reason,
        }


def _build_aliases(tree: ast.AST) -> Dict[str, str]:
    """Map bare identifiers to their module-qualified origin.

    Tracks ``import subprocess as sp`` -> {"sp": "subprocess"} and
    ``from os import system`` -> {"system": "os.system"} so obfuscated call
    sites resolve to the banned qualified name.
    """
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                if a.name == "*":
                    continue
                aliases[a.asname or a.name] = f"{mod}.{a.name}"
    return aliases


def _qualified_name(func, aliases: Dict[str, str]) -> Optional[str]:
    """Resolve a Call's func node to a dotted name, or None."""
    if isinstance(func, ast.Name):
        return aliases.get(func.id, func.id)
    if isinstance(func, ast.Attribute):
        base = _qualified_name(func.value, aliases)
        if base is None:
            return None
        return f"{base}.{func.attr}"
    return None


def scan_python_source(src: str) -> List[Violation]:
    """Statically flag dangerous call sites in Python `src`."""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [Violation(line=getattr(exc, "lineno", 0) or 0,
                          col=getattr(exc, "offset", 0) or 0,
                          kind="syntax",
                          name="<syntax>",
                          reason=f"syntax error: {exc.msg}")]
    except Exception as exc:  # pragma: no cover - defensive
        return [Violation(line=0, col=0, kind="unknown", name="<unknown>",
                          reason=f"could not parse: {exc}")]

    aliases = _build_aliases(tree)
    violations: List[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        qualified = _qualified_name(node.func, aliases)
        if qualified is None:
            continue
        name = qualified
        if name in BANNED_QUALIFIED or name in BANNED_NAMES:
            violations.append(Violation(
                line=node.lineno, col=node.col_offset,
                kind="call", name=name,
                reason=f"dangerous call: {name}()"))
    return violations


def scan_file(path: str) -> List[Violation]:
    """Read `path` and scan it; returns [] for missing/unreadable files."""
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except Exception as exc:
        return [Violation(line=0, col=0, kind="unknown", name="<io>",
                          reason=f"cannot read {path}: {exc}")]
    return scan_python_source(src)


def shield_report(src: str) -> Dict[str, object]:
    """Convenience: scan source and return a structured allow/deny report.

    Used by the security-guard skill (#128) and CI hooks.
    """
    vios = scan_python_source(src)
    return {
        "allowed": not vios,
        "violation_count": len(vios),
        "violations": [v.to_dict() for v in vios],
    }


# Extensions that name a file rather than carry the payload inline.
_PATHLIKE = frozenset(".py .md .txt .json .yaml .yml .csv .tex .bib .html .xml "
                      ".pdf .ipynb .sh .ps1 .js .ts".split())


def looks_like_path(raw: str) -> bool:
    """True when --input names a file rather than carrying the payload itself."""
    return ("/" in raw or "\\" in raw or raw.startswith((".", "~"))
            or pathlib.Path(raw).suffix.lower() in _PATHLIKE)


def resolve_input(root: str, raw: Optional[str], mode: str = "auto"):
    """Resolve a security-guard ``--input`` into ``(payload, mode, error)``.

    A missing file is an **error**, never a silent pass: scanning the path
    string as if it were the text would let the caller believe the file was
    checked. Relative paths resolve against ``root`` first (the precedence
    every adapter uses), so the router's auto-wired workspace-relative
    ``--input`` finds its file instead of failing against the repo cwd.
    """
    if not raw:
        return None, None, None          # nothing declared: smoke run
    from lib.chelate_core import paths as _paths
    src = pathlib.Path(_paths.resolve_input(root, raw))
    if src.is_file():
        auto = "source" if src.suffix == ".py" else "text"
        return src.read_text(encoding="utf-8"), mode if mode != "auto" else auto, None
    if looks_like_path(raw):
        return None, None, f"input file not found: {raw}"
    return raw, mode if mode != "auto" else "text", None


__all__ = [
    "INJECTION_PATTERNS", "BANNED_NAMES", "BANNED_QUALIFIED",
    "Violation", "scan_text", "scan", "scan_python_source", "scan_file",
    "shield_report", "looks_like_path", "resolve_input",
]
