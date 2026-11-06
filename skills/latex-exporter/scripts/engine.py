"""latex-exporter engine -- merge Markdown reports + figures into a .tex file.

Reads the Markdown reports generated under ``<root>/process/`` and the graphics
under ``<root>/process/figures/`` and concatenates them into a single,
compilable LaTeX source file. Pure standard library -- **no pandoc, no heavy
dependency** (the converter is a small, self-contained Markdown subset
renderer written from scratch here).

Markdown subset handled: ATX headings, fenced code blocks (verbatim), pipe
tables, bullet / numbered lists, block quotes, horizontal rules, and inline
bold / italic / inline-code / links / images / $...$ math. LaTeX special
characters are escaped; math and code are protected from escaping.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

_GFX_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".eps")
_CJK = re.compile(r"[\u4e00-\u9fff]")
# Compiled once at module level so md_to_latex() does not recompile these on
# every call (they were previously local to the function).
_RE_FENCE = re.compile(r"^\s*(```|~~~)")
_RE_UL = re.compile(r"^[-*+]\s+")
_RE_OL = re.compile(r"^\d+\.\s+")
_RE_HR = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")


def _verdict(status: str, evidence: str, reason: str,
             data: Optional[dict] = None, artifacts: Optional[List[str]] = None) -> dict:
    return {"status": status, "evidence_level": evidence, "reason": reason,
            "artifacts": artifacts or [], "data": data or {}}


# ---------------------------------------------------------------------------
# escaping + inline conversion
# ---------------------------------------------------------------------------

def _escape(s: str) -> str:
    """Escape LaTeX special characters (asterisk is intentionally left: it is
    not a LaTeX special and is needed as an emphasis marker)."""
    s = s.replace("\\", "\x01BACKSLASH\x01")
    for ch, rep in (("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                    ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
                    ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")):
        s = s.replace(ch, rep)
    return s.replace("\x01BACKSLASH\x01", r"\textbackslash{}")


def _inline(text: str) -> str:
    """Convert inline Markdown to LaTeX, protecting math and code."""
    ph: List[str] = []

    def stash(value: str) -> str:
        ph.append(value)
        return f"\x00{len(ph) - 1}\x00"

    text = re.sub(r"\$\$(.+?)\$\$", lambda m: stash("\\[\n" + m.group(1) + "\n\\]"),
                  text, flags=re.S)
    text = re.sub(r"\$(.+?)\$", lambda m: stash("\\(" + m.group(1) + "\\)"),
                  text, flags=re.S)
    text = re.sub(r"`([^`]+)`",
                  lambda m: stash(r"\texttt{" + _escape(m.group(1)) + "}"), text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
                  lambda m: stash(r"\includegraphics{" + m.group(2) + "}"), text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: stash(r"\href{" + m.group(2) + "}{"
                                  + _escape(m.group(1)) + "}"), text)
    text = _escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: ph[int(m.group(1))], text)


# ---------------------------------------------------------------------------
# block conversion
# ---------------------------------------------------------------------------

def _cells(row: str) -> List[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


def _table(rows: List[str]) -> str:
    header = _cells(rows[0])
    has_sep = (len(rows) >= 2 and set(rows[1]) <= set("|:- ")
               and "-" in rows[1])
    data = [_cells(r) for r in (rows[2:] if has_sep else rows[1:])]
    ncol = len(header)
    out = [r"\begin{tabular}{" + ("l" * ncol) + "}", r"\hline"]
    out.append(" & ".join(_inline(c) for c in header) + r" \\")
    out.append(r"\hline")
    for drow in data:
        drow = (drow + [""] * ncol)[:ncol]
        out.append(" & ".join(_inline(c) for c in drow) + r" \\")
    out.append(r"\hline")
    out.append(r"\end{tabular}")
    return "\n".join(out)


def md_to_latex(md: str) -> str:
    """Convert a Markdown document (subset) to a LaTeX body fragment."""
    lines = md.splitlines()
    out: List[str] = []
    para: List[str] = []
    i, n = 0, len(lines)

    def flush():
        if para:
            out.append(_inline(" ".join(para).strip()))
            out.append("")
            para.clear()

    fence, ul, ol, hr = _RE_FENCE, _RE_UL, _RE_OL, _RE_HR

    while i < n:
        line = lines[i]
        s = line.strip()
        if fence.match(s):
            flush()
            out.append(r"\begin{verbatim}")
            i += 1
            while i < n and not fence.match(lines[i].strip()):
                out.append(lines[i])
                i += 1
            i += 1
            out.append(r"\end{verbatim}")
            out.append("")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            flush()
            cmd = {1: "section", 2: "subsection", 3: "subsubsection",
                   4: "paragraph"}[len(m.group(1))]
            out.append("\\" + cmd + "{" + _inline(m.group(2).strip()) + "}")
            out.append("")
            i += 1
            continue
        if hr.match(s):
            flush()
            out.append(r"\noindent\hrulefill")
            out.append("")
            i += 1
            continue
        if s.startswith("|"):
            flush()
            tbl = []
            while i < n and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            out.append(_table(tbl))
            out.append("")
            continue
        if s.startswith(">"):
            flush()
            q = []
            while i < n and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(r"\begin{quote}")
            out.append(_inline(" ".join(q)))
            out.append(r"\end{quote}")
            out.append("")
            continue
        if ul.match(s):
            flush()
            out.append(r"\begin{itemize}")
            while i < n and ul.match(lines[i].strip()):
                out.append(r"  \item " + _inline(ul.sub("", lines[i].strip())))
                i += 1
            out.append(r"\end{itemize}")
            out.append("")
            continue
        if ol.match(s):
            flush()
            out.append(r"\begin{enumerate}")
            while i < n and ol.match(lines[i].strip()):
                out.append(r"  \item " + _inline(ol.sub("", lines[i].strip())))
                i += 1
            out.append(r"\end{enumerate}")
            out.append("")
            continue
        if not s:
            flush()
            i += 1
            continue
        para.append(s)
        i += 1
    flush()
    return "\n".join(out).strip()


# ---------------------------------------------------------------------------
# document assembly
# ---------------------------------------------------------------------------

def _caption(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").strip().capitalize() or stem


def _preamble(cjk: bool) -> str:
    lines = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{graphicx}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{geometry}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\geometry{margin=1in}",
    ]
    if cjk:
        lines.append(r"\usepackage{ctex}  % CJK detected: compile with XeLaTeX/LuaLaTeX")
    return "\n".join(lines)


def _find_reports(process_dir: str) -> List[str]:
    found: List[str] = []
    for base, _dirs, files in os.walk(process_dir):
        for f in files:
            if f.lower().endswith(".md"):
                found.append(os.path.join(base, f))
    return sorted(found)


def _find_figures(fig_dir: str) -> List[str]:
    if not os.path.isdir(fig_dir):
        return []
    return sorted(os.path.join(fig_dir, f) for f in os.listdir(fig_dir)
                  if f.lower().endswith(_GFX_EXT))


def build_document(reports: List[str], figures: List[str], out_dir: str,
                   title: str) -> str:
    texts: List[str] = []
    for path in reports:
        with open(path, encoding="utf-8") as fh:
            texts.append(fh.read())
    cjk = bool(_CJK.search(title)) or any(_CJK.search(t) for t in texts)

    parts: List[str] = [_preamble(cjk)]
    parts.append("")
    parts.append("\\title{" + _escape(title) + "}")
    parts.append(r"\author{}")
    parts.append(r"\date{\today}")
    parts.append(r"\begin{document}")
    parts.append(r"\maketitle")
    parts.append("")

    if reports:
        for idx, _path in enumerate(reports):
            body = md_to_latex(texts[idx])
            if idx:
                parts.append(r"\clearpage")
                parts.append("")
            parts.append(body)
            parts.append("")
    else:
        parts.append("% no Markdown reports found under process/")
        parts.append("")

    if figures:
        parts.append(r"\clearpage")
        parts.append(r"\section{Figures}")
        for path in figures:
            rel = os.path.relpath(path, out_dir).replace("\\", "/")
            stem = os.path.splitext(os.path.basename(path))[0]
            parts.append(r"\begin{figure}[htbp]")
            parts.append(r"  \centering")
            parts.append(r"  \includegraphics[width=0.85\textwidth]{" + rel + "}")
            parts.append(r"  \caption{" + _escape(_caption(stem)) + "}")
            parts.append(r"  \label{fig:" + re.sub(r"[^A-Za-z0-9]", "", stem) + "}")
            parts.append(r"\end{figure}")
            parts.append("")

    parts.append(r"\end{document}")
    return "\n".join(parts).rstrip() + "\n"


def export(root: Optional[str] = None, out_name: str = "merged_report.tex") -> dict:
    """Merge ``<root>/process/**/*.md`` and ``<root>/process/figures/*`` into a
    single ``.tex`` file under ``<root>/process/latex/``."""
    root = root or "."
    process_dir = os.path.join(root, "process")
    fig_dir = os.path.join(process_dir, "figures")
    out_dir = os.path.join(process_dir, "latex")

    reports = _find_reports(process_dir)
    figures = _find_figures(fig_dir)

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name or "merged_report.tex")
    tex = build_document(reports, figures, out_dir,
                         os.path.splitext(os.path.basename(out_path))[0])
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(tex)

    reason = (f"merged {len(reports)} markdown report(s) and "
              f"{len(figures)} figure(s) into {out_path}")
    if not reports and not figures:
        reason += " (no inputs found; wrote a compilable skeleton)"
    data = {"tex": out_path,
            "reports": [os.path.basename(r) for r in reports],
            "figures": [os.path.basename(f) for f in figures]}
    return _verdict("PASS", "EXACT", reason, data, artifacts=[out_path])
