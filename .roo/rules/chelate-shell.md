# Chelate Shell — agent operating rules (v1.2.0)

Chelate Shell is a deterministic **orchestrator** for local agent skills. It
routes work to the right skill through a gated pipeline; it does not generate
low-level Python itself.

## Install as one plugin

Install this repository as a **single plugin**. Do NOT scatter the folders under
`skills/` into a global skill directory and do NOT flatten the repository
layout — microkernel auto-routing depends on the structure.

## Entry points (run from the repo root; Python 3.10+)

- `python cli.py list` — list registered skills
- `python cli.py run <skill> --root <workspace> [args...]` — run one skill
- `python cli.py pipeline --root <workspace> --mode a|b|c` — run the pipeline
- `.dsh-plugin/index.js` — non-Python harness entry (`apply(ctx)`)

## Pipeline (strict order)

1. **workspace** — `task-organizer` initialises `material/initial/`, `process/`
   and `results/`. No writes to the workspace root before this completes.
2. **ingest** — normalise inputs into `process/`.
3. **gates** — every gate emits a result; one `FAIL` terminates the pipeline and
   locks `process/`.
4. **processors** — clean, transform and export into `results/`.

## Skills (18 total, flat under skills/)

- **workspace**: task-organizer, multi-dim-manager, document-evolution-tracker
- **ingest**: bibtex-normalizer, capstone-labmate, fulltext-extractor,
  literature-retriever, video-tracker
- **gates**: conflict-detector, data-profiler, formula-validator,
  longitudinal-analysis, quantitative-validator, ml-auditor, reference-auditor
- **processors**: ai-trace-remover, figure-generator, latex-exporter

## Hard rules

- Do not write to the workspace root before `task-organizer` runs.
- Treat a gate `FAIL` as terminal; stop downstream stages immediately.
- Sandboxed skills (`quantitative-validator`, `ml-auditor`, `figure-generator`) run through
  `core/sandbox.py`; missing dependencies degrade to `UNVERIFIED`, never crash.
- Keep intermediate products in `process/` and final products in `results/`.

Full contract: `ORCHESTRATOR.md`.
