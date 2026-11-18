"""secret-gate's engine — credential shapes in a tree, reported without the secret.

Caller: skills/secret-gate/run.py.

Data schemas:
    Reads:  any UTF-8 text file under the target directory (`.git`,
            dependency caches and build output are skipped), plus an
            allowlist: `.chelate/secret-allowlist.json` by default.
    Writes: nothing. The adapter writes the gate and the report beside it.

The report is the point. A scanner that prints the credential it found has
copied the credential into a gate file, a CI log and an agent's context, so
every finding carries a **fingerprint** (SHA-256 prefix) instead of the
match: enough to recognise the same string again, not enough to use it.

Two rule classes, because they fail differently:

    **Shape rules** know what a credential looks like (AWS, GitHub, Slack,
    Google, private-key headers, `sk-` keys). Precision is the point; a
    shape rule that misses a format is fixed by adding the format.

    **Context rules** (`name = "..."`) and **entropy** catch the credentials
    nobody wrote a shape for. They are the ones that produce false positives
    on fixtures and documentation, which is why the allowlist exists and why
    an allowed finding is still counted, never silently dropped.

A line may carry `chelate-secret-allow` to exempt itself — that is a
deliberate, visible edit in the file itself, not a global setting.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Any, Dict, Iterable, List, Tuple

SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".venv", "venv", "env", "dist", "build",
    ".tox", ".idea", ".vscode", "site-packages",
})
MAX_BYTES = 2 * 1024 * 1024
SNIFF_BYTES = 8192
ALLOW_PRAGMA = "chelate-secret-allow"
ALLOWLIST_PATH = os.path.join(".chelate", "secret-allowlist.json")

# (rule name, pattern). Order matters: the first shape that matches a line
# wins, so the context and entropy rules never double-report a known shape.
SHAPE_RULES: Tuple[Tuple[str, re.Pattern], ...] = (
    ("private-key-block",
     re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("provider-key", re.compile(r"\b(?:sk|sk-ant)-[A-Za-z0-9_\-]{20,}\b")),
)

CONTEXT_RULE = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|pwd|credential|"
    r"access[_-]?key|private[_-]?key)\b\s*[:=]\s*['\"]?"
    r"([A-Za-z0-9+/=_\-.!@#$%^&*]{16,})")
ENTROPY_CANDIDATE = re.compile(
    r"[:=]\s*['\"]?([A-Za-z0-9+/=_\-]{32,})['\"]?")
ENTROPY_MIN = 4.0          # bits per character; random keys sit near 4.5-6
PRAGMA_RULE = re.compile(
    r"chelate-secret-allow\s*:\s*([A-Za-z0-9_-]+)")


def fingerprint(secret: str) -> str:
    """A stable, non-reversible handle for a matched string."""
    return hashlib.sha256(secret.encode("utf-8", "replace")).hexdigest()[:12]


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: Dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    total = float(len(text))
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def scan_text(text: str, relpath: str) -> List[Dict[str, Any]]:
    """Findings for one file, in line order. The secret itself is not kept."""
    found: List[Dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_PRAGMA in line:
            named = PRAGMA_RULE.search(line)
            if not named:
                continue  # bare pragma: the whole line is exempt
        else:
            named = None
        secret = ""
        rule = ""
        for name, pattern in SHAPE_RULES:
            match = pattern.search(line)
            if match:
                rule, secret = name, match.group(0)
                break
        if not rule:
            match = CONTEXT_RULE.search(line)
            if match:
                rule, secret = "secret-assignment", match.group(1)
        if not rule:
            match = ENTROPY_CANDIDATE.search(line)
            if match and _entropy(match.group(1)) >= ENTROPY_MIN:
                rule, secret = "high-entropy-string", match.group(1)
        if not rule:
            continue
        if named and named.group(1) == rule:
            continue
        found.append({"path": relpath, "line": number, "rule": rule,
                      "fingerprint": fingerprint(secret),
                      "length": len(secret)})
    return found


def iter_text_files(base: str) -> Iterable[str]:
    """Every readable text file under `base`, in a stable order.

    Binary files, symlinks and files over `MAX_BYTES` are skipped rather
    than guessed at: a scanner that decodes a .png as text invents findings.
    """
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = os.path.join(root, name)
            if os.path.islink(path):
                continue
            try:
                if os.path.getsize(path) > MAX_BYTES:
                    continue
                with open(path, "rb") as fh:
                    head = fh.read(SNIFF_BYTES)
            except OSError:
                continue
            if b"\x00" in head:
                continue
            yield path


def load_allowlist(path: str) -> Dict[str, Any]:
    """`{fingerprints: [...], entries: [{rule, path}]}`; missing file is empty."""
    empty: Dict[str, Any] = {"fingerprints": set(), "entries": []}
    if not path or not os.path.isfile(path):
        return empty
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    prints = {str(v) for v in data.get("fingerprints") or []}
    entries = [e for e in data.get("entries") or []
               if isinstance(e, dict) and e.get("path")]
    return {"fingerprints": prints, "entries": entries}


def _allowed(finding: Dict[str, Any], allow: Dict[str, Any]) -> bool:
    if finding["fingerprint"] in allow["fingerprints"]:
        return True
    for entry in allow["entries"]:
        rule = entry.get("rule")
        path = str(entry.get("path"))
        if path != finding["path"]:
            continue
        if not rule or rule == finding["rule"]:
            return True
    return False


def scan(base: str, allowlist: str = "") -> Dict[str, Any]:
    """Scan a directory; findings are sorted and never carry the secret."""
    base = os.path.abspath(base)
    if not os.path.isdir(base):
        raise ValueError(f"not a directory: {base}")
    allow = load_allowlist(allowlist)
    findings: List[Dict[str, Any]] = []
    allowed = 0
    scanned = 0
    files = iter_text_files(base)
    for path in files:
        rel = os.path.relpath(path, base).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        scanned += 1
        for finding in scan_text(text, rel):
            if _allowed(finding, allow):
                allowed += 1
                continue
            findings.append(finding)
    findings.sort(key=lambda f: (f["path"], f["line"], f["rule"]))
    return {"root": base, "files_scanned": scanned, "findings": findings,
            "allowed": allowed,
            "rules": [name for name, _ in SHAPE_RULES]
                     + ["secret-assignment", "high-entropy-string"]}


def summarise(report: Dict[str, Any], limit: int = 3) -> str:
    """One line for the gate: counts plus the first few locations."""
    findings = report["findings"]
    if not findings:
        return (f"{report['files_scanned']} file(s) scanned; no credential "
                f"shapes" + (f" ({report['allowed']} allowlisted)"
                             if report["allowed"] else ""))
    shown = ", ".join(
        f"{f['path']}:{f['line']} ({f['rule']}, {f['fingerprint']})"
        for f in findings[:limit])
    more = "" if len(findings) <= limit else f" and {len(findings) - limit} more"
    return f"{len(findings)} finding(s): {shown}{more}"
