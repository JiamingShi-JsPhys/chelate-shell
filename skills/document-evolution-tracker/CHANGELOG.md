# Changelog

All notable changes to this skill are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [1.3.3] - 2026-11-14

### Changed
- Version declaration bumped to 1.3.3 across the repository.
  No capability change to this skill.

## [1.3.2] - 2026-11-13

### Changed
- Version declaration bumped to 1.3.2 across the repository.
  No capability change to this skill.

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

First public release of document-evolution-tracker: a document
version-alignment and concept-lineage tracker.

### Added

- Version discovery over a directory family with two naming schemes:
  `sequential` (v1, v2, ...) and `timestamp` (ISO-ish stamps, mtime
  fallback).
- Structural block diffing at three granularities: `line`, `paragraph`
  (default), and `sentence`, using `difflib` (no external dependency).
- Concept lineage: tracks named phrases (or auto-detected Markdown
  headings) across versions and classifies each transition as
  introduced / retained / modified / dropped.
- Timeline report in Markdown (human-readable transition tables +
  concept-lineage matrix) and JSON (machine-readable).
- CLI (`src/cli.py`): `run [--concepts]`, `versions`, `validate`.

### Not claimed

- Diffing is structural (block alignment), not semantic; a concept is
  "present" only when its exact phrase (case-insensitive) appears in the
  version text.
- Naming schemes beyond `sequential` / `timestamp` are not supported.
