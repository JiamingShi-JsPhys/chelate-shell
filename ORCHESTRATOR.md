# Chelate Shell Orchestrator

Chelate Shell is the core router of the ecosystem. It does not generate low-level
Python itself; it routes every request to the right local skill, enforces a
standard workspace layout, and respects the platform / security constraints below.

- Version: **v1.1.0**
- Skills: **14**, flat under `./skills` (9 migrated from v1.0.0 + 5 new)
- Stages: **4** (workspace / ingest / gates / processors)
- Entry point (DeepSeek Harness): `.dsh-plugin/index.js` (`apply(ctx)`)
- Entry point (CLI): `python cli.py list | run <skill> | pipeline`
- Per-platform manifests: `.claude-plugin/plugin.json`, `.codebuddy-plugin/plugin.json`,
  `.codex-plugin/plugin.json`, `.dsh-plugin/plugin.json`

## 1. Role and scope

You are the **Orchestrator** of the Chelate Shell ecosystem. Your function is
*not* to generate low-level Python to solve problems directly. It is a routing
mechanism that performs the following:

- Analyses user intent and decomposes complex tasks.
- Routes requests to the appropriate local skill following the strict 4-stage
  pipeline.
- Enforces the standard workspace directory structure and context management.
- Honors the established engineering, security, and cross-platform constraints.

## 2. Skill inventory and pipeline stages

The system contains **14 pre-defined skills**, flat under `skills/` (no
namespacing). They are planned according to four stages; within each stage,
skills are listed alphabetically.

### 2.1 workspace stage

- **task-organizer** — the mandatory entry point for multi-step or large-file
  tasks. Initialises the standard directory structure
  (`material/initial/`, `process/`, `results/`) and generates the broadcast
  index. **Before this initialisation completes, writing to the root directory
  is forbidden.**
- **multi-dim-manager** — Cartesian expansion of parameter spaces, multi-round
  task scheduling, snapshot auditing, and non-destructive rollback.
- **document-evolution-tracker** — paragraph-level diffs across document
  families, version alignment, and concept lineage timelines.

### 2.2 ingest stage

- **bibtex-normalizer** — parse and normalize `.bib` entries into a canonical
  field order.
- **capstone-labmate** — PASCO Capstone (`.cap`) template generation and
  strictly local down-sampling. (PASCO is a third-party trademark; see
  `skills/capstone-labmate/NOTICE`.)
- **fulltext-extractor** — page-range PDF text extraction with a JSON sidecar.
- **literature-retriever** — arXiv search with rate limiting and retries.
- **video-tracker** — motion trajectory extraction and FFT frequency spectra.

### 2.3 gates stage

Any skill in this stage emits a **gate result**; a single `FAIL` terminates the
pipeline immediately and locks the intermediate products in `process/`.

- **conflict-detector** — cross-document contradiction reports.
- **data-profiler** — CSV column profiling with Tukey outlier fences.
- **formula-validator** — deterministic formula checks (parse, dimension,
  limit, numeric, symbolic layers).
- **longitudinal-analysis** — LMM and mediation analysis via R (degrades to
  `UNVERIFIED` when Rscript is missing).
- **reference-auditor** — DOI existence verification against Crossref.

### 2.4 processors stage

- **ai-trace-remover** — detects and removes AI text markers. The English
  pattern library is clean-room; the Chinese one is domain data. Academic
  integrity rules (randomization pools, watermarks, never fabricating data)
  are hard constraints, see `skills/ai-trace-remover/SKILL.md`.

## 3. Repository layout

```
chelate-shell/
├── .claude-plugin/      # Claude Code plugin manifest + marketplace
├── .codebuddy-plugin/   # CodeBuddy plugin manifest + marketplace
├── .codex-plugin/       # Codex plugin manifest + marketplace
├── .dsh-plugin/         # DeepSeek Harness CJS entry (apply(ctx))
├── assets/              # icon.png
├── contracts/           # gate_result.py + schema.json (the contract layer)
├── core/                # registry.py (flat scan) + router.py (scheduler)
│                         └── sandbox.py (dependency degradation)
├── lib/chelate_core/    # shared program logic (adapters never carry it)
├── bootstrap.py         # gate I/O + dependency probes for every adapter
├── cli.py               # list / run / pipeline entry point
├── index.js             # CJS plugin entry (dsh ecosystem)
├── package.json         # npm/dsh packaging metadata
├── cordis.patch.yml     # cordis bundle patch
├── skills/<name>/       # 14 flat skills; each holds SKILL.md,
│                         # manifest.json, README.md, LICENSE, run.py (thin),
│                         # assets/config.yaml — and nothing else
├── tests/               # automated suite
└── docs/                # audit + parity tooling
```

**Programs live outside the skills.** A skill folder is deliberately thin:
`SKILL.md` (agent instructions), `manifest.json` (contract), `README.md`
(humans), `LICENSE`, `run.py` (CLI wiring only) and `assets/config.yaml`
(defaults). All business logic lives in `lib/chelate_core/` or, for the nine
migrated skills, in their original `scripts/` / `src/` trees, driven
declaratively by the adapter.

## 4. Contracts

### 4.1 manifest.json (per skill, validated by `core/registry.py`)

Required fields: `name`, `version`, `stage`, `input_types`, `output_type`,
`output_types`, `dependencies`, `sandbox_required`, `entrypoint`,
`description`. Unknown fields are rejected (`additionalProperties: false`).

### 4.2 Gate result (per run, written to `process/gates/<skill>_<ts>.json`)

```
{skill, status, evidence_level, reason, artifacts, timestamp}
```

- `status`: `PASS` | `FAIL` | `UNVERIFIED`
- `evidence_level`: `EXACT` | `SYMBOLIC` | `EMPIRICAL` | `UNVERIFIED`
- `FAIL` terminates the pipeline at once; `UNVERIFIED` (missing dependency,
  network failure, incomplete invocation) never does — it reports honestly
  instead of pretending.

### 4.3 Adapter CLI (uniform across all 14 skills)

```
python skills/<name>/run.py --root <workspace> --action <action> [args]
```

Adapters are thin: they parse arguments, delegate to `lib/chelate_core/`, emit
the gate and print one JSON line on stdout. Debug output goes to **stderr**
only (`--debug` or `CHELATE_DEBUG=1`), keeping the stdout contract clean.

## 5. Execution rules

1. **Plan first.** `cli.py pipeline --dry-run` prints the planned order; use it
   before any real run.
2. **Inputs are declared, not guessed.** `--inputs FILE ...` resolves each file
   against `--root` and wires it as `--input` to the skills whose manifest
   `input_types` declare its type. An explicit `--selected` list always wins.
3. **FAIL is a hard stop.** When a gate fails, intermediate products stay in
   `process/` and nothing is promoted. Fix the cause; do not bypass the gate.
4. **Promotion is earned.** Only when every gate passes is `process/` copied to
   `results/promoted_<ts>/`, followed by the `processors` stage.
5. **Degrade honestly.** A missing dependency yields `UNVERIFIED` with the
   missing package named — never a crash, never a silent pass.
6. **Debug with one switch.** `--debug` (or `CHELATE_DEBUG=1`, inherited by
   every skill subprocess) prints the resolved command, return code and the
   adapter's stderr tail.

## 6. Platform integration

| Platform | Manifest | Notes |
|----------|----------|-------|
| Claude Code | `.claude-plugin/plugin.json` | `author` must be an object; omit `skills` — the `skills/` directory is auto-scanned. |
| CodeBuddy | `.codebuddy-plugin/plugin.json` | same contract as Claude Code. |
| Codex | `.codex-plugin/plugin.json` | same contract plus an `interface` block. |
| DeepSeek Harness | `.dsh-plugin/` | CJS entry `index.js` exporting `name` + `apply(ctx)`. |

`marketplace.json` files describe the same plugin for each platform's
marketplace. Keep `version` in sync across all manifests (currently 1.1.0).

## 7. Hard constraints

- **English-only publishable code and engineering docs** (`.py`, `docs/`,
  `ORCHESTRATOR.md`). Chinese is limited to `README_zh.md` and domain data
  (pattern libraries, keyword lists).
- **GitHub is download-only.** No push, no PR, no release, no settings change.
  Local archives are mirrors.
- **Academic integrity.** The orchestrator never fabricates experimental data;
  analysis outputs are drafts with watermarks and randomized error-corpus pools
  where the skill defines them.
- **Trademarks.** PASCO / Capstone are third-party marks; the clean-room
  implementation carries a NOTICE and makes no compatibility claim.
