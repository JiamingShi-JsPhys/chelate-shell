# Changelog

All notable changes to Chelate Shell are documented in this file.

## [1.3.3] — 2026-11-14

A safety release: the pipeline's one irreversible write now needs an approval a
human issued for that exact plan, and every workspace write is checked to stay
inside the workspace.

### Added
- **One-time approval before promotion.** `router.promote()` turns provisional
  `process/` intermediates into `results/` deliverables; it now requires a
  token from `cli.py approve`, bound to the action, the resolved workspace,
  the mode/selection and the SHA-256 of every input file, with a 15-minute
  expiry and an HMAC-SHA256 signature. Spending is atomic
  (`O_CREAT|O_EXCL`), so a token cannot be replayed. Without a valid token the
  run still completes — the agent's attempts stay visible in `process/` — but
  it records `"blocked": "approval"` and the pipeline writes nothing to
  `results/`.
- **Issuing a token needs a person, not just a terminal.**
  `cli.py approve` asks the operator to type `approve promote` and treats EOF
  or any other answer as a refusal; `--no-approval` goes through the same
  check. `CHELATE_HUMAN=1` is the declared hatch for CI. This release measured
  why a TTY check alone was not enough: under an agent harness a spawned
  subprocess inherits the parent's terminal, so `isatty()` is `True` for a
  shell an agent drives.
- **The signing key moved out of the workspace** to
  `%LOCALAPPDATA%\chelate\keys\` (or `$XDG_DATA_HOME/chelate/keys/`), because
  the workspace is the directory the agent is allowed to write. Tokens stay in
  `<ws>/.chelate/approvals/` where a human can see what was issued.
- **`lib/chelate_core/paths.ensure_within()`** — a realpath-resolved
  containment check, applied to every workspace directory the shell creates,
  to the promotion target and to the output flags the adapter injects, so
  `--output ../../etc` and outward-pointing symlinks are refused before the
  write happens.
- **`tests/attacks/`** — the two probes behind the safety claims ship with the
  repository instead of living in the author's scratch folder:
  `self_approve.py` runs six agent-posture trials against the approval gate
  (three self-approval routes, plus the two boundary probes), and
  `tty_probe.py` drives the same approval through a real Windows console with
  `WriteConsoleInputW`. Both are standard library only, take under a minute,
  and write scratch workspaces to a temp directory, so neither leaves residue
  in the tree it tests.
- **`docs/SAFETY.md`** — the threat model, the control list, the adversarial
  matrix and the limitations stated plainly: this is a policy layer, not OS
  containment. It records the measured residual too — once a human has
  approved in a workspace the key persists, and a process running as the same
  user can read it and sign its own token.
- **Workspace rule files from `init`.** A host loads a plugin's *skills*, not
  its `AGENTS.md`, and a skill's `SKILL.md` is loaded only when that skill is
  invoked — so "just write this file into results/" reached no instruction at
  all in testing. `task-organizer init` now writes `AGENTS.md` and
  `CLAUDE.md` at the workspace root (never overwriting an existing one, never
  treating them as material to lift), which is the file a host actually reads.
  Measured in ZCode: with the file present the model refused a direct write
  into `results/` and named the rule; without it, it wrote.
- **The promotion log and `cli.py audit`.** Testing the plugin from a real
  agent session (ZCode) found a route the token layer cannot close: asked to
  promote, the agent skipped `cli.py pipeline` entirely and copied its profile
  straight into `results/` with its file tool. No token, no gate, no pipeline
  report. `promote()` now appends `results/.promotions.jsonl` — the token
  nonce that authorised it and a SHA-256 for every file it copied — and
  `python cli.py audit --root <ws>` reports `unapproved` (files no promotion
  accounts for) and `modified` (promoted files changed afterwards), exiting 1
  when either is non-empty. Every pipeline report carries the same dict as
  `results_audit`. This does not prevent the write — nothing in-process can on
  a filesystem the user can write — it makes the write visible and auditable.
  Probing the detector itself then closed three of its own holes: each entry
  is HMAC-signed with the workspace key (so a hand-written line does not
  verify, and an unverifiable one is reported under `tampered`), a corrupt
  line is reported instead of raising, and the report exemption now checks
  the file's shape as well as its name, so a deliverable renamed
  `pipeline_report_*.json` is still named. A log whose key cannot be found
  fails closed: signed entries are reported as unverified rather than trusted,
  so losing the key cannot quietly downgrade the audit.

### Fixed
- **A failed gate from an earlier run could still be promoted.** A manuscript
  driven end to end exposed it: `reference-auditor` failed on a DOI that does
  not exist, then a later `--mode a` run — which plans only the ingest stage —
  promoted `process/` and carried the `FAIL` gate into `results/`, reporting
  `promoted: true` and a clean audit. `promote()` now reads
  `process/gates/` and refuses while the newest gate for any skill is a
  `FAIL`; re-running that skill writes a newer gate and clears the lock, and
  the approval token is left unspent while the lock stands.
- **A withheld promotion exited 0.** `cli.py pipeline` printed
  `"blocked": "approval"`, wrote its report and told the caller nothing —
  the exit status said success, while `docs/SAFETY.md` said the process
  exits non-zero. Both entry points now return 1 for a withheld promotion,
  so a caller that only reads the status cannot mistake a refusal for a
  completed run.
- **An unknown `--selected` name was a silent success.** A typo, or an agent
  naming a skill it invented, narrowed the plan to nothing and finished with
  exit 0 and no work done. It is now reported as
  `"error": "unknown skill(s) in --selected: ...; known: ..."` and exits 1.
  An empty plan that comes from inputs nothing consumes still carries the
  `note` and exits 0, because that request did run — there was nothing to do.
- **Three routes let an agent approve itself.** Measured against this
  release's approval layer before it was hardened, all three promoted
  successfully: appending `--no-approval`, calling `approval.issue()` from the
  agent's own process, and forging a key plus token inside the workspace. All
  three now fail; the trials and their output are kept with the release notes
  rather than only asserted in tests.
- **Sandboxed skills were handed the repository root instead of the
  workspace.** `router.run_skill()` passed `_REPO_ROOT` to
  `run_skill_sandboxed()`, so a sandboxed skill wrote its gate into the source
  tree rather than the workspace the user named.
- **`python core/router.py` could not start.** The parser was built with
  `argparse.ArgumentParser(pro=...)`, which is not a parameter; the typo
  shipped in 1.3.2 and is fixed here.
- **The task-organizer AI call would send its key to a plaintext remote host.**
  `TASK_ORG_AI_BASE_URL` decides where the request goes and the request
  carries `Authorization: Bearer <key>`, so `http://` to anything but loopback
  put the key on the wire in clear text. `_key_safe_base_url()` now accepts
  https anywhere, plaintext http only to `localhost`/`127.0.0.0/8`/`::1`, and
  refuses URLs with embedded credentials. Any OpenAI-compatible endpoint —
  DeepSeek, Qwen, Moonshot, vLLM, Ollama — still works; what stops working is
  a remote endpoint over unencrypted http.

### Removed
- **`capstone-labmate`**, in full. Its bundled `assets/blank.base.cap` was a
  template saved by PASCO's Capstone (root element `DSProExperiment`,
  `Version="2.12.2"`), so every release since v1.3.0 was redistributing a
  vendor-produced artifact. The scan of that file found no credentials,
  paths, serials or personal data — 50 format GUIDs and nothing else — so the
  objection is distribution, not leakage. The skill's own generator
  (`_blank_base_xml()`) can build a skeleton, but the capability is being
  reissued separately rather than shipped under a third-party trademark.
  Also removed: the trademark notice in both READMEs, the PASCO rows in the
  dependency matrix and the reference trees, the ingest entry in the plan
  diagram, and the tests that pinned the skill's modules. Skill count 20 → 19.

### Changed
- **Promotion requires approval by default.** Skipping the token at all needs
  a human channel (a terminal plus the typed phrase, or `CHELATE_HUMAN=1`), so
  `--no-approval` is no longer reachable by an agent that simply appends it.

## [1.3.2] — 2026-11-13

**Security release — upgrade recommended.** Two command-injection paths are
closed, one dependency pointed at a package that does not exist, and the
DeepSec shield audit of the tree reports 0 findings.

### Security (important)
- **`multi-dim-manager` no longer runs the plugin command through a shell.**
  `subprocess.run(..., shell=True)` made every substituted `{PARAMS}` /
  `{OUT}` path shell syntax: a workspace path containing `;` or `$()` ran
  whatever followed it. The template is now split with `shlex` (POSIX rules
  on POSIX, non-POSIX on Windows so `C:\...` keeps its backslashes) and
  passed as an argument list; substitution happens per token, so a path with
  spaces stays one argument. Shell-only syntax (`|`, `&&`, `;`, `>`, ...) is
  refused with an explicit error instead of being silently reinterpreted, and
  `plugin.command` accepts a list, which needs no quoting at all.
- **The sandbox refuses executables that are not on a whitelist.**
  `core/sandbox.py` launched whatever `cmd[0]` named. It now checks the
  program against `ALLOWED_EXECUTABLES` (`python`, `node`, `gcc`, `clang`,
  ...) before a child process is created, and again inside the child. The
  running interpreter is always allowed, so `run_skill_sandboxed` keeps
  working.
- **A required dependency named a package that does not exist.**
  `video-tracker` declared `cv2` — an import name, not a PyPI distribution;
  `pip install cv2` returns 404. It now declares
  `opencv-contrib-python-headless`, which its `requirements.txt` already used.
- **`task-organizer` restricts its AI endpoint to http(s).**
  `TASK_ORG_AI_BASE_URL` comes from the environment and any other scheme is
  now rejected, so a `file://` value cannot turn the chat call into a
  local-file read. `doi_audit` gained the matching host assertion for
  Crossref: the URL is fixed-endpoint plus quoted DOI, and a hijacked host
  now reports `indeterminate` instead of being fetched.

### Fixed
- **The whitelist accepts the interpreter that actually runs the skills.**
  `run_skill_sandboxed` launches `sys.executable` by absolute path, so the
  check compares resolved paths and also accepts versioned names such as
  `python3.12`; a bare `python`/`node`/`gcc` list would have blocked every
  sandboxed skill.

## [1.3.1] — 2026-11-12

A release about the test suite being trustworthy, not about the skills.

### Fixed
- **A fresh clone can run its own suite.** There was no pytest configuration at
  the root, so `pytest` collected `skills/*/tests/` as well as `tests/`. Those
  directories each declare a top-level `tests` package, so the run died during
  collection with `ImportPathMismatchError` — and an early `conftest` import
  resolved to `skills/capstone-labmate/conftest.py` instead of the root one.
  `pytest.ini` now scopes collection to `tests/`, the suite this project
  maintains.
- **Two skill contract tests were pinned to `1.2.0`.** `conflict-detector` and
  `document-evolution-tracker` asserted `__version__ == "1.2.0"` while both
  skills already shipped `1.3.0`. They now compare against the skill's own
  `manifest.json`, so a release bump cannot break them again.
- **`yamlmini` kept inline comments, so `data-profiler` failed its own gate
  whenever PyYAML was absent.** The shipped `assets/config.yaml` writes
  `outlier_fence: 1.5     # Tukey multiplier …`; PyYAML strips the comment,
  the built-in fallback parser did not, and `float()` raised on the whole
  string — the adapter reported FAIL for a config it could not read. The
  fallback now strips a trailing `#` outside quotes. Found by the CI job that
  installs no PyYAML, which is the install a user gets.
- **Five changelog tests demanded CRLF, so Linux CI failed.** `conflict-detector`
  and four others asserted that their `CHANGELOG.md` was CRLF — a property of a
  Windows checkout, not of the file. They now assert that the line endings are
  consistent (all CRLF or all LF), which is the thing the guard was really
  about, and which holds on both platforms.
- **`package.json` shipped the skills without the code they import.** The
  `files` list carried `skills/` and left out `core/`, `lib/`, `bootstrap.py`,
  `cli.py` and `contracts/`, so an npm install produced a tree the registry
  could not start. It now includes them, plus `commands/` and `agents/`.

### Added
- **CI, in three jobs.** `.github/workflows/tests.yml` runs `python -m pytest` on
  every push and pull request against Python 3.10 and 3.12. The `bare` job
  installs pytest and nothing else — the `UNVERIFIED` path is what a fresh
  user gets, so that is the path worth guarding — and the `extras` job
  installs numpy, pandas, scikit-learn, matplotlib, seaborn, sympy, pint,
  pypdf, pdfminer.six, bibtexparser, requests and arxiv, so the PASS paths run
  too.
  `tests/conftest.py` gains `requires()`, the marker a test uses to skip when
  its optional dependency is absent; the 20 tests that assert a real verdict
  (CAS layers, FFT, profiling, PDF/BibTeX parsing) now carry it instead of
  failing. `test_ml_auditor` and `test_sci_visualizer` imported numpy and
  pandas at module scope and now use `pytest.importorskip`, so a bare run
  skips those modules instead of dying during collection. The PDF fixture is
  built by pypdf when pymupdf is absent, and without font metrics pdfminer
  emits one glyph per line, so its assertion now compares with whitespace
  removed. The third job, `per-skill suites`, runs each skill's own
  upstream suite in its own pytest process — they cannot share one, several
  define a top-level `tests` module.

### Changed
- **The README leads with what it does.** A one-line statement, three
  audience bullets, a real `formula-validator` gate output, a 12-row
  "what you can ask for → which skill" table, a single install command, and a
  contents list. The security statement moved to the back, with a one-line
  pointer at the top.
- **The bulk moved to `docs/`.** The 100-line repository tree is now
  `docs/REFERENCE.md`, the pipeline diagram and stage contract
  `docs/ARCHITECTURE.md`, and the test detail `docs/TESTING.md` (each with a
  Chinese twin). The README keeps a short section and a link, the way
  `web-forager` splits its front page from `docs/REFERENCE.md`.
- **Install commands moved to `docs/INSTALL_COMMANDS.md`** (and its Chinese
  twin). The README keeps methods 1 and 3 plus a pointer, so the front page is
  short again.
- **An Acknowledgements section**, with `docs/ACKNOWLEDGEMENTS.md` carrying the
  detail behind each credited report.
- **`3d-modeler`'s audit path is deprecated.** Print-quality verification
  (watertightness, non-manifold edges, normals, physical size) belongs to
  `3d-fabric --action inspect`; `3d-modeler` still audits, but says so in
  its gate reason and raises a `DeprecationWarning`.

## [1.3.0] — 2026-11-06

### Skill tree flattened to one level

- **All 20 skills now live directly under `skills/`.** The six numbered
  category folders (`01_infrastructure` … `06_domain-extensions`) and their
  `.gitkeep` placeholders are gone. A skill's category is carried by the
  manifest `stage` field, not by its path, so nothing about routing changed.
- **`core/registry.py` accepts exactly one level** (`skills/<skill>/manifest.json`)
  and records anything deeper as an error instead of loading it. The previous
  rule allowed depth 2, which is what let a skill be visible to the registry
  and invisible to the host scanners at the same time.
- **Adapters no longer assume a fixed depth.** `sci-visualizer` and
  `3d-modeler` walked up a hard-coded number of parents to find the repo root;
  both now walk up until they find `lib/chelate_core/`, so a skill can move
  without breaking its imports.

### Skill restructuring (19 → 20 skills)

- **Merged `figure-generator` into `sci-visualizer`.** The figure engine
  (`scripts/engine.py`, matplotlib/seaborn/pandas, plus the AMOS-style SEM
  path-diagram renderer) is now co-located under
  `skills/sci-visualizer/scripts/` and imported in-process by `run.py`. The
  standalone `figure-generator` skill is removed from the routing table.
  `sci-visualizer` declares `matplotlib` / `seaborn` / `pandas` as manifest
  dependencies; missing libraries degrade the gate to `UNVERIFIED`, never a
  crash.
- **Removed `sem-copilot` from the core skill set.** The SEM / AMOS
  replacement module has been extracted as an independent standalone plugin:
  `https://github.com/JiamingShi-JsPhys/sem-copilot`.
- **Restored three skills** (bumped to 1.3.0, re-joined the routing table and
  routing tests):
  - `multi-dim-manager` (workspace) — parameter-space expansion, SHA-256
    snapshots, hash audit logs, safe rollback.
  - `longitudinal-analysis` (gates) — time-series OLS plus R-backed LMM
    (lme4), mediation (lavaan) and sensitivity analysis; degrades to
    pure-Python steps when Rscript is absent.
  - `ai-trace-remover` (processors) — template-sentence removal and a 0–100
    "AI-likeness" score.
- **Three category meta-skills** — `security-guard` (infrastructure),
  `sci-visualizer` (generation) and `3d-modeler` (domain_extensions) — flat
  like every other skill, with the category in the manifest `stage` field.

### Added

- **Security shield** (`core/security_shield.py`) — pre-dispatch injection
  scan wired into `core/router.py`: every text input is screened against a set
  of known prompt-injection patterns before any skill subprocess is spawned. A
  hit writes a FAIL gate under `process/gates/` and terminates the pipeline.
- **Subagent manager** (`core/subagent_manager.py`) — discovers `agents/`,
  enforces a skill whitelist and a writable-path whitelist (fail-closed), and
  exposes `load_default_manager` for the Router.
- **Two sub-agents** — `spatial_agent` (3D content: image-to-3D, video-to-3D,
  scene composition, mesh QC; may call `3d-modeler`, `sci-visualizer`,
  `security-guard`) and `visual_agent` (publication visuals, figure QA, LaTeX
  export; may call `sci-visualizer`, `latex-exporter`, `security-guard`). Both
  are sandboxed, capped by `timeout_seconds` and `max_steps`, and may write
  only under `assets/`, `process/` and `results/`.
- **Two slash commands** — `/chelate-shell:figure` and
  `/chelate-shell:model3d` — that put the heavier engines (matplotlib/seaborn,
  the OBJ mesh builder) behind a single line.
- `sem-copilot-output/` added to `.gitignore`; pytest `tmp*/` work directories
  ignored as well.

### Changed

- **The README quick start is now slash-first.** Both READMEs open the section
  with `/chelate-shell:<skill>` examples, document the two new commands and the
  two new sub-agents, and leave the CLI flags, pipeline modes and debugging
  switches to `ORCHESTRATOR.md` §5.
- **The pipeline diagram is horizontal** (`flowchart LR`) in `README.md`,
  `README_zh.md` and `ORCHESTRATOR.md`, keeping the whole flow on one band
  instead of a tall column.
- All 20 `SKILL.md` files were rewritten to one structure: what the skill does,
  when it fires, a `Quick Execution` block, and its limits. `task-organizer`
  alone drops over 1000 lines; no behaviour changed.

### Performance

- `core/registry.py`: in-process memo on `load_default_registry()` keyed on
  per-manifest mtime + size, so a second call within the same CLI process
  (the subagent-manager dispatch fallback path) reuses the parsed Registry
  when nothing on disk has changed.

### Tests

- `tests/test_registry.py::test_physical_flatness_no_nested_manifests` now
  asserts depth **1**, and a new
  `test_registry_rejects_a_nested_manifest` proves a manifest one level deeper
  is reported rather than loaded.
- `tests/conftest.py` — `skill_root()` resolves the flat layout only.
- `tests/test_plugin_manifests.py`, `tests/test_repo_consistency.py`,
  `tests/test_no_stubs.py`, `tests/test_sci_visualizer.py` — nested-path
  resolution and the comments describing it removed.
- `tests/test_sci_visualizer.py` replaces `tests/test_figure_generator.py`.
- `tests/test_subagent_manager.py` asserts
  `mgr.names() == {"spatial_agent", "visual_agent"}`.
- The suite collects **357 tests (347 passed, 10 skipped** — dependency- or
  fixture-gated, not failures).

### Fixed

- **`security-guard` no longer reports a PASS for an input it never read.**
  The adapter treated any `--input` that did not resolve to an existing file as
  inline text, so `--input draft.md` with a typo'd path scanned the *string*
  `"draft.md"` and returned `PASS` — a security gate claiming a file was
  checked when nothing was read. The adapter now distinguishes a path from a
  payload (separator, leading `.`/`~`, or a known document extension), resolves
  relative paths against `--root`, and exits `2` with `input file not found`
  for a missing file. A run with no `--input` still passes through, which the
  generic smoke run requires.
- **Distribution names are mapped to import names before probing.**
  `scikit-learn` → `sklearn`, `opencv-python` → `cv2`, `pillow` → `PIL`,
  `pyyaml` → `yaml` and friends, so an installed package no longer reads as
  missing. A probe that raises now counts as missing instead of crashing.
- **`reference-auditor` degrades instead of failing** when no draft is
  supplied, and a `ValueError` inside the auditor is treated as degraded.
- **`formula-validator` no longer reports a false mismatch** when a
  conditional limit evaluates to NaN; the verdict becomes inconclusive.
- **`adapter.py` reports the missing required argument** instead of dumping the
  whole usage block.
- **`tests/test_router.py::test_red_fail_output` no longer fails when
  `NO_COLOR` is exported.**
- **`tests/test_repo_consistency.py` dependency-table checks** follow the
  matrix to its new home, `docs/DEPENDENCIES*.md`.

## [1.2.0] — 2026-10-24

### Added
- **sem-auditor: extended SEM capabilities delegated to semopy.** Six new
  public functions in `scripts/engine.py`, implemented in
  `scripts/sem_extended.py` and backed by semopy (an existing
  dependency), each degrading to an explicit reason string (UNVERIFIED)
  rather than a crash when semopy or the data are unavailable:

  1. `robust_ml` — ML fit with Huber-White-style two-step sandwich
     standard errors on the covariance parameters (the SEs vary across
     parameters; verified not to collapse to a flat 1/sqrt(n)).
  2. `categorical_wlsmv` — threshold-model fit for ordinal indicators:
     polychoric (rank-binned) correlation matrix for transparency; fit
     indices and standard errors taken from the semopy MLE on the binned
     indicators (CFI / TLI / RMSEA + per-indicator SEs).
  3. `mediation_effects` — direct / indirect / total effect
     decomposition: indirect effects are products of fitted path
     coefficients; total = direct + all indirect (asserted numerically
     in `tests/test_sem_extended.py`).
  4. `invariance_test` — nested configural / metric / scalar multi-group
     fits via `semopy.multigroup` with genuinely pinned loadings;
     reports pooled chi-square difference and delta-CFI per level.
  5. `modification_index` — top-k modification indices + expected
     parameter change (EPC) from the model-implied covariance.
  6. `bootstrap_ci` — percentile bootstrap CIs on the '~' path
     coefficients; the requested `n_bootstrap` is echoed back and
     `samples_used` reports how many refits actually converged.

- **Numerical regression tests** (`tests/test_sem_extended.py`, 20
  cases): every capability above is asserted against a trusted reference
  with tight tolerances (mediation product rule ±5%, bootstrap count
  echo, invariance delta on divergent vs. matched groups, SE
  non-degeneracy), plus regression tests that specifically fail the
  previously broken behaviour (flat-SE robust ML, always-invariant
  multi-group, silently capped bootstrap).

### Fixed
- Reverted the broken clean-room numerics from the earlier sem-extension
  pass (degenerate WLSMV CFI/TLI, fraudulent always-invariant multi-group
  test, 1/sqrt(n) "robust" SEs, silently capped bootstrap): `sem_fit.py`
  is byte-identical to the v1.2.0 baseline; the heavy estimation is now
  delegated to semopy instead of hand-rolled numpy.

- **sem-auditor docs**: the "replaces AMOS" overclaim is removed from
  `SKILL.md` and `skills/sem-auditor/README.md`; the `manifest.json`
  description reflects the capabilities actually implemented.

### Changed
- **Version unified to 1.2.0 everywhere.** Every project version declaration
  now reads `1.2.0`: all 18 skill `manifest.json` files, all 18 `SKILL.md`
  frontmatter blocks, all four `.claude-plugin/` / `.codebuddy-plugin/` /
  `.codex-plugin/` / `.dsh-plugin/` manifests, root `package.json`, and the
  per-skill packaging files that previously still carried `1.0.0` /
  `1.0.0-beta` (`pyproject.toml`, `capstone-labmate/skill.json`,
  `config/schema.yaml`, `config/examples/family.json`). XML declarations
  (`<?xml version="1.0"?>`) and test-internal fixtures are data, not product
  versions, and were deliberately left alone.
- **Audit follow-up (2026-10-25): version unification completed.** A re-audit
  found surfaces the first pass had not walked: `__version__` in four skill
  `scripts/__init__.py` files (still `1.0.1` / `0.0.0`), five `CITATION.cff`
  `version:` fields (`1.0.0`), two `config/examples/` schema versions
  (`1.0.0`), a stale manifest example in `docs/CONSTRUCTION_PLAN.md`
  (`1.1.0`), and two live version strings in `lib/chelate_core/` (the Crossref
  user agent `chelate-shell/1.1.0` and the `.bib` output header `v1.1.0`). All
  now read `1.2.0`; the seven legacy skills that ship a CHANGELOG each gained
  a `## [1.2.0]` section, and `tests/test_repo_consistency.py` now walks every
  declaration surface (manifests, SKILL.md frontmatter, `__init__.py`,
  CITATION.cff, example configs, dot-plugin manifests, lib strings) so this
  class of drift cannot return.
- **Audit follow-up (2026-10-25, second pass): marketplace manifests.**
  `.claude-plugin/marketplace.json` was the only plugin-manifest surface still
  declaring no version at all. The Claude Code marketplace schema defines a
  `version` field on plugin entries, and the codebuddy / codex manifests have
  carried `1.2.0` since the v1.1.x migration, but both manifest tests only
  checked the field "when present", so the gap never surfaced. The entry now
  reads `1.2.0`, and `test_plugin_manifests.py` / `test_repo_consistency.py`
  require the field instead of tolerating its absence. The same pass removed a
  dangling sentence fragment ("whole pipeline down.") that an earlier edit had
  left in `README.md`.
- **Audit follow-up (2026-10-25, third pass): contact mailbox.** The repo
  carried two spellings of the maintainer address:
  `jiamingshi_git@outlook.com` in both READMEs and nine `AUTHORS.md` files,
  and `jiamingshi_physics@outlook.com` in `capstone-labmate/pyproject.toml`
  (the stale spelling had been there since the v1.0.0 source and was
  faithfully migrated, so the capability guard saw matching bytes on both
  sides). All twelve contact surfaces now read `jiamingshi_git@outlook.com`.
  The capability guard's metadata mask learned a contact-declaration rule (an
  `email` key in a packaging file is metadata, not capability), and
  `test_repo_consistency.py::test_contact_email_is_unified` walks every
  tracked text file so a third spelling cannot return; RFC 2606 placeholder
  addresses and the third-party license inventory stay exempt. The three
  new guard tests also grew the suite from 289 to 292 collected tests, so
  both READMEs' test counts were refreshed to match.
- **Audit follow-up (2026-10-25, fourth pass): all 18 skills proven
  runnable.** Every declared entrypoint answers `--help`; the nine
  skills that ship internal suites were run in place (capstone-labmate
  57, conflict-detector 33, document-evolution-tracker 30,
  longitudinal-analysis 33 green; formula-validator 237 and
  multi-dim-manager / task-organizer / video-tracker functionally green
  with doc-convention failures only — the same class of legacy debt that
  existed in v1.1.2, now one-to-two failures lighter per skill); real
  adapter-level smoke runs (ai-trace-remover scan, task-organizer
  init/doctor, conflict-detector run, capstone-labmate ingest on the
  blank fixture) and a full `cli.py pipeline` run all completed, and the
  capability guard's runtime-output exclusion learned `process/` — the
  formula-validator internal suite writes reports into its own tree
  when run outside the adapter, and `.gitignore` has always declared
  `process/` a runtime artifact.
- **"Pro" branding removed.** The distribution is plain `chelate-shell`
  v1.2.0: no `chelate-shell-pro` identity string, no "Pro" qualifier on the
  release or on the five heavy skills, and no "Pro fork" framing. Technical
  terms that merely contain the letters (Probe, Profile, Process, Programs,
  Promotion, Produce, Protected, Project, Product, Prose, Prompt,
  additionalProperties, and the PASCO `DSProExperiment` XML element) are
  untouched.
- Corrected two stale claims while de-branding: `README.md` asserted that all
  five heavy skills set `sandbox_required: true` (the stdlib-only
  `latex-exporter` does not), and `README.md` carried a stray sentence
  fragment left by an earlier edit.

### Migration guard
- `tests/test_capability_guard.py` now tolerates exactly one kind of change
  in legacy-skill packaging files: the version-declaration line. The new
  `_mask_version_decl` helper blanks only that line, so `versions_dir` /
  `version_naming` keys and dependency pins such as `openpyxl>=3.1.0` stay
  under byte-for-byte comparison. This follows the guard's existing
  precedent for `CHANGELOG.md`, `src/__init__.py` and skill-local tests, and
  is mutation-tested: tampering with any non-version line still fails.

### Added
- **Release identity**: the project ships as `chelate-shell` v1.2.0 (all
  plugin.json, package.json, marketplace.json; version 1.2.0).
- `core/sandbox.py` — true process-level sandbox isolation via `multiprocessing`
  with a 120-second timeout circuit-breaker. A skill that exceeds the limit is
  force-terminated and reported as `UNVERIFIED` with a timeout reason.
  Windows `spawn` mode is handled with an `if __name__ == "__main__"` guard.
- 5 new heavy-gate/processor skills, all shipping a full business
  engine under `scripts/` (`scripts/engine.py` + `scripts/run.py`) and
  wired into the routing table:
  - `quantitative-validator` (gates, `rdkit`, sandbox_required=true) —
    atom conservation for formulae and chemical equations
  - `ml-auditor` (gates, `scikit-learn` + `pandas`; `cleanlab` optional,
    sandbox_required=true) — data-leakage and label-error detection
  - `sem-auditor` (gates, `semopy` + `pandas`, sandbox_required=true)
  - `figure-generator` (processors, `matplotlib` + `seaborn`,
    sandbox_required=true)
  - `latex-exporter` (processors, **standard library only** — no `pandoc`,
    sandbox_required=false) — Markdown + figures merged into one `.tex`
- `tests/test_quantitative.py`, `tests/test_ml_auditor.py`,
  `tests/test_latex_exporter.py` — real-logic and `UNVERIFIED`-degradation
  coverage for the three skills that shipped as skeletons earlier in the
  v1.2.0 cycle and have since graduated.
- `tests/test_repo_consistency.py` — repo-wide guard that every skill's
  `SKILL.md` frontmatter, `manifest.json`, entrypoint, `LICENSE` and
  declared dependencies stay in agreement. Mutation-tested against the
  `pandoc` / `cleanlab` doc drift it was written to catch.
- `tests/test_sandbox.py` — regression tests for the 120s circuit-breaker
  and the normal-return path.

### Documentation
- Back-ported the **Quick Execution** block (the one-line call template the
  v1.1.2 entry promised for "all 14 skills") to the five adapter skills that
  were still missing it: `fulltext-extractor`, `literature-retriever`,
  `bibtex-normalizer`, `reference-auditor`, `data-profiler`. The nine legacy
  trees keep their original `SKILL.md` bodies byte-frozen by the
  zero-amputation red line, so the block is deliberately **not** back-ported
  there; `tests/test_repo_consistency.py` encodes that exemption.
- Corrected stale statements across `README.md`, `README_zh.md`,
  `ORCHESTRATOR.md`: `latex-exporter` no longer claims `pandoc` (it is
  standard-library only and unsandboxed), `ml-auditor` no longer claims
  `cleanlab` as a hard dependency, and `quantitative-validator` is described
  as the atom-conservation gate it actually is.
- Documented the two skill layouts as an explicit convention —
  **adapter skills** (`run.py` at the skill root, thin wiring over
  `lib/chelate_core/`) vs **engine skills** (`scripts/run.py` +
  `scripts/engine.py`, owning their own algorithm) — instead of leaving the
  split undocumented.

- **`README.md` and `README_zh.md` are now true translations of each other.**
  The two files had drifted into different documents: the English one carried
  the architecture tree, the two skill layouts, the gate and manifest
  contracts, the per-skill inventory and the test inventory, while the Chinese
  one carried installation, known limitations, issue reporting and routing
  rules. Both files now share one section-for-section structure (37 matching
  headings), each section present in both languages; the Chinese dependency
  matrix was re-ordered to the English one's stage order, and the tree root
  label was corrected to `chelate-shell/` in both.
- **Fixed the `new` skill labels.** The label had frozen at the v1.1.x roster:
  `fulltext-extractor`, `literature-retriever`, `bibtex-normalizer`,
  `reference-auditor` and `data-profiler` were still badged *(new)* a release
  later, while the five skills that actually are new in v1.2.0 (`sem-auditor`,
  `quantitative-validator`, `ml-auditor`, `figure-generator`,
  `latex-exporter`) were badged *(v1.2.0)* instead. *(new)* now marks exactly
  the current release's additions in both the skill inventory and the
  directory tree, and the label convention is stated explicitly in both
  READMEs. The stale test count (278) was also corrected to 289 in both files.

### Removed
- `amos-auditor` — superseded by `sem-auditor` (reads lavaan-style syntax or
  JSON instead of AMOS output; same hard-gate + APA output contract).

### Removed
- **sem-auditor extracted into the standalone sem-copilot plugin.** The SEM /
  AMOS-replacement module (the extended SEM functions from the Added section
  above) now lives in its own repository, `sem-copilot`. This main repo keeps
  the remaining 18 skills. See the README引流 note for install pointers.

## [1.1.2] — 2026-10-24

### UX
- Added a **Quick Execution** block to every `SKILL.md` (all 14 skills). The
  block gives the invoking AI a precise one-line call template so it does not
  waste tokens reading the source tree. The block also instructs the AI to
  interpret stdout directly without re-reading generated report files, and to
  honour the `--root` workspace-writes contract.

## [1.1.1] — 2026-10-24

### Security
- Removed the PyMuPDF (AGPL-3.0) dependency from `fulltext-extractor`.
  The extractor now uses **pdfminer.six** (MIT) as the primary backend,
  with **pypdf** (BSD-3-Clause) as a transparent fallback when pdfminer is
  not installed. Both are permissive-licence libraries; the skill no longer
  links any AGPL component.

### Fixed
- Workspace path contract: all 14 adapters now honour a mandatory `--root`
  and write every artifact (gates, reports, ingest output) into
  `<workspace>/process/` instead of the skill install / plugin-cache dir.
  Legacy CLIs run with cwd pinned to the workspace; explicit user flags
  still win over injected defaults.
- `formula-validator` `REPORT_DIR` and `video-tracker` / `capstone-labmate` /
  `multi-dim-manager` output dirs are anchored to the workspace.
- `GateResult.from_dict` no longer raises on a corrupt gate file; malformed
  `status` / `evidence_level` degrade to `UNVERIFIED` instead of a `ValueError`
  (the router now reports a corrupt gate as UNVERIFIED, not FAIL).
- Router `--help` probe: a skill whose adapter fails to start is now reported
  as an `[INPUT]` warning instead of being silently skipped from auto-wiring.

### Changed
- Bumped every `manifest.json`, per-platform `plugin.json`, `package.json`,
  and SKILL.md frontmatter to 1.1.1 (single source of truth kept in lockstep).
## [1.1.0] — 2026-10-23

### Added — microkernel architecture
- `core/router.py`: manifest-driven dispatcher. Scans the 14 skill manifests
  into an in-memory routing table, matches inputs to `stage="ingest"` skills,
  then serially dispatches `stage="gates"` skills. The first gate returning
  `FAIL` terminates the pipeline immediately (red terminal output);
  intermediate products stay locked in `process/` and are never promoted.
  Full pass promotes `process/` to `results/promoted_<ts>/`.
- `core/registry.py`: flat scan of `skills/*/manifest.json` (nested manifests
  are rejected), pure-stdlib manifest validation, routing table
  (`by_stage` / `by_input` / `get` / `names`).
- `core/sandbox.py`: per-skill dependency resolution; missing dependencies
  degrade a skill to an `UNVERIFIED` gate instead of crashing.
- `contracts/gate_result.py`: unified gate contract
  `{skill, status, evidence_level, reason, artifacts, timestamp}`.
- `contracts/schema.json`: manifest schema (ten fields incl. `output_types`
  and `sandbox_required`, `additionalProperties: false`, `stage` enum of
  four values).
- `bootstrap.py`: workspace bootstrap helpers (`write_gate` / `read_gate` /
  `gates_dir` / `repo_root` / `legacy_cwd` / `probe_deps`).
- `cli.py`: `list`, `run <skill>`, and `pipeline` commands with
  `--mode a|b|c`, `--input-kind`, `--inputs`, `--selected`, `--skill-arg`,
  `--dry-run`, `--debug`.
- Adapter contract: every skill now exposes a root-level `run.py` with the
  unified CLI `--root <workspace> --action <...> [legacy args]`, writing a
  standard gate result to `process/gates/<skill>_<ts>.json`. Legacy CLIs
  remain directly runnable.
- `pipeline --inputs FILE [FILE ...]`: declares the run's input files
  (workspace-relative or absolute). Each file is resolved against `--root`
  (missing files fail fast with exit code 2 before any skill runs), narrows
  the plan to the skills whose manifest `input_types` declare its type (an
  explicit `--selected` list always wins), and is forwarded as `--input` to
  the matching adapters that define it (probed via `--help`; explicit
  `--skill-arg` flags are appended after, so they win under argparse's
  last-value rule). A file whose extension declares no manifest type is
  reported as an `[INPUT]` warning and wires to nothing.
- 156 automated tests under `tests/` (contracts, registry, router, cli,
  capability guard, formula-validator, video-tracker, new skills,
  thin-adapter and no-stub guards, unified debug layer, input-path
  resolution, `--inputs` auto-wiring, plugin-manifest contract,
  SKILL.md frontmatter/manifest agreement).
- Unified debug layer: `lib/chelate_core/debug.py` exposes one switch with two
  shapes — `--debug` on every `cli.py` subcommand and `core/router.py`, or the
  `CHELATE_DEBUG=1` environment variable (inherited by skill subprocesses, so
  it reaches every adapter and legacy CLI). Debug lines go to stderr with a
  `[chelate:debug]` prefix; the stdout gate-contract line stays clean.
  Coverage: registry scan, resolved command and cwd, dependency verdict,
  return code / duration / stderr tail per skill, legacy action → module
  mapping, and the emitted gate path with its status.
- Plugin manifests for four host platforms, repaired against the v1.0.0
  rejection: `.claude-plugin/`, `.codebuddy-plugin/`, `.codex-plugin/` each
  ship `plugin.json` (+ `marketplace.json`), and `.dsh-plugin/` ships the CJS
  entry (`index.js` exporting `name` + `apply(ctx)`). Two contract
  violations were fixed: `author` is now an object (`{"name": ...}`) instead
  of a bare string, and the invalid string `skills` field is omitted so the
  host auto-scans the flat `skills/` directory; the `icon` field was removed
  from `plugin.json` (the shared `assets/icon.png` stays in the repo). Root
  `package.json`, `index.js` and `cordis.patch.yml` complete the dsh
  packaging, and `ORCHESTRATOR.md` documents the v1.1.0 routing contract
  (14 skills, 4 stages). `tests/test_plugin_manifests.py` locks the shape:
  version sync across all manifests, author-object, no string `skills`, no
  `icon`, marketplace entries, and the CJS entry surface.

### Added — `lib/chelate_core/` (programs live outside the skills)
- `adapter.py`: thin-adapter toolkit — common argparse, gate emission,
  controlled degradation (`Degraded` / `Failed`), and a declarative runner
  for the migrated legacy CLIs (`run_legacy`).
- `paths.py` / `yamlmini.py`: repository/skill/workspace path resolution and
  `assets/config.yaml` loading (PyMuPDF-free flat YAML subset fallback, so
  configuration never requires PyYAML).
- Core algorithm modules shared by the skills: `pdf_text.py`,
  `arxiv_search.py`, `bibtex_norm.py`, `doi_audit.py`, `csv_profile.py`,
  `formula_merge.py`.
- Every skill folder now carries the standard surface: `SKILL.md`,
  `manifest.json`, `README.md`, `LICENSE`, thin `run.py`, `assets/`.
- The five new skills' `SKILL.md` files follow the original nine's template
  (YAML frontmatter + When to use / When NOT to use / Core Workflow / Hard
  Constraints / Resources).

### Added — five new skills
- `fulltext-extractor` (ingest): PyMuPDF text extraction with page selection
  and a JSON metadata sidecar; scanned/image PDFs degrade to `UNVERIFIED`.
- `literature-retriever` (ingest): arXiv keyword search to JSON
  (title, abstract, authors, links) in `process/literature/`.
- `bibtex-normalizer` (ingest): `bibtexparser`-based parsing with
  citation-key and title+year dedupe, normalized output plus a dedupe report.
- `reference-auditor` (gates): DOI extraction from drafts and Crossref REST
  verification; any non-existent DOI fails the gate and terminates the
  pipeline.
- `data-profiler` (gates): pandas CSV profiling — row/column counts,
  per-column missing statistics, 1.5·IQR outlier ratios (configurable fence),
  duplicate rows, constant columns.

### Changed
- `formula-validator`: merged a `pint` physical-unit cross-check layer
  (`scripts/core/pint_units.py`) alongside the existing SymPy D1–D5 layers.
  New `units` action exposes the pint layer standalone.
- All nine legacy skills re-versioned to 1.1.0 with new `manifest.json`
  metadata (`output_types`, `sandbox_required` added); internal module
  layout unchanged. Their `run.py` adapters are now declarative tables over
  `lib/chelate_core/adapter.py` instead of inline wiring.
- Root `LICENSE` added (MIT); `README_zh.md` (Chinese entry) and `.gitignore`
  carried over from v1.0.0; `capstone-labmate/NOTICE` carries the PASCO
  trademark disclaimer.

### Migration integrity
- The nine v1.0.0 skills were migrated byte-for-byte (179 Python files,
  ~37,400 lines, SHA-256 verified). `tests/test_capability_guard.py`
  re-verifies file parity with the v1.0.0 source tree and the presence of
  every key module function on every test run, guarding against future
  amputation.

### Fixed
- The nine legacy `SKILL.md` frontmatters shipped stale contract fields:
  versions like `1.0.0-beta` / `0.0.0-beta` (contradicting the manifests'
  `1.1.0`), `entry_point` values pointing at CLIs the Router never calls
  (`python -m src.cli`, `python -m scripts.tracker` — capstone-labmate
  declared `src.cli` although it has no `src/` package at all), and
  `python_requires: '>=3.9'` against the repo-wide 3.10+ floor. All three
  fields now agree with the manifests and README; the byte-identity guard
  masks exactly those frontmatter lines so the SKILL.md *bodies* stay
  provably untouched, and `tests/test_plugin_manifests.py` fails on any
  future drift.
- `docs/audit_feature_parity.py`: the entrypoint audit compared raw command
  strings including the frontmatter, so re-pointing `entry_point` at the
  thin adapter read as three "missing entrypoints". It now extracts only
  body-documented commands and normalizes `python -m a.b` to `python a/b.py`
  before diffing; the frontmatter contract is covered by the guard test
  above.
- Legacy usage errors no longer hard-block the pipeline: when a migrated
  legacy CLI exits non-zero with an argparse usage error on stderr (e.g.
  `conflict-detector` invoked without its required `--config`), the adapter
  emits `UNVERIFIED` ("legacy CLI invocation incomplete") instead of `FAIL`.
  An incomplete invocation means the check never examined the data — it is
  "not verified", not a data rejection. The legacy stderr is still echoed
  for direct runs.
- `tests/test_capability_guard.py`: the byte-identity walk now also skips
  `test_workspace/` (user scratch workspace with runtime gate artifacts),
  and `.gitignore` / the release archive exclude it as well.
- `fulltext-extractor`: `extract()` now creates its output directory when
  called programmatically (previously only the CLI path did).
- `pdf_text.parse_pages`: a non-empty but unparsable page spec (e.g. "abc")
  now falls back to all pages instead of extracting nothing.
- Workspace-relative `--input` paths: the four new skills resolved `--input`
  against the process cwd (the repository root under the Router), so the
  documented workspace-relative usage (`--input draft.md` next to
  `--root <workspace>`) failed with "not found". `lib/chelate_core/paths.py`
  gained `resolve_input(root, path)` — absolute and cwd-existing paths pass
  through, relative paths resolve against `--root`; wired into
  data-profiler, reference-auditor, fulltext-extractor and bibtex-normalizer.
- Docstrings quoting the original Chinese build instructions were
  translated to English, keeping the shipped tree English-clean.
- `core/router.py`: `run_skill` referenced the debug module through its
  `debug` parameter (shadowing), raising `AttributeError` whenever
  `--debug` was active on a real pipeline run. The mock-based router tests
  never executed the real `run_skill`, so `tests/test_debug.py` now includes
  a real-subprocess integration test for the router's debug plumbing.
- `tests/test_capability_guard.py`: `task-organizer/_broadcast/` (a runtime
  output directory the legacy broadcast CLI writes on every run) is now
  whitelisted like the other runtime dirs.
- `docs/audit_feature_parity.py`: fixed path resolution (the v1.0.0 source
  tree and the `skills/` directory were mis-resolved) and translated the
  module docstring to English; the audit now exits non-zero on any missing
  documented entrypoint or unimportable legacy module.
