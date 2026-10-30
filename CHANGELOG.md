# Changelog

All notable changes to Chelate Shell are documented in this file.

## [1.1.3] — 2026-10-29

Maintenance release on top of the v1.1.2 tree. No skill gained or lost
capability; every change below is a fix for something that shipped wrong.

### Fixed
- **Version declarations now all read 1.1.3.** v1.1.2 shipped with `1.1.1`
  in every declaration surface (`package.json`, the four `plugin.json`
  files, two `marketplace.json` files, all 14 `manifest.json` files and
  all 14 `SKILL.md` frontmatter blocks) while its release tag and both
  README banners said `1.1.2`. All surfaces are bumped together, and
  `tests/test_plugin_manifests.py` enforces that every one of them agrees
  with the skill manifests.
- **`CHANGELOG.md` had no `1.1.2` entry.** The v1.1.2 work was released
  without a changelog section, so the file jumped from 1.1.1 straight to
  1.1.0. The missing 1.1.2 entry is restored here, and its *Quick Execution*
  claim is corrected: the block was promised for "all 14 skills" but never
  written into the tree. Five adapter skills gain it in this release; the
  nine legacy trees keep their `SKILL.md` bodies byte-frozen by the
  zero-amputation rule.
- **`capstone-labmate/pyproject.toml` carried the wrong contact mailbox.**
  The stale `jiamingshi_physics@outlook.com` spelling survived the migration
  while the other nine `AUTHORS.md` files and both READMEs use
  `jiamingshi_git@outlook.com`. Unified.
- **`tests/test_router.py::test_red_fail_output` fails whenever `NO_COLOR`
  is set in the environment.** The test forces `CHELATE_FORCE_COLOR=1` but
  `_color()` checks `NO_COLOR` first, so the assertion on the red escape
  code fails on any machine whose shell exports `NO_COLOR` (the Windows
  dev box used to cut this release does). The test now clears `NO_COLOR`
  through `monkeypatch` so the ambient environment cannot mask a real
  regression.
- **README test counts were stale.** Both READMEs advertised 156 tests while
  the suite collects 191 (190 passed, 1 skipped on a machine without the
  v1.0.0 source tree, which the migration guard skips by design).
- **`ORCHESTRATOR.md` still declared `v1.1.0`** in its header and in the
  manifest-sync note two releases later. The version assertion in
  `test_plugin_manifests.py` was hard-coded to `v1.1.0`, so it could not
  catch the drift; it now compares against the shipped skill version.

## [1.1.2] — 2026-10-24

### Security / Licensing
- Completed the PyMuPDF removal started in 1.1.1: no `import fitz` /
  `import pymupdf` remains in production code, and `fulltext-extractor`
  declares `pypdf` as the core dependency for cross-version compatibility.

### Fixed
- `GateResult.from_dict` coerces corrupt `status` / `evidence_level` values
  to `UNVERIFIED` instead of raising, so a malformed gate file can no longer
  be misreported as a hard `FAIL` by the router.
- The router's `--help` probe prints an explicit `[INPUT] warning` when a
  skill's environment probe fails instead of silently dropping the skill from
  `--inputs` auto-wiring.
- `fulltext-extractor` PDF parsing no longer degrades to character-by-character
  output on Python 3.13 (incomplete font descriptors); covered by the
  pdfminer/pypdf dual-backend path.

### Known issue carried into 1.1.3
- The release announced a *Quick Execution* block for "all 14 skills", but
  the block was never written into the tree. 1.1.3 adds it to the five
  adapter skills that can honour it; the nine legacy skills keep their
  `SKILL.md` bodies byte-frozen by the zero-amputation migration rule.
- The version bump for this release stopped at the README banner: every
  machine-read manifest still declared `1.1.1`. Corrected in 1.1.3.

## [1.1.1] — 2026-10-24

### Security
- Removed the PyMuPDF (AGPL-3.0) dependency from `fulltext-extractor`.
  The extractor now uses **pdfminer.six** (MIT) as the primary backend,
  with **pypdf** (BSD-3-Clause) as a transparent fallback when pdfminer is
  not installed. Both are permissive-licence libraries; the skill no longer
  links any AGPL component.

### Fixed
- Workspace path contract: all 14 adapters now honour a mandatory `--root`
  and write every artifact (gates, reports, ingest output) into
  `<workspace>/process/` instead of the skill install / plugin-cache dir.
  Legacy CLIs run with cwd pinned to the workspace; explicit user flags
  still win over injected defaults.
- `formula-validator` `REPORT_DIR` and `video-tracker` / `capstone-labmate` /
  `multi-dim-manager` output dirs are anchored to the workspace.
- `GateResult.from_dict` no longer raises on a corrupt gate file; malformed
  `status` / `evidence_level` degrade to `UNVERIFIED` instead of a `ValueError`
  (the router now reports a corrupt gate as UNVERIFIED, not FAIL).
- Router `--help` probe: a skill whose adapter fails to start is now reported
  as an `[INPUT]` warning instead of being silently skipped from auto-wiring.

### Changed
- Bumped every `manifest.json`, per-platform `plugin.json`, `package.json`,
  and SKILL.md frontmatter to 1.1.1 (single source of truth kept in lockstep).
## [1.1.0] — 2026-10-23

### Added — microkernel architecture
- `core/router.py`: manifest-driven dispatcher. Scans the 14 skill manifests
  into an in-memory routing table, matches inputs to `stage="ingest"` skills,
  then serially dispatches `stage="gates"` skills. The first gate returning
  `FAIL` terminates the pipeline immediately (red terminal output);
  intermediate products stay locked in `process/` and are never promoted.
  Full pass promotes `process/` to `results/promoted_<ts>/`.
- `core/registry.py`: flat scan of `skills/*/manifest.json` (nested manifests
  are rejected), pure-stdlib manifest validation, routing table
  (`by_stage` / `by_input` / `get` / `names`).
- `core/sandbox.py`: per-skill dependency resolution; missing dependencies
  degrade a skill to an `UNVERIFIED` gate instead of crashing.
- `contracts/gate_result.py`: unified gate contract
  `{skill, status, evidence_level, reason, artifacts, timestamp}`.
- `contracts/schema.json`: manifest schema (ten fields incl. `output_types`
  and `sandbox_required`, `additionalProperties: false`, `stage` enum of
  four values).
- `bootstrap.py`: workspace bootstrap helpers (`write_gate` / `read_gate` /
  `gates_dir` / `repo_root` / `legacy_cwd` / `probe_deps`).
- `cli.py`: `list`, `run <skill>`, and `pipeline` commands with
  `--mode a|b|c`, `--input-kind`, `--inputs`, `--selected`, `--skill-arg`,
  `--dry-run`, `--debug`.
- Adapter contract: every skill now exposes a root-level `run.py` with the
  unified CLI `--root <workspace> --action <...> [legacy args]`, writing a
  standard gate result to `process/gates/<skill>_<ts>.json`. Legacy CLIs
  remain directly runnable.
- `pipeline --inputs FILE [FILE ...]`: declares the run's input files
  (workspace-relative or absolute). Each file is resolved against `--root`
  (missing files fail fast with exit code 2 before any skill runs), narrows
  the plan to the skills whose manifest `input_types` declare its type (an
  explicit `--selected` list always wins), and is forwarded as `--input` to
  the matching adapters that define it (probed via `--help`; explicit
  `--skill-arg` flags are appended after, so they win under argparse's
  last-value rule). A file whose extension declares no manifest type is
  reported as an `[INPUT]` warning and wires to nothing.
- 156 automated tests under `tests/` (contracts, registry, router, cli,
  capability guard, formula-validator, video-tracker, new skills,
  thin-adapter and no-stub guards, unified debug layer, input-path
  resolution, `--inputs` auto-wiring, plugin-manifest contract,
  SKILL.md frontmatter/manifest agreement).
- Unified debug layer: `lib/chelate_core/debug.py` exposes one switch with two
  shapes — `--debug` on every `cli.py` subcommand and `core/router.py`, or the
  `CHELATE_DEBUG=1` environment variable (inherited by skill subprocesses, so
  it reaches every adapter and legacy CLI). Debug lines go to stderr with a
  `[chelate:debug]` prefix; the stdout gate-contract line stays clean.
  Coverage: registry scan, resolved command and cwd, dependency verdict,
  return code / duration / stderr tail per skill, legacy action → module
  mapping, and the emitted gate path with its status.
- Plugin manifests for four host platforms, repaired against the v1.0.0
  rejection: `.claude-plugin/`, `.codebuddy-plugin/`, `.codex-plugin/` each
  ship `plugin.json` (+ `marketplace.json`), and `.dsh-plugin/` ships the CJS
  entry (`index.js` exporting `name` + `apply(ctx)`). Two contract
  violations were fixed: `author` is now an object (`{"name": ...}`) instead
  of a bare string, and the invalid string `skills` field is omitted so the
  host auto-scans the flat `skills/` directory; the `icon` field was removed
  from `plugin.json` (the shared `assets/icon.png` stays in the repo). Root
  `package.json`, `index.js` and `cordis.patch.yml` complete the dsh
  packaging, and `ORCHESTRATOR.md` documents the v1.1.0 routing contract
  (14 skills, 4 stages). `tests/test_plugin_manifests.py` locks the shape:
  version sync across all manifests, author-object, no string `skills`, no
  `icon`, marketplace entries, and the CJS entry surface.

### Added — `lib/chelate_core/` (programs live outside the skills)
- `adapter.py`: thin-adapter toolkit — common argparse, gate emission,
  controlled degradation (`Degraded` / `Failed`), and a declarative runner
  for the migrated legacy CLIs (`run_legacy`).
- `paths.py` / `yamlmini.py`: repository/skill/workspace path resolution and
  `assets/config.yaml` loading (PyMuPDF-free flat YAML subset fallback, so
  configuration never requires PyYAML).
- Core algorithm modules shared by the skills: `pdf_text.py`,
  `arxiv_search.py`, `bibtex_norm.py`, `doi_audit.py`, `csv_profile.py`,
  `formula_merge.py`.
- Every skill folder now carries the standard surface: `SKILL.md`,
  `manifest.json`, `README.md`, `LICENSE`, thin `run.py`, `assets/`.
- The five new skills' `SKILL.md` files follow the original nine's template
  (YAML frontmatter + When to use / When NOT to use / Core Workflow / Hard
  Constraints / Resources).

### Added — five new skills
- `fulltext-extractor` (ingest): PyMuPDF text extraction with page selection
  and a JSON metadata sidecar; scanned/image PDFs degrade to `UNVERIFIED`.
- `literature-retriever` (ingest): arXiv keyword search to JSON
  (title, abstract, authors, links) in `process/literature/`.
- `bibtex-normalizer` (ingest): `bibtexparser`-based parsing with
  citation-key and title+year dedupe, normalized output plus a dedupe report.
- `reference-auditor` (gates): DOI extraction from drafts and Crossref REST
  verification; any non-existent DOI fails the gate and terminates the
  pipeline.
- `data-profiler` (gates): pandas CSV profiling — row/column counts,
  per-column missing statistics, 1.5·IQR outlier ratios (configurable fence),
  duplicate rows, constant columns.

### Changed
- `formula-validator`: merged a `pint` physical-unit cross-check layer
  (`scripts/core/pint_units.py`) alongside the existing SymPy D1–D5 layers.
  New `units` action exposes the pint layer standalone.
- All nine legacy skills re-versioned to 1.1.0 with new `manifest.json`
  metadata (`output_types`, `sandbox_required` added); internal module
  layout unchanged. Their `run.py` adapters are now declarative tables over
  `lib/chelate_core/adapter.py` instead of inline wiring.
- Root `LICENSE` added (MIT); `README_zh.md` (Chinese entry) and `.gitignore`
  carried over from v1.0.0; `capstone-labmate/NOTICE` carries the PASCO
  trademark disclaimer.

### Migration integrity
- The nine v1.0.0 skills were migrated byte-for-byte (179 Python files,
  ~37,400 lines, SHA-256 verified). `tests/test_capability_guard.py`
  re-verifies file parity with the v1.0.0 source tree and the presence of
  every key module function on every test run, guarding against future
  amputation.

### Fixed
- The nine legacy `SKILL.md` frontmatters shipped stale contract fields:
  versions like `1.0.0-beta` / `0.0.0-beta` (contradicting the manifests'
  `1.1.0`), `entry_point` values pointing at CLIs the Router never calls
  (`python -m src.cli`, `python -m scripts.tracker` — capstone-labmate
  declared `src.cli` although it has no `src/` package at all), and
  `python_requires: '>=3.9'` against the repo-wide 3.10+ floor. All three
  fields now agree with the manifests and README; the byte-identity guard
  masks exactly those frontmatter lines so the SKILL.md *bodies* stay
  provably untouched, and `tests/test_plugin_manifests.py` fails on any
  future drift.
- `docs/audit_feature_parity.py`: the entrypoint audit compared raw command
  strings including the frontmatter, so re-pointing `entry_point` at the
  thin adapter read as three "missing entrypoints". It now extracts only
  body-documented commands and normalizes `python -m a.b` to `python a/b.py`
  before diffing; the frontmatter contract is covered by the guard test
  above.
- Legacy usage errors no longer hard-block the pipeline: when a migrated
  legacy CLI exits non-zero with an argparse usage error on stderr (e.g.
  `conflict-detector` invoked without its required `--config`), the adapter
  emits `UNVERIFIED` ("legacy CLI invocation incomplete") instead of `FAIL`.
  An incomplete invocation means the check never examined the data — it is
  "not verified", not a data rejection. The legacy stderr is still echoed
  for direct runs.
- `tests/test_capability_guard.py`: the byte-identity walk now also skips
  `test_workspace/` (user scratch workspace with runtime gate artifacts),
  and `.gitignore` / the release archive exclude it as well.
- `fulltext-extractor`: `extract()` now creates its output directory when
  called programmatically (previously only the CLI path did).
- `pdf_text.parse_pages`: a non-empty but unparsable page spec (e.g. "abc")
  now falls back to all pages instead of extracting nothing.
- Workspace-relative `--input` paths: the four new skills resolved `--input`
  against the process cwd (the repository root under the Router), so the
  documented workspace-relative usage (`--input draft.md` next to
  `--root <workspace>`) failed with "not found". `lib/chelate_core/paths.py`
  gained `resolve_input(root, path)` — absolute and cwd-existing paths pass
  through, relative paths resolve against `--root`; wired into
  data-profiler, reference-auditor, fulltext-extractor and bibtex-normalizer.
- Docstrings quoting the original Chinese build instructions were
  translated to English, keeping the shipped tree English-clean.
- `core/router.py`: `run_skill` referenced the debug module through its
  `debug` parameter (shadowing), raising `AttributeError` whenever
  `--debug` was active on a real pipeline run. The mock-based router tests
  never executed the real `run_skill`, so `tests/test_debug.py` now includes
  a real-subprocess integration test for the router's debug plumbing.
- `tests/test_capability_guard.py`: `task-organizer/_broadcast/` (a runtime
  output directory the legacy broadcast CLI writes on every run) is now
  whitelisted like the other runtime dirs.
- `docs/audit_feature_parity.py`: fixed path resolution (the v1.0.0 source
  tree and the `skills/` directory were mis-resolved) and translated the
  module docstring to English; the audit now exits non-zero on any missing
  documented entrypoint or unimportable legacy module.
