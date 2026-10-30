# Chelate Shell

> **The missing orchestrator for your local agent skills.**
> Orchestrating scattered local skills into a deterministic research and engineering workflow.

**English** · [简体中文](README_zh.md)

**Version:** 1.1.3 | **Core Skills:** 14 | **Layers:** 4 (workspace / ingest / gates / processors)

---

## Security & Open Source Statement

> **Disclaimer**: This repository contains auxiliary tools developed by the author to automate research workflows. It is not a peer-reviewed academic project. Some boilerplate or utility scripts may have been generated with the assistance of AI, and have been integrated with high-level review and modifications by the author. The author assumes no responsibility for any third-party code issues, but commits to promptly addressing any valid claims.
>
> This tool **will never do the experiment for you**. Data must be collected manually by students in the lab; AI is absolutely physically isolated during the in-lab stage. Generated reports are merely "data-analysis drafts", and final academic responsibility lies with the user and their institution.

---
## Why Chelate Shell?

In the current AI ecosystem, individual skills excel at solving isolated problems: validating formulas, tracking videos, or organizing files. However, when an Agent faces a complex task, it often struggles to determine **which skill to invoke, in what order, and where to place the outputs**.

Chelate Shell is an **Orchestrator**. It does not write low-level code to solve domain-specific problems. Instead, acting like a senior project manager, it decomposes user intents, enforces a standardized workspace directory structure, and **deterministically** routes tasks to the appropriate skills.

### v1.1.0 Architecture: physical flatness + adapter isolation + microkernel

All 14 skills live **flat** under `skills/` — no nested category folders — so AI
platforms that scan a single directory level see every skill. Logical layering
lives in each skill's `manifest.json`, and a tiny microkernel (`core/`) reads
those manifests to build the pipeline.

```text
chelate/
├── .claude-plugin/            # Claude Code plugin manifest + marketplace
├── .codebuddy-plugin/         # CodeBuddy plugin manifest + marketplace
├── .codex-plugin/             # Codex plugin manifest + marketplace
├── .dsh-plugin/               # DeepSeek Harness CJS entry (apply(ctx))
├── assets/                    # icon.png (shared by the plugin manifests)
├── index.js                   # CJS plugin entry (dsh ecosystem)
├── package.json               # npm/dsh packaging metadata
├── cordis.patch.yml           # cordis bundle patch
├── ORCHESTRATOR.md            # agent-facing routing contract (v1.1.0)
├── core/                      # microkernel
│   ├── router.py                # dispatcher: manifest-driven pipeline
│   ├── registry.py              # scans skills/ into a routing table
│   └── sandbox.py               # dependency resolution / degradation
├── contracts/                   # global contracts
│   ├── gate_result.py           # {skill, status, evidence_level, reason, artifacts}
│   └── schema.json              # manifest.json validation spec
├── lib/chelate_core/            # shared core library (logic lives here)
│   ├── adapter.py               # thin-adapter toolkit: argparse, gate emission, legacy runner
│   ├── paths.py / yamlmini.py   # path resolution / assets/config.yaml loading
│   ├── pdf_text.py              # PDF extraction core (pdfminer.six / pypdf)
│   ├── arxiv_search.py          # arXiv search core
│   ├── bibtex_norm.py           # BibTeX parse / dedupe / normalize core
│   ├── doi_audit.py             # DOI extraction + Crossref verification core
│   ├── csv_profile.py           # CSV profiling core (pandas)
│   └── formula_merge.py         # legacy D1-D5 + pint verdict merge policy
├── skills/                      # 14 skills, completely flat
│   ├── task-organizer/          #   workspace  (infrastructure)
│   ├── multi-dim-manager/       #   workspace  (infrastructure)
│   ├── document-evolution-tracker/ # workspace (infrastructure)
│   ├── capstone-labmate/        #   ingest     (extraction)
│   ├── video-tracker/           #   ingest     (extraction)
│   ├── fulltext-extractor/      #   ingest     (extraction, new)
│   ├── literature-retriever/    #   ingest     (extraction, new)
│   ├── bibtex-normalizer/       #   ingest     (extraction, new)
│   ├── formula-validator/       #   gates
│   ├── longitudinal-analysis/   #   gates
│   ├── conflict-detector/       #   gates
│   ├── reference-auditor/       #   gates      (new)
│   ├── data-profiler/           #   gates      (new)
│   └── ai-trace-remover/        #   processors
│       ├── SKILL.md             #   instructions for the AI platform
│       ├── manifest.json        #   metadata for the Router
│       ├── README.md            #   human-facing documentation
│       ├── LICENSE              #   MIT (per-skill copy)
│       ├── run.py               #   thin adapter: CLI wiring only
│       └── assets/              #   config.yaml and other dead resources
└── tests/                       # automated test suite (191 tests)
```

Every skill directory carries the same surface: `SKILL.md` for the AI,
`manifest.json` for the Router, `README.md` for humans, `LICENSE`, and
`run.py` — a **thin adapter** that only parses arguments and formats the
gate result.

### Plugin manifests (Claude Code / CodeBuddy / Codex / dsh)

The repository doubles as a plugin for four host platforms. Each `.xx-plugin/`
directory holds that platform's `plugin.json` (+ `marketplace.json` where the
platform has one). The v1.0.0 manifests were silently rejected by Claude Code
for two contract violations; both are now locked down by
`tests/test_plugin_manifests.py`:

- **`author` must be an object** (`{"name": "Jiaming Shi"}`), not a bare
  string — a string author fails validation and the plugin is ignored.
- **`skills` is omitted, not `"./skills"`** — a string here fails validation
  too; when the field is absent the host auto-scans the `skills/` directory,
  which is exactly the flat layout this project ships. (A list of strings is
  also legal but unnecessary.)
- **`icon` is kept out of `plugin.json`** — it was the second rejection
  cause; the shared `assets/icon.png` stays in the repo for humans.

`version` is a single value across every skill manifest, every
`plugin.json` and `package.json`; the test suite fails on any disagreement.

### Programs live outside the skills

Business logic is never implemented inside a skill folder. The five new
skills are pure wiring over `lib/chelate_core/*`; the nine migrated skills
keep their byte-identical legacy trees and drive them through
`lib/chelate_core/adapter.py`. Consequences:

- **No duplicated code** — one PDF parser, one Crossref client, one
  BibTeX deduplicator, shared by every consumer.
- **Testable cores** — `tests/test_new_skills.py` exercises the library
  directly; a guard test (`tests/test_no_stubs.py`) fails if a skill
  folder re-implements a core function or grows past the adapter budget.
- **Crash isolation** — heavy dependencies are imported inside the library
  cores; a broken core degrades to an `UNVERIFIED` gate instead of taking
  the pipeline down.

### The manifest contract

```json
{
  "name": "formula-validator",
  "version": "1.1.3",
  "stage": "gates",
  "input_types": ["latex_string", "plain_text"],
  "output_type": "gate_result",
  "output_types": ["gate_result"],
  "dependencies": ["sympy", "numpy", "pint"],
  "sandbox_required": false,
  "entrypoint": "run.py",
  "description": "..."
}
```

`sandbox_required` marks skills that must run isolated (reserved for
v1.2.0 heavy dependencies; `false` for every v1.1.0 skill). The full spec
is `contracts/schema.json` (`additionalProperties: false` — unknown fields
are rejected, so the contract cannot rot).

### The gate contract

All `gates`-stage skills return a structured result:

```json
{
  "skill": "reference-auditor",
  "status": "FAIL",
  "evidence_level": "EXACT",
  "reason": "DOI 10.9999/fake-doi-12345 not found in Crossref",
  "artifacts": ["process/reference_audit_20261023T114148Z.json"]
}
```

`status` is `PASS` / `FAIL` / `UNVERIFIED`; `evidence_level` is
`EXACT` / `SYMBOLIC` / `EMPIRICAL` / `UNVERIFIED`. **Only `FAIL` hard-blocks
the pipeline.**

### Pipeline execution

1. **Registry**: at startup the Router scans the 14 `manifest.json` files
   (exactly one level under `skills/`) into an in-memory routing table.
2. **Ingest**: inputs are matched by type — a `.pdf` queues
   `fulltext-extractor` (and `capstone-labmate`), a `.bib` queues
   `bibtex-normalizer`, keywords queue `literature-retriever`.
3. **Gates**: the `gates` skills run serially — `formula-validator`,
   `reference-auditor`, `data-profiler`, `longitudinal-analysis`,
   `conflict-detector`.
4. **Hard block**: the first gate returning `FAIL` terminates the pipeline
   immediately (red terminal output). Intermediate products stay locked in
   `process/` and are never promoted to `results/`.
5. **Promotion**: only when every gate passes is `process/` copied to
   `results/promoted_<ts>/`, followed by the `processors` stage.

### Debugging

One switch, every layer: add `--debug` to any `cli.py` subcommand
(`list` / `run` / `pipeline`) or to `core/router.py`, or export
`CHELATE_DEBUG=1` for the whole process tree. The flag sets the same
environment variable, so skill subprocesses inherit it automatically.

```bash
# debug one skill directly (flag may sit before or after the skill name)
python cli.py run data-profiler --root /path/to/workspace --action profile --input data.csv --debug

# debug a whole pipeline
CHELATE_DEBUG=1 python cli.py pipeline --root /path/to/workspace --mode c --selected reference-auditor
```

With the switch on, stderr receives `[chelate:debug]` lines covering the
registry scan, the resolved subprocess command and cwd, the dependency
verdict (degraded / missing), the return code and duration, the last
stderr lines of each skill, the legacy action → module mapping, and the
final gate path with its status. **stdout is never polluted** — the single
gate-contract JSON line stays machine-parseable. Output colors follow
`NO_COLOR` / `CHELATE_FORCE_COLOR`.

For post-mortem analysis, every run leaves machine-readable traces:
`process/gates/<skill>_<ts>.json` (one gate result per skill),
`results/pipeline_report_<ts>.json` (the full decision record, including
the command, degraded flag, missing dependencies, return code and seconds
of every skill), and `_broadcast/pipeline_index_<ts>.json` (the compact
context-compression index).

---
## Quick start

```bash
# list the 14 registered skills
python cli.py list

# run one skill directly
python cli.py run reference-auditor --root /path/to/workspace \
    --action audit --input draft.md

# dry-run a pipeline (shows the planned execution order)
python cli.py pipeline --root /path/to/workspace --mode a --input-kind pdf --dry-run

# full pipeline: ingest -> gates -> processors
python cli.py pipeline --root /path/to/workspace --mode a --input-kind pdf

# gates only, with per-skill arguments
python cli.py pipeline --root /path/to/workspace --mode c \
    --selected reference-auditor \
    --skill-arg "reference-auditor:--input draft.md"

# declare the run's input files: each is wired as --input to the plan
# skills whose manifest input_types declare its type (missing files fail
# fast with exit code 2 before anything runs)
python cli.py pipeline --root ./test_workspace --inputs draft.md data.csv
```

Pipeline modes: `a` auto (ingest → gates → processors), `b` extract-only,
`c` gates-only. `--inputs` narrows the plan to the skills that can consume
the declared files (an explicit `--selected` list always wins); a file
whose extension declares no manifest type is reported as an `[INPUT]`
warning and wires to nothing.

## The 14 skills

**Workspace (infrastructure)**
- `task-organizer` — four-zone workspace init, file organization (C1–C8
  validation, dedupe, snapshots, undo/redo), `_broadcast/INDEX.md` context index
- `multi-dim-manager` — parameter-space expansion, SHA-256 snapshots, hash
  audit logs, safe rollback to any past round
- `document-evolution-tracker` — paragraph-level diff across document
  versions with concept-lineage tracking

**Ingest (extraction)**
- `capstone-labmate` — PASCO Capstone `.cap` binary parsing, CSV/JSON
  conversion, watermarked draft reports
- `video-tracker` — OpenCV coordinate extraction (CSRT/Template trackers),
  FFT spectrum analysis, physics consistency probes
- `fulltext-extractor` *(new)* — pdfminer.six text extraction into `process/` (pypdf fallback)
- `literature-retriever` *(new)* — arXiv keyword search to JSON
- `bibtex-normalizer` *(new)* — `.bib` parsing, dedupe, normalized output

**Gates**
- `formula-validator` — SymPy D1–D5 layers (dimensional analysis, limit
  enumeration, numeric sampling, symbolic proof) merged with a `pint`
  physical-unit cross-check
- `longitudinal-analysis` — time-series OLS plus R-backed LMM (lme4),
  mediation (lavaan) and sensitivity analysis; degrades to pure-Python steps
  when Rscript is absent
- `conflict-detector` — cross-document contradiction engine with regex
  number extraction for hard cross-checks
- `reference-auditor` *(new)* — DOI extraction and Crossref verification;
  a non-existent DOI fails the gate
- `data-profiler` *(new)* — pandas CSV profiling: row counts, missing-value
  statistics, 1.5·IQR outlier ratios, duplicates, constant columns

**Processors**
- `ai-trace-remover` — template-sentence removal and a 0–100 "AI-likeness"
  score (clean-room English lexicon plus the full Chinese lexicon)

## Migration guarantee (v1.0.0 → v1.1.0)

The nine legacy skills were migrated **byte-for-byte**: 179 Python files
(~37,400 lines) plus all non-code assets were copied with SHA-256
verification, and the internal package layout (`scripts.*`, `src.*`, `R/`,
`templates/`, `config/`) is unchanged. The only additions are each skill's
root `run.py` adapter, its `manifest.json`, and — for `formula-validator` —
a new `scripts/core/pint_units.py` layer. A guard test
(`tests/test_capability_guard.py`) re-verifies file parity and the presence
of every key module function on every run.

## Tests

```bash
python -m pytest tests/ -q     # 191 tests (190 passed, 1 skipped: v1.0.0 source tree not present)
```

The suite covers the gate contract, manifest schema validation, flat-layout
enforcement, pipeline planning and FAIL termination, the migration guard,
the legacy D1–D5 and FFT/physics probes, the five new skills, workspace
input-path resolution, `--inputs` auto-wiring (manifest-type matching,
plan narrowing, fail-fast on missing files), the unified debug layer
(switch semantics plus a real-subprocess integration test for the router's
debug plumbing), and the manifest-contract suite (plugin manifests for all
four host platforms: author-object, no string `skills`, no `icon`, version
sync; SKILL.md frontmatter agreeing with each manifest).

## Requirements

Python 3.10+. Per-skill dependencies are declared in each `manifest.json`
and resolved at run time by `core/sandbox.py`; a missing dependency
degrades the skill to an `UNVERIFIED` gate instead of crashing the pipeline.

| Skill | Required dependencies | Optional (degrade gracefully) |
|-------|----------------------|------------------------------|
| video-tracker | numpy, opencv | matplotlib (FFT plots), PyYAML (`.yaml` configs) |
| formula-validator | sympy, numpy, pint | — |
| longitudinal-analysis | pandas | numpy, R (lme4/lavaan), python-docx (`--format docx` export), PyYAML (`.yaml` configs) |
| capstone-labmate | *(stdlib only)* | numpy (vectorized paths), matplotlib (plots), pypdf (PDF text) |
| task-organizer | *(stdlib only)* | openpyxl (fast `.xlsx` path), PyPDF2 (one PDF backend) |
| multi-dim-manager, document-evolution-tracker, conflict-detector | *(stdlib only)* | PyYAML (`.yaml` configs; JSON configs need nothing) |
| ai-trace-remover | *(stdlib only)* | — |
| fulltext-extractor | pdfminer.six / pypdf | — |
| literature-retriever | `arxiv` | — |
| bibtex-normalizer | `bibtexparser` | — |
| reference-auditor | `requests` | — |
| data-profiler | `pandas` | — |

Third-party packages are used at run time only; none are vendored into this
repository, and each remains under its own license (e.g. numpy/pandas BSD,
OpenCV Apache-2.0, SymPy/pint/requests/bibtexparser/arxiv BSD/MIT/Apache,
pdfminer. six is MIT; pypdf is BSD-3-Clause — both permissive). Optional dependencies are imported behind
`try`/`ImportError` or action-scoped conditionals, so a missing one degrades
that feature (or that config format) — never the whole skill.

## Trademarks

"PASCO" and "Capstone" are registered trademarks of PASCO Scientific. The
`capstone-labmate` skill is an independent, third-party interoperability and
educational-assistance tool. It is not affiliated with, endorsed by, or
sponsored by PASCO Scientific. All `.cap` parsing runs locally; users are
responsible for complying with their institution's academic-integrity policy.

## License

MIT. See [LICENSE](LICENSE). Each skill directory also carries its own
`LICENSE` file with the same terms.
