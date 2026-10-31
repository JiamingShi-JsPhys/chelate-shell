# Chelate v1.1.0 — Complete Construction Plan

Positioning: **heavy-asset, lossless migration** — 9 legacy skills / 179 Python
files / 37,356 LOC move 1:1 under a flat microkernel shell; 5 new skills are
written from scratch. Architecture: **absolute physical flattening + adapter
isolation + microkernel scheduling**.

---

## 1. Red lines (non-negotiable)

| # | Rule | Enforcement |
|---|------|-------------|
| R1 | All 14 skills flat in `skills/` — no `namespaces/`, no `03_gates/`, no nesting | registry scan asserts depth; test |
| R2 | No empty shells — no `pass` / `TODO` in any shipped file | grep guard in tests |
| R3 | 100% capability migration of the 9 legacy skills (every module & function in `docs/FILE_FUNCTION_MAP.md`) | per-skill capability-assertion tests |
| R4 | Internal package layout preserved verbatim (`scripts.*`, `src.*`, `R/`, `templates/`, `config/`, `references/`) | byte-identical copy, no rewrite |
| R5 | Gate FAIL terminates the pipeline; intermediates stay in `process/`, never enter `results/` | router logic + acceptance test |
| R6 | Engineering code/docs in English; no git push; local packaging only | project convention |

---

## 2. Directory topology (per approved blueprint)

```text
chelate-shell-v1.1.0/
├── bootstrap.py               # shared sys.path + gate-writing helpers (kept, cleaned)
├── cli.py                     # operator CLI: list / run / pipeline (kept, rewritten router call)
├── core/
│   ├── __init__.py
│   ├── registry.py            # scans skills/*/manifest.json -> routing table (rewritten)
│   ├── router.py              # stage state-machine + hard gate blocking (rewritten from scratch)
│   └── sandbox.py             # dependency degradation decisions (kept, adapted)
├── contracts/
│   ├── __init__.py            # re-exports gate_result helpers
│   ├── gate_result.py         # {skill, status, evidence_level, reason, artifacts} (rewritten to new contract)
│   └── schema.json            # manifest JSON Schema (updated: input_types, entrypoint)
├── skills/                    # 14 flat skill directories
│   ├── <skill>/
│   │   ├── SKILL.md           # AI-facing doc (migrated / new)
│   │   ├── manifest.json      # router metadata
│   │   ├── run.py             # NEW adapter entry (root level)
│   │   └── scripts/ | src/    # legacy modules 1:1 (plus R/, templates/, config/, references/)
├── tests/                     # pytest suite
└── docs/                      # audit + plan artifacts (this file, checklist, file map)
```

`process/` and `results/` are runtime workspace zones created by the router /
task-organizer, not shipped.

---

## 3. Contract layer

### 3.1 manifest.json (per skill, per approved field set)

```json
{
  "name": "formula-validator",
  "version": "1.2.0",
  "stage": "gates",
  "input_types": ["latex_string", "plain_text"],
  "output_type": "gate_result",
  "dependencies": ["sympy", "pint"],
  "entrypoint": "run.py",
  "description": "..."
}
```

Stage enum: `workspace` (3 infra skills) / `ingest` (4 extractors) /
`gates` (5 gates) / `processors` (ai-trace-remover). The blueprint's
ingest/gates/processors are the pipeline stages; `workspace` skills are
user-invoked utilities and are excluded from automatic pipeline dispatch.

### 3.2 gate_result.json (single output contract)

```json
{
  "skill": "reference-auditor",
  "status": "FAIL",
  "evidence_level": "UNVERIFIED",
  "reason": "DOI 10.9999/does.not.exist not found in Crossref",
  "artifacts": ["process/gates/reference-auditor_20261023T...json"]
}
```

`status`: PASS | FAIL | UNVERIFIED (WARN folded into UNVERIFIED per blueprint).
`evidence_level`: EXACT | SYMBOLIC | EMPIRICAL | UNVERIFIED.
Written to `process/gates/<skill>_<UTC ts>.json` by `bootstrap.write_gate`.
Terminal output: PASS green, FAIL **red**, UNVERIFIED yellow.

---

## 4. Microkernel design

### 4.1 core/registry.py
- Scan `skills/*/manifest.json` only (never import skill code, never read
  SKILL.md) — lazy metadata load.
- Validate each manifest against `contracts/schema.json`; invalid manifests are
  recorded as errors and excluded from the routing table (reported, not fatal).
- Build `name -> SkillRecord` plus a `stage -> [records]` index.

### 4.2 core/router.py — state machine
```
inputs (files + inline payload)
  │
  ▼
[stage=ingest]   match by extension / input_types → extract → write process/
  │                     (missing extractor → UNVERIFIED, continue)
  ▼
[stage=gates]    serial, in registry order (formula-validator, reference-auditor,
  │              conflict-detector, longitudinal-analysis, data-profiler)
  │               ├─ PASS / UNVERIFIED → next gate
  │               └─ FAIL → TERMINATE: red banner, intermediates locked in
  │                        process/, nothing copied to results/
  ▼
[stage=processors]  ai-trace-remover etc. run only when all gates passed
  │
  ▼
promote: process/ artifacts → results/ (only on full pass)
```
- Each skill runs as a subprocess: `python <skill_dir>/run.py --root <ws>
  --action <action> [skill args]`, exit code 0 required; non-zero = UNVERIFIED
  with stderr captured.
- Router reads the gate file the skill wrote and adjudicates.
- `--dry-run` prints the plan without executing.

### 4.3 core/sandbox.py
Kept as-is in spirit: resolve declared dependencies; missing deps → skill
degrades to UNVERIFIED instead of crashing. True venv isolation is v1.2.0.

---

## 5. Skill landing matrix (14)

### 5.1 Migrated 9 — adapter wiring (verified against source)

| Skill | Stage | Legacy layout | Adapter (`run.py`) wiring | Actions exposed |
|-------|-------|---------------|---------------------------|-----------------|
| task-organizer | workspace | `scripts/` pkg, absolute `from scripts import ...` | `sys.path+=SKILL_ROOT`; `from scripts import run as legacy` | init / organize / broadcast / index / snapshot / verify / dedupe / undo / redo / doctor |
| multi-dim-manager | workspace | `scripts/` pkg, relative imports | `from scripts import run as legacy` | run / dryrun / rollback / summary / verify |
| document-evolution-tracker | workspace | `src/` pkg, relative imports | `from src import cli as legacy` | track / diff / lineage |
| capstone-labmate | ingest | plain scripts, `import _capx` | `sys.path+=SKILL_ROOT/scripts`; `import preconfigure_cap / process_cap / draft_report` | preconfigure / process / draft |
| video-tracker | ingest | `scripts/` pkg, relative imports | `from scripts import run as legacy` | probe / track / fft / physics / report / demo |
| longitudinal-analysis | gates | `src/` pkg + `R/` | `from src import cli as legacy` | run pipeline (steps: descriptive/lmm/mediation/sensitivity/manipulation) |
| formula-validator | gates | `scripts/` pkg, absolute | `from scripts import cli as legacy` | validate / check / derive / matrix |
| ai-trace-remover | processors | `src/` pkg, relative | `from src import cli as legacy` | scan (score + suggestions) |
| conflict-detector | gates | `src/` pkg, relative | `from src import cli as legacy` | detect (docs/JSON sources) |

Adapter contract (all 14 identical):
```
python run.py --root <ws> --action <action> [-- <legacy args>] --json
```
- Translates `--action` to legacy argv, calls the legacy entry **in-process**
  (no behavior change), captures exit code + stdout.
- Maps outcome to a GateResult, writes `process/gates/<skill>_<ts>.json`,
  prints one-line JSON to stdout.
- Legacy CLIs remain directly runnable (`python scripts/cli.py ...` etc.) —
  the adapter is additive, never a replacement.

### 5.2 New 5 — clean-room implementations

| Skill | Stage | Library | Behavior | Degradation |
|-------|-------|---------|----------|-------------|
| fulltext-extractor | ingest | PyMuPDF (`fitz`) | PDF → per-page text → `process/fulltext/<name>.txt` + meta JSON | missing PyMuPDF → UNVERIFIED gate, clear install hint |
| literature-retriever | ingest | `arxiv` | keywords/max-results → title/abstract/published/url JSON → `process/literature/` | offline / API error → UNVERIFIED |
| bibtex-normalizer | ingest | `bibtexparser` | parse `.bib` → dedupe by normalized DOI/title → standard BibTeX + JSON report | malformed file → UNVERIFIED with entry-level errors |
| reference-auditor | gates | `requests` | DOI regex from draft → Crossref `/works/<doi>` → 200 = PASS, 404 = **FAIL**, network error = UNVERIFIED | network error never faked as PASS |
| data-profiler | gates | `pandas` | CSV → rows/cols/dtypes/missing-%/outlier-% (IQR + z-score) → JSON + MD | unreadable CSV → UNVERIFIED |

All five reference public library documentation patterns; implementations are
written from scratch (no copied code blocks).

---

## 6. Construction phases

### Phase 0 — Skeleton & cleanup (today)
- Delete 7 encrypted files in `chelate-shell-v1.1.0/` (`core/router.py`, 5
  skill `run.py`s) and stale artifacts (`_probe_fv/`, old `process/`).
- Keep clean: `core/registry.py` (rewrite), `core/sandbox.py` (keep),
  `contracts/gate_result.py` (rewrite to new contract), `contracts/schema.json`
  (update), `bootstrap.py` (keep), `cli.py` (adapt to new router API).

### Phase 1 — Contracts
- `contracts/gate_result.py`: GateStatus(PASS/FAIL/UNVERIFIED),
  Evidence(EXACT/SYMBOLIC/EMPIRICAL/UNVERIFIED), `GateResult` dataclass with
  `to_dict()`, helpers `pass_gate/fail_gate/unverified_gate`, file writer.
- `contracts/schema.json`: required `[name, version, stage, input_types,
  output_type, entrypoint, description]`; stage enum; entrypoint must be
  `run.py`.

### Phase 2 — Microkernel
- `core/registry.py`: manifest scan + schema validation + stage index.
- `core/router.py`: state machine per §4.2 with red FAIL banner, process/
  locking, results/ promotion, `--dry-run`.
- `cli.py`: `list` / `run <skill> --action ...` / `pipeline --root --inputs`.

### Phase 3 — Migrate 9 legacy skills
- Byte-identical copy of each skill tree from `chelate-shell-main/skills/`
  into `skills/<name>/` (excluding `__pycache__`), preserving internal layout.
- Write root `run.py` adapter per §5.1 (one shared adapter skeleton, per-skill
  action table).
- Write `manifest.json` per §3.1; refresh `SKILL.md` front-matter version to
  1.1.0 (body unchanged).
- Self-check per skill: `python run.py --action <default> --root <tmpws>`
  exits 0 and writes a gate file; legacy CLI still runs.

### Phase 4 — Write 5 new skills
- Per §5.2, each with `SKILL.md` + `manifest.json` + `run.py` + real logic.
- Unit-test each with local fixtures (no network where avoidable: Crossref and
  arXiv tests use recorded/offline fallbacks + one live smoke test).

### Phase 5 — tests/
- `test_registry.py`: 14 skills discovered, manifests valid, flat (no nested
  skill dirs), entrypoint exists.
- `test_contracts.py`: gate serialization round-trip, status enum.
- `test_router.py`: fake-DOI draft → pipeline FAIL, nothing in results/;
  happy path promotes to results/.
- `test_capability_migration.py`: for every skill, import the legacy entry
  module and assert the presence of the key functions listed in
  `docs/FILE_FUNCTION_MAP.md` (guards R3).
- `test_no_stubs.py`: no `TODO` / bare `pass` bodies in shipped `run.py`s.
- Per-skill functional tests (ported legacy tests run from their new home):
  formula-validator dimension check, video-tracker FFT on demo CSV, etc.

### Phase 6 — Acceptance (spec §4) & packaging
1. `python cli.py list` → 14 skills; `python tests/bootstrap_check.py` (or
   pytest) asserts 14 directories exist.
2. Fake-DOI draft → terminal red `FAIL` + standard `gate_result.json`.
3. `formula-validator` dimension validation passes; `video-tracker` FFT
   reproduces the demo spectrum.
4. README / CHANGELOG updated; zip packaged locally (no push).

---

## 7. Risk register

| Risk | Mitigation |
|------|-----------|
| Encrypted files resurface in copies | migration source is the verified clean tree; post-copy UTF-8 scan is part of Phase 3 self-check |
| Heavy optional deps absent (sympy, opencv, pandas, R) | sandbox degradation → UNVERIFIED gate; acceptance tests use available deps + skip-with-reason for the rest |
| Adapter import breaks legacy relative imports | all 3 import patterns verified against source (§5.1); Phase 3 self-check runs every legacy entry |
| Crossref/arXiv network unavailable in CI | offline fallback → UNVERIFIED; FAIL only on definitive 404 |
| Capability drift during migration | Phase 5 capability-assertion tests keyed to the 179-file function map |

---

## 8. Definition of done

- [ ] 14 flat skill dirs, each: SKILL.md + manifest.json + run.py + real code
- [ ] All 179 legacy files present, byte-identical, importable from new home
- [ ] Registry + router + contracts green; three acceptance criteria pass
- [ ] pytest suite green (with documented skips for absent heavy deps)
- [ ] No push; local zip only
