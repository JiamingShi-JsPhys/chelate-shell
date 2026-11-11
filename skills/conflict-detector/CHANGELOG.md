# Changelog

All notable changes to this skill are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [1.3.1] - 2026-11-11

### Changed
- Version declaration bumped to 1.3.1 across the repository.
  The version contract test now compares against this skill's
  `manifest.json` instead of a hardcoded `"1.2.0"`, so a release
  bump cannot break it.

## [1.3.0] - 2026-10-28

### Added
- Version declaration unified to 1.3.0 across the repository (manifest,
  SKILL.md frontmatter, `__init__.py`, CITATION.cff, config/examples,
  package.json, plugin manifests, lib version strings). No capability
  change to this skill.
## [1.2.0] - 2026-10-25

### Changed
- Version declaration unified to 1.2.0 across the repository: the CHANGELOG
  now documents the current release alongside `manifest.json`, the `SKILL.md`
  frontmatter, and `src/__init__.py`. No capability change.

## [1.0.0] - 2026-10-15

First public release of conflict-detector: a cross-document
contradiction detector.

### Added

- Three detection levels: `entity` (numeric / boolean mismatch on the same
  key), `clause` (categorical mismatch), and `argument` (free-text
  line-level disagreement).
- Document sources via path, inline text, or inline JSON (YAML config).
- Deterministic claim normalisation: key canonicalisation (case /
  punctuation / alias-aware) and table-driven unit rescaling.
- Cross-document rule engine that pairs claims by canonical key across
  distinct sources and flags mismatches with a structured detail payload
  (delta / interval overlap / vocabulary flags).
- Reporter that renders the conflict list to JSON, CSV, and Markdown.
- CLI (`src/cli.py`): `run [--format]`, `validate`, `list-docs`.

### Not claimed

- Extraction is key-value oriented; free-text paragraphs only participate
  at the `argument` level (line-level comparison).
- This skill does not perform semantic NLP; contradictions are detected
  by key/value equality, interval overlap, and controlled-vocabulary
  membership.
