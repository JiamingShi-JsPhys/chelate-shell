"""latex-exporter skill tests: Markdown+figures -> .tex merging, inline
conversion correctness, the empty-workspace skeleton, and the CLI gate.

No heavy dependency: the engine is pure standard library, so every test here
runs unconditionally. The engine is loaded directly from scripts/ via importlib
under a unique module name.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import pytest

from conftest import REPO_ROOT, SKILLS_DIR

LX_SCRIPTS = SKILLS_DIR / "latex-exporter" / "scripts"
LX_RUN = SKILLS_DIR / "latex-exporter" / "scripts" / "run.py"


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "latex_exporter_engine", LX_SCRIPTS / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_workspace(root):
    proc = root / "process"
    (proc / "reports").mkdir(parents=True, exist_ok=True)
    (proc / "figures").mkdir(parents=True, exist_ok=True)
    (proc / "reports" / "results.md").write_text(
        "# Results\n\nA **bold** and *italic* line with `code`, $E=mc^2$, "
        "100% & under_score.\n\n"
        "## Table\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
        "- one\n- two\n\n```python\nx = 1\n```\n\n"
        "> quoted\n\n[docs](https://example.com/a_b)\n",
        encoding="utf-8")
    (proc / "figures" / "fig_1-loss.pdf").write_bytes(b"%PDF-1.4 dummy")
    (proc / "figures" / "fig_2-acc.png").write_bytes(b"\x89PNG dummy")
    return proc


# ------------------------------------------------- unit: conversion

def test_export_merges_reports_and_figures(tmp_path):
    e = _load_engine()
    _seed_workspace(tmp_path)
    res = e.export(root=str(tmp_path))
    assert res["status"] == "PASS"
    assert res["evidence_level"] == "EXACT"
    tex_path = res["artifacts"][0]
    tex = open(tex_path, encoding="utf-8").read()
    for tok in (r"\documentclass[11pt]{article}", r"\begin{document}",
                r"\end{document}", r"\section{Results}", r"\subsection{Table}",
                r"\begin{tabular}", r"\begin{itemize}", r"\begin{verbatim}",
                r"\begin{quote}", r"\section{Figures}", r"\includegraphics",
                r"\caption{Fig 1 loss}"):
        assert tok in tex, f"missing {tok!r}"
    # figures referenced by a workspace-relative path
    assert "../figures/fig_1-loss.pdf" in tex
    assert len(res["data"]["reports"]) == 1
    assert len(res["data"]["figures"]) == 2


def test_inline_conversions_and_escaping(tmp_path):
    e = _load_engine()
    frag = e.md_to_latex(
        "A **bold** *italic* `co_de` $x^2$ 100% & a_b [t](http://e.com/a_b).")
    assert r"\textbf{bold}" in frag
    assert r"\textit{italic}" in frag
    assert r"\texttt{co\_de}" in frag          # code content escaped
    assert r"\(x^2\)" in frag                   # math preserved (^ not escaped)
    assert r"100\% \& a\_b" in frag             # specials escaped
    assert r"\href{http://e.com/a_b}{t}" in frag  # URL kept raw


def test_empty_workspace_writes_skeleton(tmp_path):
    e = _load_engine()
    (tmp_path / "process").mkdir(parents=True, exist_ok=True)
    res = e.export(root=str(tmp_path))
    assert res["status"] == "PASS"
    tex = open(res["artifacts"][0], encoding="utf-8").read()
    assert r"\documentclass" in tex and r"\begin{document}" in tex
    assert r"\end{document}" in tex
    assert res["data"]["reports"] == [] and res["data"]["figures"] == []


def test_cjk_adds_ctex(tmp_path):
    e = _load_engine()
    proc = tmp_path / "process"
    (proc / "reports").mkdir(parents=True, exist_ok=True)
    (proc / "reports" / "cn.md").write_text("# 结果\n\n中文内容。\n",
                                            encoding="utf-8")
    res = e.export(root=str(tmp_path))
    tex = open(res["artifacts"][0], encoding="utf-8").read()
    assert r"\usepackage{ctex}" in tex


# ------------------------------------------------- CLI integration

def test_cli_emits_gate_via_subprocess(tmp_path):
    _seed_workspace(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(LX_RUN), "--root", str(tmp_path),
         "--action", "process", "--name", "out.tex"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-500:]
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["status"] == "PASS", payload
    assert (tmp_path / "process" / "latex" / "out.tex").is_file()
    gates = sorted((tmp_path / "process" / "gates").glob(
        "latex-exporter_*.json"))
    assert gates, "no gate written into the workspace"
