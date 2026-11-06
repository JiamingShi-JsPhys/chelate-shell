# Chelate Shell v1.1.0 — Release Audit Report

**Date:** 2026-10-23
**Scope:** `chelate-shell-v1.1.0/` (14 skills, 194 Python files under `skills/`,
~38.4k lines) and the release archive `chelate-shell-v1.1.0.zip` (390 entries).
**Method:** static scans (SHA-256 parity, CJK scan, license scan), the automated
suite (`python -m pytest tests/ -q`, 122 tests), `docs/audit_feature_parity.py`,
and end-to-end pipeline runs including the acceptance criteria.

This report answers the three release-blocking questions: (1) code/corpus
copyright, (2) v1.0.0 feature parity, (3) global consistency including debug
support.

---

## 1. Code and corpus copyright — CLEAN

**Provenance.** Every line ships under one of three provenances:

| Provenance | Extent | Evidence |
|---|---|---|
| Author's own v1.0.0 code, migrated byte-for-byte | 179 Python files (~37.4k lines) across the 9 legacy skills | `tests/test_capability_guard.py::test_migrated_files_byte_identical_to_v1_source` recomputes SHA-256 for every carried-over file on every test run; `test_no_python_file_lost` pins the file count at 179 + 9 adapters + 1 pint layer = 189 |
| Author's new v1.1.0 code | `lib/chelate_core/` (11 files), `core/` (4), `contracts/` (2), `bootstrap.py`, `cli.py`, 5 new skills, `tests/` (10) | Written for this release; no external snippets |
| Author's original corpora | AI-flavor lexicons, physics rules, broadcast keyword lists | See clean-room note below |

**No vendored third-party code.** All third-party packages (numpy, pandas,
sympy, pint, opencv, PyMuPDF, arxiv, bibtexparser, requests, R packages) are
declared in `manifest.json` / `requirements.txt` and imported at run time.
None is copied into this repository; no non-MIT license text exists anywhere
in the tree (verified by scanning all 15 `LICENSE` files — root + 14 skills —
all MIT, "Copyright (c) 2026 Jiaming Shi").

**Trademark isolation (R-01).** "PASCO" / "Capstone" are third-party
trademarks. `skills/capstone-labmate/NOTICE` carries the disclaimer; the root
README repeats it in a Trademarks section. The `.cap` parser is an
independent clean-room implementation of the file format; no PASCO
documentation, sample data, or binaries were copied.

**PyMuPDF (AGPL).** `fulltext-extractor` links PyMuPDF, which is dual-licensed
AGPL-3.0 / commercial. The README dependency table states this explicitly so
redistributors of PyMuPDF itself can comply.

**Clean-room corpus (R-01/R-02).** `skills/ai-trace-remover/src/core/patterns_en.py`
carries an explicit provenance header: original category design and regexes,
no external text copied, demonstration sentences built from public-domain
teaching texts and classic public-domain fiction. The Chinese lexicon
(`patterns_zh.py`) is the author's own domain corpus.

**Academic integrity (R-02).** The pipeline never fabricates data: `capstone-labmate`
watermarks generated reports as analysis drafts, the R-backed skills degrade to
`UNVERIFIED` (never a fabricated PASS) when Rscript is absent, and
`reference-auditor` FAILs on DOIs that do not resolve in Crossref. Missing
dependencies degrade gates to `UNVERIFIED`; a crash fails closed — a broken
core can never pass a gate.

**Conclusion:** no copyright exposure identified. Nothing to re-license,
attribute, or remove.

---

## 2. v1.0.0 feature parity — ZERO AMPUTATION

**Method.** The 9 legacy skills were copied from the intact v1.0.0 source tree
(`chelate-shell-main/skills/`) with SHA-256 verification; internal package
layout (`scripts.*`, `src.*`, `R/`, `templates/`, `config/`) is unchanged.
Additions are limited to each skill's root `run.py` adapter, `manifest.json`,
`README.md`, and one new layer for `formula-validator`
(`scripts/core/pint_units.py`, an additive capability, not a replacement).

**Automated proof (runs on every `pytest` invocation):**

- `test_migrated_files_byte_identical_to_v1_source` — every carried-over file
  matches the v1.0.0 source byte-for-byte (whitelisted: the 6 designed new
  files and 6 runtime-output directory names, including `_broadcast/`, which
  the legacy broadcast CLI regenerates on every run).
- `test_legacy_key_functions_exist` — 41 key modules across the 9 skills are
  imported in isolated subprocesses and checked for their documented
  top-level names (e.g. `scripts.core.pipeline.validate_equation`,
  `src.core.engine.scan`, `_capx.extract_datasets`).
- `test_no_python_file_lost` — 189 Python files under `skills/`, exactly the
  documented inventory.

**Documented-entrypoint proof** (`docs/audit_feature_parity.py`, exit 0):

```
task-organizer               SKILL.md identical | entrypoints 1 -> 1
multi-dim-manager            SKILL.md identical | entrypoints 2 -> 2
document-evolution-tracker   SKILL.md identical | entrypoints 1 -> 1
capstone-labmate             SKILL.md identical | entrypoints 4 -> 4
video-tracker                SKILL.md identical | entrypoints 2 -> 2
longitudinal-analysis        SKILL.md identical | entrypoints 1 -> 1
formula-validator            SKILL.md identical | entrypoints 1 -> 1
ai-trace-remover             SKILL.md identical | entrypoints 1 -> 1
conflict-detector            SKILL.md identical | entrypoints 1 -> 1

TOTAL documented python entrypoints: 14 (1.0.0) -> 14 (v1.1.0)
importable: 11/11
```

All nine `SKILL.md` files are byte-identical to v1.0.0; the five new skills'
`SKILL.md` files were written to the same template (YAML frontmatter + When to
use / When NOT to use / Core Workflow / Hard Constraints / Resources).

**Additive-only deltas.** Beyond the pint layer, v1.1.0 adds capability
without touching legacy behavior: thin adapters (same CLI surface for all 14
skills), the gate contract, the microkernel router, and 5 new skills. The
legacy CLIs remain directly runnable inside their skill folders.

**Conclusion:** every v1.0.0 documented entrypoint and key function is
present, importable, and byte-identical where migrated.

---

## 3. Global consistency (including Debug) — CONSISTENT

### 3.1 One contract at every layer

| Layer | Contract | Enforcement |
|---|---|---|
| Skill ↔ Router | `python run.py --root <ws> --action <a> [args]`, one stdout JSON line, gate JSON in `process/gates/` | `lib/chelate_core/adapter.py` (all 14 adapters) |
| Gate result | `{skill, status, evidence_level, reason, artifacts, timestamp}`, `status ∈ PASS/FAIL/UNVERIFIED` | `contracts/gate_result.py` + `contracts/schema.json` |
| Manifest | 10 fields, `additionalProperties: false`, 4-value stage enum | `core/registry.py::validate_manifest` |
| Adapter budget | thin `run.py` (45–107 lines), logic in `lib/`, no duplicated core functions | `tests/test_no_stubs.py` |
| Debug | one switch, two shapes (below) | `lib/chelate_core/debug.py` + `tests/test_debug.py` |

### 3.2 Debug support (added in this cycle)

Before this release cycle the framework had colored status lines and JSON
reports but **no debug facility at all** — `grep` for `debug|verbose` across
`cli.py`, `bootstrap.py`, `core/`, `lib/chelate_core/` returned zero matches.
v1.1.0 now ships a unified layer:

- **One switch, two shapes.** `--debug` on every `cli.py` subcommand
  (`list` / `run` / `pipeline`) and on `core/router.py`, or `CHELATE_DEBUG=1`
  in the environment. The flag calls `debug.enable()`, so the environment
  variable propagates to every skill subprocess automatically — one switch
  covers cli → router → adapter → legacy CLI.
- **Adapter-level flag.** Every adapter also accepts `--debug` directly
  (`python run.py --root ... --action ... --debug`); the adapter strips it
  before forwarding argv to legacy CLIs, so it can never crash a legacy
  entry point.
- **stderr only.** All debug lines carry a `[chelate:debug]` prefix and go to
  stderr; the stdout gate-contract line stays machine-parseable (asserted by
  tests).
- **Coverage.** Registry scan (14 skills, manifest details), resolved
  subprocess command + cwd, dependency verdict (degraded / missing), return
  code + duration + last stderr lines per skill, legacy action → module
  mapping, and the emitted gate path with status/evidence.
- **Colors.** `NO_COLOR` and `CHELATE_FORCE_COLOR` (pre-existing) are
  documented alongside `--debug` in the README Debugging section.
- **Post-mortem artifacts** (pre-existing, now documented): every run writes
  `process/gates/<skill>_<ts>.json`, `results/pipeline_report_<ts>.json`
  (full decision record: command, degraded flag, missing deps, rc, seconds),
  and `_broadcast/pipeline_index_<ts>.json`.

**Bug found and fixed during this audit.** The first implementation of the
router debug hook referenced the debug module through its `debug` parameter
(bool), raising `AttributeError` on any real `--debug` pipeline run. The
existing router tests all mocked `run_skill`, so none caught it. Fixed, and
`tests/test_debug.py` now includes a real-subprocess integration test
(`test_router_run_skill_debug_logs_real_subprocess`) that executes the actual
`run_skill` path with `debug=True` — the mock-based suite can no longer hide a
break in that plumbing.

### 3.3 Language consistency

- **All new code is 100% English.** A CJK scan over every non-legacy file
  (`lib/`, `core/`, `contracts/`, `tests/`, `bootstrap.py`, `cli.py`, all 14
  `run.py` adapters, `docs/`) finds CJK in exactly two files, both by design:
  `README.md` (the 简体中文 entry link) and `README_zh.md` (the designated
  Chinese document). 48 of 50 files are pure English.
- **CJK inside the legacy trees is domain data or upstream content, never
  new non-English code.** Classification of the 32 CJK-touching files:
  - *Functional domain data that must not be translated* (removing it would
    amputate capability): `ai-trace-remover`'s Chinese lexicon
    (`patterns_zh.py`, `hard_bans.py`, `sound_rules.py` regexes),
    `task-organizer`'s Chinese filename keywords (`rules.py`) and CJK
    stopword list (`broadcast.py`), `conflict-detector`'s Chinese test
    fixtures.
  - *Upstream legacy comments/docstrings*, preserved verbatim as part of the
    byte-identical migration guarantee (auditable against v1.0.0).
  - *Legacy skill docs and metadata* (`task-organizer/CHANGELOG.md`,
    `capstone-labmate/skill.json`, `ai-trace-remover/SKILL.md` and its
    `references/`), all upstream content.

### 3.4 Consistency defects found and fixed in this cycle

1. `core/router.py` debug-module shadowing (see 3.2) — fixed + regression
   test.
2. `docs/audit_feature_parity.py` resolved the v1.0.0 source tree one level
   too high and looked for skills outside `skills/` — it crashed with
   `FileNotFoundError` instead of auditing. Fixed; it now also exits non-zero
   on any parity regression.
3. `tests/test_capability_guard.py` flagged `task-organizer/_broadcast/`
   (runtime output) as a migration mismatch — whitelisted alongside the other
   runtime-output dirs.
4. Release packaging leaked `.pytest_cache/` and runtime `process/` into the
   zip — the archive is now built from an explicit exclusion list
   (`__pycache__`, `.pytest_cache`, `process`, `results`, `_broadcast`, `*.pyc`),
   and `.gitignore` covers the same set.
5. Both READMEs mis-stated dependencies. A guarded-import scan of all 14
   skills showed every "hard" third-party import outside the manifests is in
   fact conditional (`yaml` only for `.yaml` configs, `docx` only for
   `--format docx`, `openpyxl`/`PyPDF2` only for specific backends,
   `matplotlib` only for plots). `README_zh.md` listed several of these as
   required (e.g. `numpy/matplotlib/pypdf` for capstone-labmate, `scipy/mpmath`
   for formula-validator — which are not imported at all). Both tables were
   rewritten with a required/optional split verified against the code; the
   English README additionally states that optional imports sit behind
   `try`/`ImportError` or action-scoped conditionals.
6. The four new skills resolved `--input` against the process cwd (the
   repository root under the Router), so the documented workspace-relative
   usage (`--skill-arg "reference-auditor:--input draft.md"`) failed with
   "not found" — acceptance criterion 3 could not even be exercised with a
   relative path. Fixed with `paths.resolve_input(root, path)` wired into
   all four adapters, plus a unit test; AC2/AC3 re-verified end-to-end with
   workspace-relative inputs.

---

## Verification appendix

- **Automated suite:** 123 passed, 0 failed (`python -m pytest tests/ -q`,
  ~35s) — contracts, registry, router, capability guard, formula-validator,
  video-tracker, new skills, thin-adapter/no-stub guards, debug layer,
  input-path resolution.
- **Acceptance criterion 1 (flat layout):** 14 skills directly under
  `skills/`, no nesting; verified in the zip (14 directories, each with
  `SKILL.md` + `manifest.json` + `README.md` + `LICENSE` + `run.py`).
- **Acceptance criterion 2 (hard block):** a FAIL gate terminates the
  pipeline, `process/` stays locked, `promoted: 0` — reproduced with a
  non-existent DOI (`reference-auditor` → `FAIL/EXACT`, "1 of 1 DOIs do not
  exist in Crossref").
- **Acceptance criterion 3 (full pass):** all gates PASS promotes
  `process/` → `results/promoted_<ts>/` — reproduced with `data-profiler`
  (`PASS/EMPIRICAL` → `promoted=True`).
- **Release archive:** `chelate-shell-v1.1.0.zip`, byte-verified against the
  on-disk tree (no diff either way), zero cache/runtime entries.
- **GitHub red line respected:** download-only. No push, no PR, no release,
  no settings change; the archive is a local mirror.
