# Changelog

All notable changes to Chelate Shell are documented in this file.

## [1.2.0] — 2026-10-24

### Changed
- **Version unified to 1.2.0 everywhere.** Every project version declaration
  now reads `1.2.0`: all 18 skill `manifest.json` files, all 18 `SKILL.md`
  frontmatter blocks, all four `.claude-plugin/` / `.codebuddy-plugin/` /
  `.codex-plugin/` / `.dsh-plugin/` manifests, root `package.json`, and the
  per-skill packaging files that previously still carried `1.0.0` /
  `1.0.0-beta` (`pyproject.toml`, `capstone-labmate/skill.json`,
  `config/schema.yaml`, `config/examples/family.json`). XML declarations
  (`<?xml version="1.0"?>`) and test-internal fixtures are data, not product
  versions, and were deliberately left alone.
- **Audit follow-up (2026-10-25): version unification completed.** A re-audit
  found surfaces the first pass had not walked: `__version__` in four skill
  `scripts/__init__.py` files (still `1.0.1` / `0.0.0`), five `CITATION.cff`
  `version:` fields (`1.0.0`), two `config/examples/` schema versions
  (`1.0.0`), a stale manifest example in `docs/CONSTRUCTION_PLAN.md`
  (`1.1.0`), and two live version strings in `lib/chelate_core/` (the Crossref
  user agent `chelate-shell/1.1.0` and the `.bib` output header `v1.1.0`). All
  now read `1.2.0`; the seven legacy skills that ship a CHANGELOG each gained
  a `## [1.2.0]` section, and `tests/test_repo_consistency.py` now walks every
  declaration surface (manifests, SKILL.md frontmatter, `__init__.py`,
  CITATION.cff, example configs, dot-plugin manifests, lib strings) so this
  class of drift cannot return.
- **Audit follow-up (2026-10-25, second pass): marketplace manifests.**
  `.claude-plugin/marketplace.json` was the only plugin-manifest surface still
  declaring no version at all. The Claude Code marketplace schema defines a
  `version` field on plugin entries, and the codebuddy / codex manifests have
  carried `1.2.0` since the v1.1.x migration, but both manifest tests only
  checked the field "when present", so the gap never surfaced. The entry now
  reads `1.2.0`, and `test_plugin_manifests.py` / `test_repo_consistency.py`
  require the field instead of tolerating its absence. The same pass removed a
  dangling sentence fragment ("whole pipeline down.") that an earlier edit had
  left in `README.md`.
- **Audit follow-up (2026-10-25, third pass): contact mailbox.** The repo
  carried two spellings of the maintainer address:
  `jiamingshi_git@outlook.com` in both READMEs and nine `AUTHORS.md` files,
  and `jiamingshi_physics@outlook.com` in `capstone-labmate/pyproject.toml`
  (the stale spelling had been there since the v1.0.0 source and was
  faithfully migrated, so the capability guard saw matching bytes on both
  sides). All twelve contact surfaces now read `jiamingshi_git@outlook.com`.
  The capability guard's metadata mask learned a contact-declaration rule (an
  `email` key in a packaging file is metadata, not capability), and
  `test_repo_consistency.py::test_contact_email_is_unified` walks every
  tracked text file so a third spelling cannot return; RFC 2606 placeholder
  addresses and the third-party license inventory stay exempt. The three
  new guard tests also grew the suite from 289 to 292 collected tests, so
  both READMEs' test counts were refreshed to match.
- **Audit follow-up (2026-10-25, fourth pass): all 18 skills proven
  runnable.** Every declared entrypoint answers `--help`; the nine
  skills that ship internal suites were run in place (capstone-labmate
  57, conflict-detector 33, document-evolution-tracker 30,
  longitudinal-analysis 33 green; formula-validator 237 and
  multi-dim-manager / task-organizer / video-tracker functionally green
  with doc-convention failures only — the same class of legacy debt that
  existed in v1.1.2, now one-to-two failures lighter per skill); real
  adapter-level smoke runs (ai-trace-remover scan, task-organizer
  init/doctor, conflict-detector run, capstone-labmate ingest on the
  blank fixture) and a full `cli.py pipeline` run all completed, and the
  capability guard's runtime-output exclusion learned `process/` — the
  formula-validator internal suite writes reports into its own tree
  when run outside the adapter, and `.gitignore` has always declared
  `process/` a runtime artifact.
- **"Pro" branding removed.** The distribution is plain `chelate-shell`
  v1.2.0: no `chelate-shell-pro` identity string, no "Pro" qualifier on the
  release or on the four heavy skills, and no "Pro fork" framing. Technical
  terms that merely contain the letters (Probe, Profile, Process, Programs,
  Promotion, Produce, Protected, Project, Product, Prose, Prompt,
  additionalProperties, and the PASCO `DSProExperiment` XML element) are
  untouched.
- Corrected two stale claims while de-branding: `README.md` asserted that all
  four heavy skills set `sandbox_required: true` (the stdlib-only
  `latex-exporter` does not), and `README.md` carried a stray sentence
  fragment left by an earlier edit.

### Migration guard
- `tests/test_capability_guard.py` now tolerates exactly one kind of change
  in legacy-skill packaging files: the version-declaration line. The new
  `_mask_version_decl` helper blanks only that line, so `versions_dir` /
  `version_naming` keys and dependency pins such as `openpyxl>=3.1.0` stay
  under byte-for-byte comparison. This follows the guard's existing
  precedent for `CHANGELOG.md`, `src/__init__.py` and skill-local tests, and
  is mutation-tested: tampering with any non-version line still fails.

### Added
- **Release identity**: the project ships as `chelate-shell` v1.2.0 (all
  plugin.json, package.json, marketplace.json; version 1.2.0).
- `core/sandbox.py` — true process-level sandbox isolation via `multiprocessing`
  with a 120-second timeout circuit-breaker. A skill that exceeds the limit is
  force-terminated and reported as `UNVERIFIED` with a timeout reason.
  Windows `spawn` mode is handled with an `if __name__ == "__main__"` guard.
- 4 new heavy-gate/processor skills, all shipping a full business
  engine under `scripts/` (`scripts/engine.py` + `scripts/run.py`) and
  wired into the routing table:
  - `quantitative-validator` (gates, `rdkit`, sandbox_required=true) —
    atom conservation for formulae and chemical equations
  - `ml-auditor` (gates, `scikit-learn` + `pandas`; `cleanlab` optional,
    sandbox_required=true) — data-leakage and label-error detection
  - `figure-generator` (processors, `matplotlib` + `seaborn`,
    sandbox_required=true)
  - `latex-exporter` (processors, **standard library only** — no `pandoc`,
    sandbox_required=false) — Markdown + figures merged into one `.tex`
- `tests/test_quantitative.py`, `tests/test_ml_auditor.py`,
  `tests/test_latex_exporter.py` — real-logic and `UNVERIFIED`-degradation
  coverage for the three skills that shipped as skeletons earlier in the
  v1.2.0 cycle and have since graduated.
- `tests/test_repo_consistency.py` — repo-wide guard that every skill's
  `SKILL.md` frontmatter, `manifest.json`, entrypoint, `LICENSE` and
  declared dependencies stay in agreement. Mutation-tested against the
  `pandoc` / `cleanlab` doc drift it was written to catch.
- `tests/test_sandbox.py` — regression tests for the 120s circuit-breaker
  and the normal-return path.

### Documentation
- Back-ported the **Quick Execution** block (the one-line call template the
  v1.1.2 entry promised for "all 14 skills") to the five adapter skills that
  were still missing it: `fulltext-extractor`, `literature-retriever`,
  `bibtex-normalizer`, `reference-auditor`, `data-profiler`. The nine legacy
  trees keep their original `SKILL.md` bodies byte-frozen by the
  zero-amputation red line, so the block is deliberately **not** back-ported
  there; `tests/test_repo_consistency.py` encodes that exemption.
- Corrected stale statements across `README.md`, `README_zh.md`,
  `ORCHESTRATOR.md`: `latex-exporter` no longer claims `pandoc` (it is
  standard-library only and unsandboxed), `ml-auditor` no longer claims
  `cleanlab` as a hard dependency, and `quantitative-validator` is described
  as the atom-conservation gate it actually is.
- Documented the two skill layouts as an explicit convention —
  **adapter skills** (`run.py` at the skill root, thin wiring over
  `lib/chelate_core/`) vs **engine skills** (`scripts/run.py` +
  `scripts/engine.py`, owning their own algorithm) — instead of leaving the
  split undocumented.

- **`README.md` and `README_zh.md` are now true translations of each other.**
  The two files had drifted into different documents: the English one carried
  the architecture tree, the two skill layouts, the gate and manifest
  contracts, the per-skill inventory and the test inventory, while the Chinese
  one carried installation, known limitations, issue reporting and routing
  rules. Both files now share one section-for-section structure (37 matching
  headings), each section present in both languages; the Chinese dependency
  matrix was re-ordered to the English one's stage order, and the tree root
  label was corrected to `chelate-shell/` in both.
- **Fixed the `new` skill labels.** The label had frozen at the v1.1.x roster:
  `fulltext-extractor`, `literature-retriever`, `bibtex-normalizer`,
  `reference-auditor` and `data-profiler` were still badged *(new)* a release
  later, while the four skills that actually are new in v1.2.0
  (`quantitative-validator`, `ml-auditor`, `figure-generator`,
  `latex-exporter`) were badged *(v1.2.0)* instead. *(new)* now marks exactly
  the current release's additions in both the skill inventory and the
  directory tree, and the label convention is stated explicitly in both
  READMEs. The stale test count (278) was also corrected to 289 in both files.

### Removed
- `amos-auditor` — the AMOS-output parser was dropped; `.amw` / AMOS-report
  inputs are no longer gated by the suite.
- Structural-equation-modelling **auditing** is out of scope for this release:
  the `sem-auditor` skill (and its `semopy` dependency) is not part of the
  18-skill roster. `figure-generator` still ships the `sem_path` path-diagram
  renderer as a pure matplotlib drawing routine, so SEM diagrams can be drawn
  from an externally supplied spec without any SEM estimation library.

## [1.1.2] — 2026-10-24

### UX
- Added a **Quick Execution** block to every `SKILL.md` (all 14 skills). The
  block gives the invoking AI a precise one-line call template so it does not
  waste tokens reading the source tree. The block also instructs the AI to
  interpret stdout directly without re-reading generated report files, and to
  honour the `--root` workspace-writes contract.

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
