# Chelate v1.1.0 — Old-Version Capability Checklist (Pre-Migration Audit)

Purpose: enumerate every module and sub-function of the 9 legacy skills BEFORE
rewriting, so the 100%-capability-migration red line can be verified
function-by-function. Source of truth: `chelate-shell-main/skills/` (clean tree,
275 files, all `.py` verified UTF-8 and byte-identical to the intact copies in
the root `skills/`).

Migration scale: **9 skills / 179 Python files / ~35,400 LOC / 97 non-Python
assets** (configs, templates, references, R scripts, fixtures).

---

## 0. Source integrity findings (blocking issues found during audit)

| # | Finding | Impact | Decision |
|---|---------|--------|----------|
| S1 | Root `skills/` has 35 non-UTF8 files, including 8 core sources: `task-organizer/scripts/{init,organize,rotate,index_xlsx}.py`, `task-organizer/scripts/utils/__init__.py`, `multi-dim-manager/scripts/{executor,param_space}.py`, `formula-validator/scripts/core/limits.py`, `conflict-detector/src/{rules,cli}.py`, `capstone-labmate/scripts/{process_cap,draft_report}.py`, `longitudinal-analysis/R/{lmm,mediation}.R` | Root tree unusable as migration source | Use `chelate-shell-main/skills/` (clean; all `.py` sizes match root's intact files) |
| S2 | `chelate-shell-v1.1.0/` partial build has 7 encrypted files: `core/router.py` + 5 skill `run.py` (data-profiler, document-evolution-tracker, formula-validator, fulltext-extractor, literature-retriever, longitudinal-analysis) | Previous attempt unusable | Rebuild router + all 14 skills from scratch; keep clean `core/registry.py`, `core/sandbox.py`, `contracts/*`, `bootstrap.py`, `cli.py` |
| S3 | `chelate-shell-v1.0.0/` uses namespaced layout (`skills/ai-cs/...`, `skills/literature/...`) and 8 encrypted files | Violates v1.1.0 flat-layout red line | Not used as source; superseded by clean tree |
| S4 | Root `skills/` per-skill `README.md` / `README_zh.md` exist only in root (encrypted) and are absent from clean tree | Docs loss | SKILL.md (clean) is the authoritative per-skill doc; READMEs regenerated in English per project convention |

---

## 1. task-organizer (infrastructure) — 41 py files / 15,401 LOC

Legacy entry: `python -m scripts.run` (run.py:837). Four-zone workspace
(`material/initial`, `material/downloaded`, `process/`, `results/`,
`_broadcast/`), provenance filing, 8-check verification with auto-rollback,
read-only broadcast index.

| Module | Key functions / classes (must all migrate) |
|--------|---------------------------------------------|
| `scripts/run.py` | `PipelineResult`, `run`, `_rotate`, `init_folder`, `index_only`, `snapshot_only`, `mark_downloaded`, `mark_user`, `undo`, `redo`, `dedupe_action`, `broadcast_only`, `run_from_cli` |
| `scripts/broadcast.py` | `BroadcastResult`, `local_summary`, `_zh_ngrams`, `_extend_zh_word`, `local_keywords`, `_iter_indexable`, `_scan_entries`, `_md_inline`, `_render_md`, `_render_json`, `broadcast` |
| `scripts/rules.py` | `Rules`, `builtin_rules`, mini-YAML parser (`_mini_yaml_load`, `_parse_mapping`, `_parse_list`, `_parse_block`, `_parse_scalar*`, `_strip_comment`, `_parse_inline_list`), `load_rules`, `available_profiles`, `profile_names`, `_select_profile`, `target_for` |
| `scripts/organize.py` | file-placement engine (94 lines; full body migrates) |
| `scripts/init.py` | four-zone structure builder (55 lines) |
| `scripts/verify.py` | `Check`, `VerifyResult`, C1–C8 checks (`_run_c1`..`_run_c8`), `verify`, `_write_report`, `load_report` |
| `scripts/rollback.py` | `RollbackResult`, `_reverse_moves`, `_suffixed_source`, `_created_dirs_under`, `_remove_created_dirs`, `_purge_generated_files`, `_seal_log`, `rollback`, `_reconstruct_session` |
| `scripts/snapshot.py` | `SnapshotFile`, `Snapshot`, `make_snapshot`, `_build`, `load_snapshot`, `find_latest_snapshot`, `snapshot_file_names`, `build_verification_inputs` |
| `scripts/scan.py` | `FileRecord`, `ScanResult`, `_is_hidden`, `_stat_safe`, `_classify`, `_collect`, `iter_records`, `scan` |
| `scripts/sources.py` | `SourceEntry`, `SourceManifest`, `manifest_path`, `is_manifest` |
| `scripts/dedupe.py` | `DuplicateReport`, `DedupeResult`, `_candidate_files`, `_first_1kb_hash`, `_similarity`, `find_duplicates`, `write_report`, `_quarantine_move`, `run_dedupe`, `run_dedupe_verified` |
| `scripts/history.py` | `HistoryAction`, `History`, `HistoryResult`, `write_history`, `_apply_directions`, `undo`, `redo`, `latest_history` |
| `scripts/doctor.py` | `DoctorResult`, `_loose_root_files`, `_newest_source_mtime`, `_broadcast_fresh`, `doctor`, `doctor_summary_lines` |
| `scripts/hashcache.py` | `CacheEntry`, `HashCache`, `cache_path` |
| `scripts/index_md.py` | `IndexRow`, `_classify_path`, `_type_label`, `_remark_for`, `build_rows`, `_markdown_table`, `write_index_md`, `load_rows_from_md` |
| `scripts/index_xlsx.py` | Excel index writer (openpyxl, optional dep) |
| `scripts/text_extract.py` | `is_supported`, `extract_text`, enc sniffing, plain/srt/vtt/docx/pptx/xlsx(3-tier)/pdf(4-tier: pdfminer→pypdf2→stdlib operator scan), `pdf_page_count`, `json_summary_of` |
| `scripts/rotate.py` | log rotation |
| `scripts/utils/` | `OrganizeSession` + helpers (`utils/__init__.py`), `logger.py` (`setup_logging`, `debug/info/warning/error`, `reset`) |
| assets | `index-template.md`, `verification-report-template.md`, `.task-organizer.yml.example` |

Spec-mandated minimums (`init` / `organize` / `broadcast`) are a SUBSET of the
above — everything else migrates too.

---

## 2. multi-dim-manager (infrastructure) — 27 py files / 2,305 LOC

Legacy entry: `python -m scripts.run`. Cartesian parameter expansion, SHA-256
snapshots, hash audit log, non-destructive rollback.

| Module | Key functions / classes |
|--------|--------------------------|
| `scripts/run.py` | `_output_paths`, `_summarize`, `cmd_run`, `cmd_dryrun`, `cmd_rollback`, `cmd_summary`, `cmd_verify`, `build_parser`, `main` |
| `scripts/param_space.py` | Cartesian expansion (18 lines) |
| `scripts/snapshot.py` | `Manifest`, `_store` (SHA-256 content store), `snapshot`, `restore` |
| `scripts/audit.py` | `RoundRecord`, `AuditLog`, `write_metadata` |
| `scripts/executor.py` | `ExecutionResult`, plugin contract runner ({PARAMS}/{OUT} substitution, exit-code semantics 0/1/2) |
| `scripts/rollback.py` | `rollback_to` (snapshot-based safe rollback) |
| `scripts/verify.py` | `VerifyResult`, `verify_round` |
| `scripts/aggregator.py` | `Summary`, `aggregate`, `write_csv` |
| `scripts/report.py` | `_table`, `write_markdown`, `write_draft` |
| `scripts/config.py` | `Config`, `load_config` |
| `scripts/common.py` | `sha256`, `now_iso` |
| `scripts/errors.py` | `ManagerError`, `ConfigError`, `PluginError`, `RollbackError` |
| `sample_plugin.py` | reference compute plugin (contract example) |

---

## 3. document-evolution-tracker (infrastructure) — 13 py files / 1,146 LOC

Legacy entry: `python -m src.cli`. Version-family diff + concept lineage.

| Module | Key functions / classes |
|--------|--------------------------|
| `src/tracker.py` | `EvolutionResult`, `track_evolution`, `run_config` |
| `src/versioning.py` | `Version`, `discover_versions` |
| `src/diff_blocks.py` | `Change`, `BlockDiff`, `split_blocks` (paragraph/line/sentence), `diff_blocks`, `_normalize` |
| `src/lineage.py` | `LineageNode`, `build_lineage` (introduced/retained/modified/dropped), `_detect_headings` |
| `src/align.py` | `align_versions` |
| `src/config.py` | `Granularity`, `EvoConfig`, `load_config` |
| `src/report.py` | `render_timeline_markdown`, `render_timeline_json`, `write_timeline` |
| `src/cli.py` | `build_parser`, `main` |

---

## 4. capstone-labmate (ingest) — 10 py files / 2,567 LOC

Legacy entries: `scripts/preconfigure_cap.py`, `scripts/process_cap.py`,
`scripts/draft_report.py`. 4-phase workflow (A pre-config, B manual collection,
C down-sample, D draft). R-01..R-05 guardrails; R-02 mandatory watermark.

| Module | Key functions / classes |
|--------|--------------------------|
| `scripts/_capx.py` | `DataSetRecord`, `ProbeReport`, `is_zip`, `open_cap_zip`, `parse_main_xml`, `extract_datasets`, `read_tmp_values` (12-byte record layout), `build_time_axis`, `extract_document_text`, `load_config`, `json_dumps` |
| `scripts/formula_ast.py` | Capstone formula AST: `_tokenize`, `_Node`, `_Parser`, `build_ast`, `render_expression`, `_unit_for`, `_xml_escape` (includes the Type=27 bare-leaf fix from the blackbody lab2.cap crash) |
| `scripts/preconfigure_cap.py` | `_profile_signature`, `_doc_matches`, `_inject_sampling_rate`, `_inject_calculation_columns`, `_inject_columns`, `_inject_graph`, `_blank_base_xml`, `_build_cap`, `run`, `main` |
| `scripts/process_cap.py` | Stage C: probe → decode → time axis → mean-segmentation down-sample → `summary.json` + `manifest.json` + CSV + PNG |
| `scripts/draft_report.py` | Stage D: `_apply_watermark` (R-02, idempotent), randomized error-corpus sampling, `main` |
| config/templates | `error_corpus.json`, `sampling_profiles.json`, `analysis_draft.md`, `lab_report_template.md`, `blank.base.cap` |

---

## 5. video-tracker (ingest) — 19 py files / 3,914 LOC

Legacy entry: `python -m scripts.run` (probe/track/fft/physics/report/demo).
OpenCV tracking, FFT spectra, physics consistency probes.

| Module | Key functions / classes |
|--------|--------------------------|
| `scripts/tracker.py` | `TrajectoryPoint`, `ObjectResult`, `_require_cv2`, `_gray_enhance`, `_color_enhance`, `_parabolic_offset`, `_optical_flow_predict`, `_BaseTracker`, `_CSRTTracker`, `_TemplateTracker`, `create_tracker`, `track_video`, `roi_in_bounds` |
| `scripts/fft_analyzer.py` | `SpectrumResult`, `ObjectAnalysis`, `compute_spectrum` (dominant peak/period/top-N), `analyze_object`, `write_spectra` |
| `scripts/physics.py` | `_central_diff`, `_cv`, `teleport_metric`, `fit_sinusoid`, `fit_poly2`, `fit_damped`, `fit_spiral_recon`, `eom_dynamical_score`, `fit_reconstruct`, `conservation_score`, `PhysicsReport`, `score_trajectory`, `compare_trajectories`, `object_physics` |
| `scripts/data_export.py` | `write_csv`, `write_summary`, `write_batch_summary`, `load_summary`, `load_csv_rows` |
| `scripts/report.py` | `write_report`, `write_report_from_files` |
| `scripts/config.py` | `TrackerParams`, `ObjectROI`, `Config`, `load_config`, `_parse_frame_range` |
| `scripts/errors.py` | `TrackerError`, `ConfigError`, `VideoError`, `TrackingError`, `FFTError` |
| `scripts/run.py` | `_build_parser`, `_probe`, `cmd_probe/track/fft/physics/report/demo`, `main` |
| assets | `demo_fft.json`, `demo_summary.json`, `demo_tracking.csv`, `config.yaml` |

---

## 6. longitudinal-analysis (gates) — 19 py files / 1,429 LOC + 2 R scripts

Legacy entry: `python -m src.cli`. OLS descriptive + LMM/mediation/sensitivity
via R (lme4/lavaan), graceful degradation when Rscript absent.

| Module | Key functions / classes |
|--------|--------------------------|
| `src/pipeline.py` | `run_step`, `run_pipeline` |
| `src/steps/descriptive.py` | `_tidy_group_agg`, `run` (time-series OLS) |
| `src/steps/lmm.py` | `run` → `R/lmm.R` (lme4) |
| `src/steps/mediation.py` | `_build_lagged`, `run` → `R/mediation.R` (lavaan bootstrap) |
| `src/steps/sensitivity.py` | `run` → `R/lmm.R` |
| `src/steps/manipulation.py` | `run` (statsmodels/scipy) |
| `src/r_runner.py` | `RNotAvailableError`, `PluginResult`, `has_rscript`, `run_r` |
| `src/audit.py` | `now_iso`, `hash_payload`, `set_seed`, `log_step`, `read_audit_log` |
| `src/config.py` | `Step`, `AnalysisConfig`, `_parse_steps`, `load_config` |
| `src/cli.py` | `build_parser`, `_only_step`, `main` |
| `R/lmm.R`, `R/mediation.R` | R back-ends (lme4 / lavaan) |
| fixtures | `fixture_panel.csv`, `behavior_2x2x2.yaml` |

---

## 7. formula-validator (gates) — 28 py files / 5,348 LOC

Legacy entry: `python scripts/cli.py`. Five CAS layers: parse (D1/D2),
dimension (D3-limit enumeration), numeric (D4 Monte Carlo), symbolic (D5
high-precision proof), matrix properties. pint merge is a v1.1.0 ADDITION.

| Module | Key functions / classes |
|--------|--------------------------|
| `scripts/core/parsing.py` | LaTeX-ish → SymPy: `_take_group`, `_frac`, `_needs_mul`, `_convert`, `_read_env`, `_matrix_literal`, `_sympify`, `parse_expr`, `parse_equation` |
| `scripts/core/dimensions.py` | `analyse`, `check_equation`, `_walk`, `_dim_of_unit_string`, `_build_resolver`, `_collect_names` |
| `scripts/core/limits.py` | `enumerate_limits` (D3), `find_singularities` |
| `scripts/core/numeric.py` | `LambdifyError`, `sort_symbols`, `sample_values`, `_compile`, `_evaluate`, `monte_carlo` (D4), `_hp_agree` |
| `scripts/core/symbolic.py` | `_zero_test`, `high_precision_check`, `prove_identity` (D5) |
| `scripts/core/matrixprops.py` | `parse_matrix`, `_numeric_zero`, `_check_one`, `check_matrix` |
| `scripts/core/breakpoint.py` | `_difference_text`, `diagnose`, `locate_breakpoint` |
| `scripts/core/pipeline.py` | `validate_equation`, `inspect_expression`, `summarize` |
| `scripts/core/report.py` | `render` (+ section builders) |
| `scripts/core/registry.py` | `dim`, `describe_dimension`, `UnitParseError` |
| `scripts/core/errors.py` | `FVError`, `ParseError`, `DimensionError`, `UnsupportedConstruct` |
| `scripts/cli.py` | `cmd_validate/check/derive/matrix`, `build_parser`, `main`, exit codes 0-4 |
| `mcp_server/server.py` | MCP adapter (optional surface) |

---

## 8. ai-trace-remover (processors) — 8 py files / 1,041 LOC

Legacy entry: `python -m src.cli`. EN lexicon already clean-room (module
docstring: "Original category design and regex, authored for this skill. No
external text is copied"), 30 ENPattern entries E1–E24; ZH lexicon + scoring
rubric preserved verbatim.

| Module | Key functions / classes |
|--------|--------------------------|
| `src/core/engine.py` | `Hit`, `TraceReport`, `_detect_language`, `_line_col`, `_region`, `_scan_zh_patterns`, `_scan_en_patterns`, `_structural_deduction`, `_hard_bans`, `_zh_deduction`, `_en_ai_taste`, `grade_zh`, `grade_en`, `build_suggestions`, `scan` |
| `src/core/patterns_zh.py` | ZH pattern table (153 lines) |
| `src/core/patterns_en.py` | EN pattern table (clean-room, 30 entries) |
| `src/core/hard_bans.py` | `HardBan`, `compiled`, `blocking_codes` |
| `src/core/sound_rules.py` | `SoundRule`, `check_sound` (Sound-5) |
| `src/cli.py` | `_render_md`, `_render_json`, `build_parser`, `main` |
| references | `ai-patterns-en.md`, `ai-patterns-zh.md`, `scoring-rubric.md`, `revision.md`, `example-diff.md` |

---

## 9. conflict-detector (gates) — 14 py files / 1,233 LOC

Legacy entry: `python -m src.cli`. Plugin-style rule engine + numeric
hard-check via regex extraction.

| Module | Key functions / classes |
|--------|--------------------------|
| `src/detector.py` | `DetectionResult`, `detect_conflicts`, `run_config` |
| `src/extract.py` | `Fact`, `_facts_from_json`, `_facts_from_text`, `extract_facts` |
| `src/detect.py` | `Conflict`, `NumericClaim`, `detect_numeric_mismatch`, `detect_interval_overlap`, `detect_boolean_conflict`, `detect_categorical_mismatch` |
| `src/rules.py` | rule registry (plugin loading) |
| `src/normalize.py` | `Normaliser`, `normalize_key`, `normalize_value` |
| `src/config.py` | `DocumentSource`, `ConflictDetectorConfig`, `load_config` |
| `src/report.py` | `render_json`, `render_csv`, `render_markdown`, `write_report` |
| `src/cli.py` | CLI entry |

---

## 10. New skills (5) — written from scratch, closed loop required

| Skill | Stage | Library | Contract |
|-------|-------|---------|----------|
| `fulltext-extractor` | ingest | PyMuPDF (`fitz`) | PDF → text → `process/`; degrades to UNVERIFIED without PyMuPDF |
| `literature-retriever` | ingest | `arxiv` | keywords → title/abstract JSON → `process/`; offline → UNVERIFIED |
| `bibtex-normalizer` | ingest | `bibtexparser` | `.bib` → dedupe → standard-format output |
| `reference-auditor` | gates | `requests` | DOI regex → Crossref API → missing ⇒ **FAIL** gate |
| `data-profiler` | gates | `pandas` | CSV → rows / missing / outlier ratio |

Online implementations to be referenced (NOT copied — clean-room per project
rules): PyMuPDF docs, arxiv API examples, bibtexparser docs, Crossref REST API
docs, pandas profiling recipes.

---

## 11. Migration rules (binding)

1. Every module + function listed above migrates 1:1 — no simplification, no
   "minimal viable" cuts (red line 3).
2. Internal package layout inside each skill directory is preserved verbatim
   (so `from scripts.core import ...`, `_SKILL_ROOT / "R" / "lmm.R"`, template
   and reference paths keep working).
3. Each skill gets a NEW adapter `scripts/run.py`: unified router contract
   (`--root`, `--action`, gate_result output) that imports the legacy modules
   in-process — legacy CLIs remain directly runnable.
4. Skills sit flat in `skills/` — no `namespaces/`, no `03_gates/` (red line 1).
5. No `TODO` / `pass` stubs anywhere (red line 2).
6. Engineering docs/code in English; Chinese only in user-facing summaries.
