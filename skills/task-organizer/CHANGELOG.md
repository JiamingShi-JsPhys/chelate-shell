# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-10-25

### Changed
- Version declaration unified to 1.2.0 across the repository: `__version__`
  in `scripts/__init__.py` now matches `manifest.json` and the `SKILL.md`
  frontmatter (previously 1.0.1). No capability change.

## [1.0.1] - 2026-10-16

Documentation and installation overhaul; no functional change to the
engine itself (the shipped feature set is the same as 1.0.0).

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

## [1.0.0] - 2026-10-13

The first release of the skill. It ships the complete, proven feature set:
the three-tier task-folder organizer with forced before/after verification,
the provenance model, and the **broadcast center** - a read-only
context-compression index that lets later AI sessions read a digest first and
open only the original documents they actually need.

### Added

- **Three-tier organizer with forced verification.** `organize` builds the
  `material` / `process` / `results` structure, takes before/after
  SHA-256 snapshots and enforces 7 consistency checks (C1-C7); any error
  triggers an automatic rollback to the before-state, so the folder is never
  left half-organized.

- **Provenance manifest** (`process/sources.json`). Placement is decided by
  *who produced the file*, never by its name: `user` material is lifted
  verbatim into `material/initial/` (never renamed, never modified, never
  deleted), assistant downloads go to `material/downloaded/`. The manifest
  stores names only - no hashes, no content reads. `mark-downloaded` /
  `mark-user` declare provenance explicitly.

- **Provenance re-filing.** `organize` moves files whose registered
  provenance contradicts their current location: user material stranded in
  `process/` (dumped there by a blind first run) goes to
  `material/initial/`, registered downloads go to `material/downloaded/`.
  Declaring with `mark-user` / `mark-downloaded` and re-running therefore
  just works - no `undo`/`redo` dance. Undeclared files are never touched
  (idempotent re-runs), and tool artifacts stay protected by the exact-path
  whitelist.

- **Broadcast center (`_broadcast/`) - the context-compression index.**
  `broadcast <root>` scans every supported document (`txt` / `md` / `csv`
  / `json` / `docx` / `pdf` / `pptx` / `xlsx` / `srt` / `vtt`), extracts
  text with the standard library (`openpyxl` / `pdfminer` / `PyPDF2` are
  optional upgrades, never requirements), and writes two lightweight files:
  `_broadcast/INDEX.md` - one line per file with path, type, size, date,
  a one-sentence summary and keywords - and `_broadcast/index.json`, the
  machine-readable twin. `INDEX.md` opens with a **categorized Directory**:
  every file is filed under its most salient keyword (the topics most
  common across the corpus become the biggest headings), so a reader scans
  the directory and opens only the originals they need without reading
  every line - the whole point when a folder holds thousands of files.
  Summaries are AI-generated when `TASK_ORG_AI=1` plus a key is configured
  (or `--ai` is passed); otherwise the local mode keeps the first 200
  characters and derives keywords statistically (English word frequency,
  Chinese character-bigram frequency). Subtitle files (`.srt` / `.vtt`)
  have their timing axis and index numbers stripped before summarization,
  so the digest summarizes the dialogue instead of a wall of metadata. The
  command is read-only with respect to the originals, idempotent, and
  bounded (per-file extraction cap, `--max-files`, soft size warning).
  `_broadcast` is a tool-owned prefix, so `init` / `organize` never
  relocate it. Works standalone on any folder, task folder or not.

- **Folder-signal trigger with propose-first semantics.** Referencing or
  attaching a folder and starting a task on it is a trigger class of its
  own: the mandatory workflow opens with a folder-signal check that PROPOSES
  one `init` ("I see you are working in `<folder>`; want me to set up the
  standard three-tier structure before we start?") and then stops - no
  command runs until the user confirms, because `init` moves existing
  content into `material/initial/` and reorganizing a referenced folder
  uninvited is a layout change the user must agree to first. An explicit
  organize / workspace request, or the compound content-production request,
  runs directly with no proposal. The proposal fires at most once per
  folder; a declined proposal is never repeated.

- **Content-production scenarios are first-class.** The frontmatter
  description claims the compound intent ("finishes producing an artifact -
  article / review / report / write-up - and wants the task folder kept in
  the standard three-tier layout"), and `SKILL.md` defines the action chain:
  `init` first (so the user's inputs are registered), produce, declare
  provenance, name the deliverable, `organize`.

- **Chinese deliverable keywords** in the built-in fallback table:
  `定稿` / `最终版` / `综述` / `报告` -> `results/` and `草稿` / `临时`
  -> `process/`. A finished `综述_xxx.txt` no longer falls through to
  `process/` because it lacks an English `final` in its name.

- **`init`** - the cheap entry point: skeleton + lift + config template,
  with no snapshot, no verification and no log file, so creating a task
  folder is instant.

- **Execution tiers** (`--mode quick|incremental|full`, default `full`):
  `incremental` reuses SHA-256 digests for files whose size and mtime are
  unchanged (hidden hash cache); `quick` is the no-frills tidy pass; `full`
  stays the guarantee tier.

- **Artifact rotation** (`--keep N`, default 5) keeps `process/` from
  growing without bound; the newest before/after snapshots are always
  protected.

- **Standalone `index` and `snapshot` sub-commands** - regenerate the
  hand-off indexes, or take the safety airbag before a risky batch
  operation.

- **Operation history & undo / redo** (`process/history/`):
  user-initiated reversal or re-application of a verified run, itself
  wrapped in the snapshot/verify/rollback protocol.

- **Smart deduplication** (`--dedupe-action report|move`): exact
  (SHA-256) and similar (first-1-KB prefix + `difflib` ratio >= 0.85)
  duplicates; `move` quarantines exact duplicates into
  `material/duplicates/` (originals are never deleted) and is covered by
  the forced verification.

- **YAML placement-rule config** (`.task-organizer.yml`) with named
  domain profiles (`--profile`), parsed by a dependency-free mini-reader
  that falls back to the built-ins on any error.

- **Per-day logging** (`process/logs/YYYYMMDD.log`) at INFO level, with
  `-v` / `-q` console control.

- **Agent-facing workflow**: `SKILL.md` opens with a mandatory workflow
  (resolve the path, pick the entry point, run via Bash, verify, report,
  declare provenance) so triggering the skill means *running* the tool,
  never answering with a description of it. Mirrored in `README_zh.md`.

- **The skill is pure English.** `SKILL.md` and `README.md` carry no CJK;
  the dedicated Chinese user guide remains separate.

- Test suite: **323 passing cases** (0 skipped when the dependencies are
  absent), coverage >= 80%.

### Hardening

Hardening found by two adversarial debug rounds before the release (both
rounds plus regression tests are part of the shipped 1.0.0):

- **Legacy encodings decoded as mojibake.** `text_extract` sniffs the
  encoding (BOM, then UTF-8, GBK/GB18030, Big5, a NUL-density probe for
  BOM-less UTF-16, latin-1 last) and rejects decodes that land in the
  Unicode private-use area - GBK/Big5 bytes under the wrong codec do
  exactly that. Chinese notes saved in GBK/Big5/UTF-16 now summarize
  correctly.

- **Unbounded reads.** Plain-text files are read with a bounded character
  count after a 64 KB encoding probe, and the stdlib PDF path caps its
  byte read, so a 500 MB log cannot exhaust memory.

- **Symlink cycles and hidden trees.** The scan walks with
  `os.walk(followlinks=False)` and prunes hidden directories, `process/`
  and `_broadcast/` before descending, so a symlink loop or a `.git`
  tree can neither hang the scan nor waste time inside it. Index paths
  use forward slashes on every platform.

- **Unbounded skip list.** When `--max-files` bites, the skipped list
  stays aggregated (one line) while the count still reports every file.

- **Markdown-breaking names.** Filenames containing backticks no longer
  break the one-line-per-file bullet; summaries are whitespace-collapsed.

- **AI mode told the truth.** `--ai` without a key degraded to local
  summaries while the index still claimed `ai`; the mode label now
  reflects what was actually used. `--ai` also forces AI past the
  `TASK_ORG_AI` opt-in when a key is configured, and one call returns
  both the summary and the keywords (half the round trips).

- **Local keyword quality.** Chinese keywords are repeated 2-4 character
  n-grams extended to their full repeated phrase (a frequent fragment is
  superseded by the longer phrase), with overlapping fragments dropped;
  summaries cut at a sentence boundary when one is near. PDF page counts
  are only computed for the metadata fallback instead of re-reading every
  PDF.

- **Built-in keyword table restored for folders with a config.** A folder
  that has the comment-only `.task-organizer.yml` template (exactly what
  `init` writes) previously lost the built-in keyword rules, so deliverable
  names like `开题报告_*.md` fell through to `process/` instead of
  `results/`. An empty / comment-only config now silently uses the
  built-in placement table, so `报告` / `final` still route correctly.
