"""New-skill unit tests: the shared lib/chelate_core cores (offline-safe).

The five v1.1.0 skills are thin adapters over lib/chelate_core, so the unit
tests exercise the library cores directly (the adapters themselves are
covered end-to-end by the router and capability-guard suites).
"""
from __future__ import annotations

from conftest import run_in_skill

# Every snippet puts the repo root on sys.path and imports the shared core.

# ---------------------------------------------------------------- fulltext

PDF_EXTRACT = """
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.getcwd())
import fitz
from lib.chelate_core import pdf_text
ws = Path(tempfile.mkdtemp())
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 72), "Chelate fulltext extraction test page one.")
doc.save(ws / "sample.pdf")
doc.close()
res = pdf_text.extract(ws / "sample.pdf", "", ws / "out")  # "" = all pages
text = (ws / "out" / "sample.txt").read_text(encoding="utf-8") \\
    if (ws / "out" / "sample.txt").exists() else ""
print(json.dumps({"ok": "Chelate fulltext extraction test" in text,
                  "chars": len(text), "res": str(res)[:120]}))
"""

# ---------------------------------------------------------------- bibtex

BIB_DEDUPE = """
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.getcwd())
from lib.chelate_core import bibtex_norm
ws = Path(tempfile.mkdtemp())
bib = ws / "refs.bib"
# two different citation keys, same title+year -> content-level duplicate
bib.write_text(
    "@article{a2020, title={Alpha Scattering}, author={Smith, J}, year={2020}}\\n"
    "@article{a2020b, title={Alpha Scattering}, author={Smith, J}, year={2020}}\\n"
    "@book{b2021, title={Beta Decay}, author={Roe, R}, year={2021}}\\n",
    encoding="utf-8")
report = bibtex_norm.normalize(bib, ws / "out")
print(json.dumps({"total": report["total"], "unique": report["unique"],
                  "dups": len(report["duplicates"])}))
"""

# ---------------------------------------------------------------- profiler

PROFILE_CSV = """
import csv, json, os, random, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.getcwd())
from lib.chelate_core import csv_profile
ws = Path(tempfile.mkdtemp())
csv_path = ws / "sensor.csv"
random.seed(7)
with open(csv_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t", "v", "note"])
    for i in range(60):
        v = 20 + 0.1 * i + random.gauss(0, 0.3)
        if i == 5:
            v = ""
        if i in (30, 31):
            v = 999.0
        w.writerow([i, v, "" if i % 2 else "x"])
report = csv_profile.profile_csv(csv_path)
cols = {c["column"]: c for c in report["columns"]}
print(json.dumps({
    "rows": report["rows"],
    "cols": report["cols"],
    "missing_v": cols["v"]["missing"],
    "outlier_v": cols["v"]["outliers"],
    "has_note": "note" in cols,
}))
"""

PROFILE_CSV_FENCE = """
import csv, json, os, random, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.getcwd())
from lib.chelate_core import csv_profile
ws = Path(tempfile.mkdtemp())
csv_path = ws / "sensor.csv"
random.seed(7)
with open(csv_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t", "v"])
    for i in range(60):
        v = 20 + 0.1 * i + random.gauss(0, 0.3)
        if i in (30, 31):
            v = 999.0
        w.writerow([i, v])
wide = csv_profile.profile_csv(csv_path, fence=3.0)
narrow = csv_profile.profile_csv(csv_path, fence=1.5)
print(json.dumps({"wide": wide["columns"][1]["outliers"],
                  "narrow": narrow["columns"][1]["outliers"]}))
"""

# ---------------------------------------------------------------- auditor

DOI_REGEX = """
import json, os, sys
sys.path.insert(0, os.getcwd())
from lib.chelate_core import doi_audit
text = ("See [1] https://doi.org/10.1103/PhysRevD.101.055031 and "
        "doi:10.9999/fake-doi-12345 plus 10.1000/xyz123 inline.")
dois = doi_audit.extract_dois(text)
print(json.dumps({"dois": sorted(dois), "count": len(dois)}))
"""

# ---------------------------------------------------------------- pages

PAGES_PARSE = """
import json, os, sys
sys.path.insert(0, os.getcwd())
from lib.chelate_core import pdf_text
print(json.dumps({
    "all": pdf_text.parse_pages("", 5),
    "range": pdf_text.parse_pages("2-4", 5),
    "mixed": pdf_text.parse_pages("1,3,9", 5),
    "garbage": pdf_text.parse_pages("abc", 5),
}))
"""

# ---------------------------------------------------------------- config

CONFIG_LOAD = """
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.getcwd())
from lib.chelate_core import yamlmini, adapter
root = Path(tempfile.mkdtemp())
(root / "assets").mkdir()
(root / "assets" / "config.yaml").write_text(
    "max_results: 7\\nsort_by: submittedDate\\nflag: true\\n"
    "items: [a, b]\\nnested:\\n  key: 1\\n", encoding="utf-8")
cfg = yamlmini.load_config(str(root))
print(json.dumps({"cfg": cfg, "merged": adapter.load_config(str(root),
      {"max_results": 10})}))
"""


def test_fulltext_extractor_reads_pdf():
    out = run_in_skill("fulltext-extractor", PDF_EXTRACT)
    assert out["ok"], out
    assert out["chars"] > 10


def test_bibtex_normalizer_dedupes():
    out = run_in_skill("bibtex-normalizer", BIB_DEDUPE)
    assert out["total"] >= 3, out
    assert out["unique"] == 2, f"expected 2 unique entries: {out}"
    assert out["dups"] >= 1, out


def test_data_profiler_counts_missing_and_outliers():
    out = run_in_skill("data-profiler", PROFILE_CSV)
    assert out["rows"] == 60, out
    assert out["cols"] == 3, out
    assert out["missing_v"] == 1, out
    assert out["outlier_v"] >= 2, f"999.0 spikes must be outliers: {out}"


def test_data_profiler_fence_is_configurable():
    out = run_in_skill("data-profiler", PROFILE_CSV_FENCE)
    assert out["wide"] <= out["narrow"], \
        f"a wider Tukey fence must flag fewer or equal outliers: {out}"


def test_reference_auditor_extracts_dois():
    out = run_in_skill("reference-auditor", DOI_REGEX)
    assert "10.1103/PhysRevD.101.055031" in out["dois"], out
    assert "10.9999/fake-doi-12345" in out["dois"], out
    assert "10.1000/xyz123" in out["dois"], out
    assert out["count"] == 3, out


def test_pdf_page_spec_parsing():
    out = run_in_skill("fulltext-extractor", PAGES_PARSE)
    assert out["all"] == [0, 1, 2, 3, 4], out
    assert out["range"] == [1, 2, 3], out
    assert out["mixed"] == [0, 2], out       # page 9 clipped to n_pages=5
    assert out["garbage"] == [0, 1, 2, 3, 4], out  # unparsable -> all pages


def test_yamlmini_loads_flat_subset_without_pyyaml():
    out = run_in_skill("data-profiler", CONFIG_LOAD)
    cfg = out["cfg"]
    assert cfg["max_results"] == 7, cfg
    assert cfg["sort_by"] == "submittedDate", cfg
    assert cfg["flag"] is True, cfg
    assert cfg["items"] == ["a", "b"], cfg
    assert out["merged"]["max_results"] == 7, out  # file value wins


def test_new_skill_dependency_importable():
    """Every declared third-party dependency must import in this env."""
    import importlib
    from conftest import SKILLS_DIR
    import json as _json
    for skill, dep in [("fulltext-extractor", "fitz"),
                       ("literature-retriever", "arxiv"),
                       ("bibtex-normalizer", "bibtexparser"),
                       ("reference-auditor", "requests"),
                       ("data-profiler", "pandas")]:
        manifest = _json.loads((SKILLS_DIR / skill / "manifest.json")
                               .read_text(encoding="utf-8"))
        assert dep in manifest["dependencies"], \
            f"{skill} manifest does not declare {dep}"
        try:
            importlib.import_module(dep)
        except Exception as exc:  # pragma: no cover - env dependent
            raise AssertionError(f"{skill} requires {dep}: {exc}")


# ------------------------------------------------------- input resolution

def test_resolve_input_prefers_workspace_root(tmp_path, monkeypatch):
    """Relative --input must resolve against --root, not the adapter cwd.

    The Router launches adapters with cwd=repository root, so a
    workspace-relative path (the documented usage) only works when the
    adapter resolves it against the workspace root.
    """
    import os
    import sys
    sys.path.insert(0, os.getcwd())
    from pathlib import Path
    from lib.chelate_core import paths

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "draft.md").write_text("hello", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "cwd.md").write_text("cwd copy", encoding="utf-8")
    monkeypatch.chdir(elsewhere)  # simulate the router's cwd=repo root

    # workspace-relative: only exists under root -> resolved against root
    assert paths.resolve_input(str(ws), "draft.md") == ws / "draft.md"
    # cwd-relative that exists: passes through unchanged (still opens
    # correctly relative to the current directory)
    assert paths.resolve_input(str(ws), "cwd.md") == Path("cwd.md")
    # absolute paths pass through untouched
    abs_path = tmp_path / "abs.md"
    abs_path.write_text("abs", encoding="utf-8")
    assert paths.resolve_input(str(ws), str(abs_path)) == abs_path
    # missing everywhere: original path returned for an honest error message
    missing = paths.resolve_input(str(ws), "nope.md")
    assert missing == Path("nope.md")


def test_resolve_inputs_reports_missing_separately(tmp_path):
    """Batch resolution: found files -> absolute paths, rest -> missing."""
    import os
    import sys
    sys.path.insert(0, os.getcwd())
    from lib.chelate_core import paths

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "here.md").write_text("x", encoding="utf-8")
    resolved, missing = paths.resolve_inputs(
        str(ws), ["here.md", "ghost.md", str(ws / "here.md")])
    assert [os.path.basename(p) for p in resolved] == ["here.md", "here.md"]
    assert missing == ["ghost.md"]
    assert all(os.path.isabs(p) for p in resolved)


def test_resolve_input_handles_unicode_filenames(tmp_path):
    """The documented `--inputs 我的文件.md` case must resolve under root."""
    import os
    import sys
    sys.path.insert(0, os.getcwd())
    from lib.chelate_core import paths

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "我的文件.md").write_text("x", encoding="utf-8")
    resolved = paths.resolve_input(str(ws), "我的文件.md")
    assert resolved == ws / "我的文件.md"
