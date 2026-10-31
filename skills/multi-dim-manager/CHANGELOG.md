# Changelog

All notable changes to this skill are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-10-25

### Changed
- Version declaration unified to 1.2.0 across the repository: `__version__`
  in `scripts/__init__.py` now matches `manifest.json` and the `SKILL.md`
  frontmatter (previously 1.0.1). No capability change.

## [1.0.1] - 2026-10-16

Documentation and installation overhaul; no functional change to the
manager itself (the shipped feature set is the same as 1.0.0).

### Changed

- **README rewritten (EN + ZH).** The per-skill English and Chinese
  READMEs were fully reworked to the repository's standard template:
  bilingual nav line, a compact design-principles / core-features block,
  a unified "Download and install" section, and a per-skill security
  disclosure example in the "Report issues" block.
- **Installation streamlined to four standard methods.** The install
  section now documents exactly four routes in one consistent style:
  the cross-platform installer binary, the source archive, Agent
  self-fetch, and `git clone`.

## [1.0.0] - 2026-10-14

First release of multi-dim-manager: a state manager for multi-dimensional
computational experiments.

### Added

- Parameter-space definition from JSON/YAML with Cartesian expansion.
- Per-round, content-addressed snapshots of user-declared critical paths
  (no full working-directory copy).
- Append-only JSONL audit log: parameters, input/output hashes, timestamps,
  plugin exit codes, and pre/post snapshots per round.
- Non-destructive rollback to any recorded round (new directory by default;
  `--force` to overwrite the live working directory). Automatic rollback to the
  last good baseline after a failed round, itself audited.
- Result aggregation to CSV / Markdown plus a report draft.
- Unified plugin contract: one shell command, JSON in/out, exit codes 0/1/2.
- CLI (`scripts/run.py`) with `run`, `dryrun`, `rollback`, `summary`, `verify`.
- Documentation: `SKILL.md` (MANDATORY WORKFLOW), bilingual `README.md` /
  `README_zh.md`, `config.example.yaml`, `sample_plugin.py`.

### Hardening

- Deterministic orchestration: same parameters always yield the same plan and the
  same recorded hashes.
- Pure standard library by default; PyYAML is an optional dependency used only
  for YAML configs.

### Not claimed

- Golden-output verification (comparison against a known expected output) is
  deferred to v0.2; the current verifier only checks the plugin contract.
- The manager cannot enforce plugin-level determinism (network, random seeds,
  wall-clock); this is the user's responsibility and is documented as a
  limitation.
