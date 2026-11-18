[chelate-shell](../README.md) · [简体中文](REFERENCE_zh.md)

# Reference

Every directory in the repository, and what each of the 25 skills does. The
front page of the README keeps the short version: **core/** is the microkernel,
**lib/chelate_core/** is the shared logic, **skills/** holds one folder per
skill.

## Repository layout

```text
chelate-shell/
├── .claude-plugin/                   # Claude Code plugin manifest + marketplace
├── .clinerules/                      # Cline rule file
├── .codebuddy-plugin/                # CodeBuddy plugin manifest + marketplace
├── .codex-plugin/                    # Codex plugin manifest + marketplace
├── .continue/rules/                  # Continue rule directory
├── .cursor/rules/                    # Cursor rule file (.mdc)
├── .dsh-plugin/                      # DeepSeek Harness descriptor (re-exports index.js)
├── .github/                          # GitHub Copilot instruction file
├── .gitignore
├── .roo/rules/                       # Roo Code rule directory
├── .windsurf/rules/                  # Windsurf rule file
├── agents/                           # sub-agent role definitions
│   ├── spatial_agent.md              # mesh/3D role (3d-modeler)
│   └── visual_agent.md               # figure/visualisation role (sci-visualizer + latex-exporter)
├── AGENTS.md                         # generic agent contract (Codex / Cursor / Copilot / opencode)
├── assets/                           # icon.png (shared by the plugin manifests)
├── bootstrap.py                      # shared import + gate-write helper for every run.py
├── CHANGELOG.md                      # release notes
├── cli.py                            # CLI entry: list / run / approve / pipeline / publish / audit / status /
│                                     # recipe / hook / memory / update
├── commands/                         # slash commands
│   ├── figure.md                     # /figure — chart from a CSV or JSON dataset
│   └── model3d.md                    # /model3d — OBJ mesh generate / merge / audit
├── contracts/                        # global contracts
│   ├── __init__.py
│   ├── gate_result.py                # {skill, status, evidence_level, reason, artifacts,
│   │                                 #  inputs, provenance}  (last two bind a PASS to bytes)
│   └── schema.json                   # manifest.json validation spec
├── cordis.patch.yml                  # cordis bundle patch
├── core/                             # microkernel
│   ├── __init__.py
│   ├── approval.py                   # promotion tokens: signing, expiry, atomic spend, revocation
│   ├── broker.py                     # two-channel publication broker (submit / approve, separate keys)
│   ├── hooks.py                      # pipeline/host hook dispatch (argv only, scrubbed env)
│   ├── memory.py                     # append-only hash-chained workspace notes
│   ├── recipes.py                    # serial recipe loading, validation, graph, run
│   ├── registry.py                   # scans skills/ into a routing table
│   ├── router.py                     # dispatcher: manifest-driven pipeline
│   ├── sandbox.py                    # dependency resolution / 120-second circuit-breaker
│   ├── runtime.py                    # the five-call Runtime API (policy / fail-closed broker)
│   ├── security_shield.py            # anti-injection text scan + AST dangerous-call scan
│   ├── skillkit.py                   # skill scaffolding + manifest/SKILL.md/README/CHANGELOG lint
│   ├── snapshot.py                   # content-addressed input snapshots (TOCTOU)
│   ├── subagent_manager.py           # sub-agent role registry
│   └── update.py                     # self-update check (version lookup, no auto-install)
├── docs/                             # this reference, architecture, testing, install commands, dependencies
├── index.js                          # ESM plugin entry (dsh: registers 4 tools)
├── install.py                        # one-command rule-file installer (see Installation)
├── lib/chelate_core/                 # shared core library (logic lives here)
│   ├── __init__.py
│   ├── adapter.py                    # thin-adapter toolkit: argparse, gate emission, legacy runner
│   ├── arxiv_search.py               # arXiv search core
│   ├── bibtex_norm.py                # BibTeX parse / dedupe / normalize core
│   ├── codegate.py                   # eight fixed AST code-quality rules
│   ├── csv_profile.py                # CSV profiling core (pandas)
│   ├── debug.py                      # [chelate:debug] switch shared by every layer
│   ├── deck.py                       # Markdown reports -> one self-contained HTML deck
│   ├── doi_audit.py                  # DOI extraction + Crossref verification core
│   ├── formula_merge.py              # legacy D1-D5 + pint verdict merge policy
│   ├── paths.py                      # path resolution
│   ├── pdf_text.py                   # PDF extraction core (pdfminer.six / pypdf)
│   ├── repro.py                      # deterministic result bundle (build / verify)
│   ├── schema_check.py               # CSV/JSON column-contract validator
│   ├── scholar_search.py             # Crossref / PubMed / DOI lookup core
│   ├── testgate.py                   # declared test command runner, verdict from output
│   └── yamlmini.py                   # assets/config.yaml loader
├── LICENSE
├── ORCHESTRATOR.md                   # agent-facing routing contract (v1.4.0)
├── package.json                      # npm/dsh packaging metadata
├── README.md
├── README_zh.md
├── skills/                           # 25 skills, all flat — one folder per skill
│   ├── 3d-modeler/                   # [domain_extensions] pure-Python OBJ mesh generate /
│   │                                 # merge / audit with mesh QC; sandboxed
│   ├── ai-trace-remover/             # [processors] template-sentence removal and a
│   │                                 # 0–100 "AI-likeness" score (EN + ZH lexicons)
│   ├── bibtex-normalizer/            # [ingest]    .bib parsing, dedupe, normalized output
│   ├── code-gate/                    # [gates]     eight fixed AST rules over Python
│   │                                 # source; ruff opt-in, named when it runs
│   ├── conflict-detector/            # [gates]     cross-document contradiction engine
│   │                                 # with regex number extraction
│   ├── data-profiler/                # [gates]     pandas CSV profiling: row counts,
│   │                                 # missing values, 1.5·IQR outliers, duplicates, constant columns
│   ├── document-evolution-tracker/   # [workspace] paragraph-level diff across
│   │                                 # document versions, concept-lineage tracking
│   ├── formula-validator/            # [gates]     SymPy D1–D5 layers (dimensional analysis,
│   │                                 # limit enumeration, numeric sampling, symbolic proof)
│   │                                 # + pint unit cross-check
│   ├── fulltext-extractor/           # [ingest]    pdfminer.six text extraction into process/
│   │                                 # (pypdf fallback)
│   ├── deck-exporter/                # [processors] process/*.md -> one self-contained HTML deck
│   ├── latex-exporter/               # [processors] merges process/ Markdown + process/figures/
│   │                                 # into one compilable .tex
│   ├── literature-retriever/         # [ingest]    arXiv keyword search to JSON
│   ├── longitudinal-analysis/        # [gates]     time-series OLS plus R-backed LMM (lme4),
│   │                                 # mediation (lavaan), sensitivity analysis;
│   │                                 # pure-Python steps without Rscript
│   ├── ml-auditor/                   # [gates]     data-leakage and label-error audit with
│   │                                 # scikit-learn (cleanlab optional); sandboxed
│   ├── multi-dim-manager/            # [workspace] parameter-space expansion, SHA-256 snapshots,
│   │                                 # hash audit logs, rollback to any past round
│   ├── quantitative-validator/       # [gates]     atom conservation for molecular formulae and
│   │                                 # chemical equations (Hill-notation grammar + rdkit
│   │                                 # cross-check); sandboxed
│   ├── reference-auditor/            # [gates]     DOI extraction + Crossref verification;
│   │                                 # a fake DOI fails the gate
│   ├── repro-bundler/                # [processors] deterministic result bundle
│   │                                 # (files + gates + skill versions), and a
│   │                                 # non-extracting verifier that refuses
│   │                                 # escaping entries
│   ├── secret-gate/                  # [gates] credentials by shape, reported by fingerprint
│   ├── schema-gate/                  # [gates]     declared column contract for CSV/JSON;
│   │                                 # an unsupported keyword degrades to UNVERIFIED
│   ├── sci-visualizer/               # [generation] publication-quality charts (matplotlib +
│   │                                 # seaborn + pandas), incl. AMOS-style SEM path renderer,
│   │                                 # plus gif frame scan
│   ├── security-guard/               # [infrastructure] anti-injection text scan +
│   │                                 # AST scan for dangerous call sites
│   ├── task-organizer/               # [workspace] four-zone workspace init, file organization
│   │                                 # (C1–C8 validation, dedupe, snapshots, undo/redo),
│   │                                 # _broadcast/INDEX.md context index
│   ├── test-gate/                    # [gates]     runs the declared test command as an
│   │                                 # argv list; a green exit code with no test
│   │                                 # collected is UNVERIFIED; sandboxed
│   └── video-tracker/                # [ingest]    OpenCV coordinate extraction (CSRT/Template),
│                                     # FFT spectrum, physics probes
├── tests/                            # root suite (662 tests); each skill also ships skills/<skill>/tests/
└── THIRD_PARTY_LICENSES.txt          # upstream licence inventory
```

---
