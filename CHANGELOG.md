# Changelog

All notable changes to Chelate Shell are documented in this file.

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
- 141 automated tests under `tests/` (contracts, registry, router, cli,
  capability guard, formula-validator, video-tracker, new skills,
  thin-adapter and no-stub guards, unified debug layer, input-path
  resolution, `--inputs` auto-wiring).
- Unified debug layer: `lib/chelate_core/debug.py` exposes one switch with two
  shapes — `--debug` on every `cli.py` subcommand and `core/router.py`, or the
  `CHELATE_DEBUG=1` environment variable (inherited by skill subprocesses, so
  it reaches every adapter and legacy CLI). Debug lines go to stderr with a
  `[chelate:debug]` prefix; the stdout gate-contract line stays clean.
  Coverage: registry scan, resolved command and cwd, dependency verdict,
  return code / duration / stderr tail per skill, legacy action → module
  mapping, and the emitted gate path with its status.

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
