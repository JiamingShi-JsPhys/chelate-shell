# Chelate Shell

**A deterministic orchestrator for research and engineering workflows — nineteen research skills ship with it, and they run in the pipeline.**

Individual skills solve isolated problems; an agent still has to decide which one to call, in what order, and where the output belongs. Chelate Shell puts both halves in one repository: the 19 engines, and a microkernel that routes them in a fixed stage order and writes a typed gate for every call.

- **For researchers:** the skills compute. Five SymPy layers plus a pint cross-check, RDKit atom conservation, R mixed models and mediation, OpenCV trajectory tracking, publication-grade charts — not prompt templates.
- **For agents:** `core/router.py` builds a deterministic plan, screens text inputs for prompt injection before dispatch, and stops the pipeline on the first `FAIL`.
- **For the record:** every call leaves a `GateResult` in `process/gates/`. `PASS`, `UNVERIFIED` and `FAIL` are different states, and only the last one is terminal.

**English** · [简体中文](README_zh.md)

**Version:** 1.3.3 | **License:** MIT | **Python:** 3.10+ | **Skills:** 19

> Research assistance only. Read the [security & open-source statement](#security--open-source-statement) before relying on any output.

---

## Contents

**Getting started**

- [Why Chelate Shell?](#why-chelate-shell)
- [Installation](#installation)
- [Quick start](#quick-start)
- [What you can ask for](#what-you-can-ask-for)
- [See it work](#see-it-work)

**How it works**

- [How a run flows](#how-a-run-flows)
- [Commands added in 1.3.0](#commands-added-in-130)
- [Sub-agents added in 1.3.0](#sub-agents-added-in-130)
- [Repository layout](#repository-layout)

**The rest**

- [Requirements](#requirements)
- [Tests](#tests)
- [Security & Open Source Statement](#security--open-source-statement)
- [Known limitations](#known-limitations)
- [Report issues](#report-issues)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## Why Chelate Shell?

In the current AI ecosystem, individual skills excel at solving isolated problems: validating formulas, tracking videos, or organizing files. However, when an Agent faces a complex task, it often struggles to determine **which skill to invoke, in what order, and where to place the outputs**. Scattered, stateless skill calls lead to context pollution, file-version confusion, and untrustworthy AI hallucination.

Chelate Shell addresses this in two parts, and both are part of the same repository.

**The 19 skills implement their algorithms directly.** They are not prompt templates. `formula-validator` runs five check layers over SymPy and cross-checks units with pint. `quantitative-validator` balances chemical equations through RDKit. `longitudinal-analysis` calls lme4 and lavaan in R. `video-tracker` performs CSRT tracking in OpenCV and computes an FFT of the trajectory. `ml-auditor` checks labelled datasets for data leakage and label errors with scikit-learn. `sci-visualizer` renders publication-grade charts with matplotlib and seaborn. `fulltext-extractor` extracts page ranges from PDFs, and `latex-exporter` assembles the Markdown reports into a compilable `.tex` using the standard library only. Each one is wired into the pipeline and covered by the test suite.

**The orchestrator supplies the guarantees an individual skill cannot provide for itself.** `core/router.py` decomposes the request, enforces the standard four-zone workspace, and routes work in a deterministic stage order, so the same inputs always produce the same plan. It also writes a typed gate for every call, stops the pipeline on the first `FAIL`, reports an explicit `UNVERIFIED` when a dependency is missing, and maintains the `_broadcast/` index that lets a later session read one summary instead of every original.

---

## How a run flows

`core/router.py` reads the 19 manifests, builds a plan in the canonical stage
order, screens text inputs for prompt injection before dispatching, and calls
each skill's adapter. Every call writes a `GateResult`: `PASS` continues,
`UNVERIFIED` degrades one skill and the run continues, and the first `FAIL`
locks `process/` and stops the pipeline — including across runs: promotion
refuses while any skill's newest gate is a `FAIL`, so a later, narrower plan
cannot deliver around a failure it did not re-run.

Promotion from `process/` to `results/` is the one irreversible step, so it
needs an approval a human issued for that plan: run
`python cli.py approve --root <ws> --mode a`, type the confirmation it asks
for, then `python cli.py pipeline --root <ws> --mode a`. The signing key
lives outside the workspace, so an agent cannot mint its own. Without a token
the run still completes — the attempt stays visible in `process/` — but the
pipeline writes nothing to `results/` and exits non-zero, so a caller that
only reads the status cannot mistake a withheld promotion for success.

The gate guards `promote()`, not the directory: an agent with file-write tools
can still copy a file into `results/` itself, and one did in testing. So every
promotion is logged with the token that authorised it and the hash of each
file it copied, and `python cli.py audit --root <ws>` names anything in
`results/` no promotion accounts for (exit 1), as does every pipeline report
under `results_audit`. Threat model, adversarial tests and limits:
**[docs/SAFETY.md](docs/SAFETY.md)**.

The diagram, the four stages and the promotion path: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Installation

If you are on Claude Code, this is the whole install:

```bash
claude plugin install chelate-shell --marketplace https://github.com/JiamingShi-JsPhys/chelate-shell.git
```

Every other host has its own one-liner — Codex, dsh, CodeBuddy, and the eight rule-file hosts — collected on **[docs/INSTALL_COMMANDS.md](docs/INSTALL_COMMANDS.md)**.

Three ways in. Plugin hosts install Chelate Shell as **one plugin** — the only form that keeps microkernel auto-routing intact. Hosts without a plugin channel take it as a **rule file**, and one script writes every rule file for you. The third way hands the whole job to an AI.

### Keeping an installed copy current

A host installs a plugin into a cache of its own, so the copy that runs is
frozen at install time — and a fixed bug keeps running until that cache is
refreshed. Two commands close that gap:

```bash
python cli.py update            # does this copy still match main?
python cli.py update --apply    # run each host's own update command
```

`update` compares the files this copy is running with the ones on `main` (line
endings aside) and names the ones that differ; version numbers alone would not
notice a release window. `--apply` runs `zcode plugins …` or `claude plugin
update` for the hosts that actually have the plugin installed, and reports what
each one said. Both are best-effort: offline means "unknown", not an error.
`cli.py pipeline` and `cli.py audit` print one stderr line when the copy has
drifted, checked at most once a day and cached; `CHELATE_UPDATE_OFF=1` silences
it.

### Method 1: install from the plugin marketplace by URL

Every host below has its own plugin marketplace. Register this repository's Git URL, then install the plugin it lists (registering the URL twice is harmless — the second call reports it is already known).

```text
/plugin marketplace add https://github.com/JiamingShi-JsPhys/chelate-shell.git#v1.3.3
/plugin install chelate-shell@chelate-shell-marketplace
```

The `#v1.3.3` suffix pins the release; drop it to follow the default branch.

### Method 2: install with commands

Claude Code, Codex, dsh and CodeBuddy take a one-line plugin command; Cursor, Windsurf, Cline, Continue, Roo Code, GitHub Copilot and opencode read a rule file, and one script writes all of them. Every command, every flag and the optional dependencies live on one page: **[docs/INSTALL_COMMANDS.md](docs/INSTALL_COMMANDS.md)**.
### Method 3: let your AI install it

```bash
Please visit the GitHub repository `https://github.com/JiamingShi-JsPhys/chelate-shell` and clone it, then run `python install.py --project . --global`. If your host has a plugin system, install it as a single plugin instead; the script covers the hosts that read rule files.
```

> **Warning**: when an AI performs the installation it will very likely scatter the individual skills from `skills/` flat into the platform's global skill directory. That breaks Chelate Shell's microkernel auto-routing architecture and degrades it into 19 loose skills. Use Method 1 if you need the full plugin orchestration.

## Quick start

Install the plugin, then stay in the chat box: type `/` and pick a skill or a
command. No shell, no absolute path — the workspace is the folder you are
already working in.

### Skills

All 19 skills are registered under the `chelate-shell` namespace, so every one
of them is one `/` away:

```text
/chelate-shell:task-organizer      turn this folder into a task workspace
/chelate-shell:formula-validator   check F = m*a with units F=N, m=kg, a=m/s^2
/chelate-shell:reference-auditor   verify every DOI in draft.md against Crossref
/chelate-shell:security-guard      screen draft.md for prompt injection
/chelate-shell:data-profiler       profile data.csv
```

Say what you want after the name; the skill picks the action and writes a gate
result. A fake DOI does not merely warn — it fails the gate and stops the
pipeline.

### Commands added in 1.3.0

Two commands put the heavier engines behind a single line:

| Command | Does |
|---|---|
| `/chelate-shell:figure` | Renders a bar / line / scatter / box chart from a CSV or JSON dataset into `process/figures/` — a vector PDF plus a raster PNG |
| `/chelate-shell:model3d` | Generates a Wavefront `.obj` from a JSON spec, or audits and merges existing meshes, into `process/models/` |

```text
/chelate-shell:figure data.csv — scatter of voltage against time
/chelate-shell:model3d spec.json
```

Both run sandboxed with a 120-second circuit-breaker: a pathological input
degrades to `UNVERIFIED` rather than blocking the run.

### Sub-agents added in 1.3.0

Two roles in `agents/` are registered with the plugin:

| Sub-agent | Fits | Skills it may use |
|---|---|---|
| `spatial_agent` | 3D content — image-to-3D, video-to-3D, scene composition, mesh QC | 3d-modeler, sci-visualizer, security-guard |
| `visual_agent` | Publication visuals — 2D plots, static diagrams, gif frames, figure QA, LaTeX export | sci-visualizer, latex-exporter, security-guard |

Claude dispatches to them when a task matches, and you can name one in your
request. Each is bounded by a skill whitelist, a writable-path whitelist
(`assets/`, `process/`, `results/`) and a step budget, so a sub-agent cannot
reach a skill or a directory outside its role.

### When you need the CLI

The same operations are available headlessly for CI and scripted runs; the
flags, the `a` / `b` / `c` pipeline modes and the debugging switches are
specified in [ORCHESTRATOR.md](ORCHESTRATOR.md) §5.

## What you can ask for

| Ask in your own words | Routes to | You get back |
|---|---|---|
| "check `F = m*a` with units F=N, m=kg, a=m/s²" | `formula-validator` | PASS / FAIL across five check layers, plus a Markdown report |
| "verify every DOI in draft.md" | `reference-auditor` | each DOI checked against Crossref; a fake one fails the gate |
| "are these two drafts consistent?" | `conflict-detector` | every contradiction, with a severity |
| "profile data.csv" | `data-profiler` | rows, missing values, 1.5·IQR outliers, duplicate rows |
| "is there leakage in this labelled dataset?" | `ml-auditor` | leakage and label-error verdict, via scikit-learn |
| "draw voltage against time" | `sci-visualizer` | a vector PDF and a PNG in `process/figures/` |
| "extract text from these PDFs, pages 3–7" | `fulltext-extractor` | plain text plus a JSON sidecar in `process/` |
| "find recent papers on X" | `literature-retriever` | arXiv metadata as JSON |
| "track the ball in this video" | `video-tracker` | coordinates, an FFT spectrum, physics probes |
| "merge my reports into a LaTeX file" | `latex-exporter` | one compilable `.tex` |
| "build this mesh and check it" | `3d-modeler` | an OBJ plus winding / degenerate-face / bounding-box audit |
| "is this text trying to inject instructions?" | `security-guard` | injection markers and dangerous call sites |

All 19, with what each one actually computes, are listed under [Repository layout](#repository-layout).

## See it work

```text
> /chelate-shell:formula-validator   v = d/t    units: v=m, d=m, t=s

FAIL · SYMBOLIC
pint unit mismatch — LHS [length], RHS [length]/[time]
gate    → process/gates/formula-validator_20261112T130046Z.json
report  → process/reports/equation-4c9b2ce5-20261112-210045.md
```

A wrong dimension is not a warning: it is a gate failure, a written report, and a pipeline that stops there.

## Requirements

Python 3.10+ and nothing else to start: the microkernel and most skills run on the standard library alone. A handful of data and network skills additionally want common third-party packages (numpy, pandas, sympy, rdkit, matplotlib, requests and friends); each skill's `manifest.json` declares exactly what it needs, and `core/sandbox.py` checks that at run time. A missing package never crashes the pipeline — that one skill degrades to an `UNVERIFIED` gate with a hint and the rest keeps running. No third-party code is vendored; every library stays under its own permissive licence. The full per-skill matrix lives in [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

## Repository layout

`core/` is the microkernel, `lib/chelate_core/` holds the shared logic every
adapter imports, `skills/` holds one folder per skill (flat — the host
scanners do not descend into namespace folders), and each host's plugin or rule
file sits in its own dot-directory.

Every directory, and what each of the 19 skills computes: **[docs/REFERENCE.md](docs/REFERENCE.md)**.

## Tests

```bash
python -m pytest tests/ -q
```

412 tests: 401 pass and 11 skip with the optional dependencies installed;
with nothing but pytest, the dependency-gated cases skip instead and the
`UNVERIFIED` path is what runs. The seven skills that ship their own upstream
suite under `skills/<skill>/tests/` are run one directory per process.

Both environments, the coverage list and the per-skill counts: **[docs/TESTING.md](docs/TESTING.md)**.

## Security & Open Source Statement

> **Disclaimer**: This repository contains auxiliary tools developed by the author to automate research workflows. It is not a peer-reviewed academic project. Some boilerplate or utility scripts may have been generated with the assistance of AI, and have been integrated with high-level review and modifications by the author. The author assumes no responsibility for any third-party code issues, but commits to promptly addressing any valid claims.
>
> This tool **will never do the experiment for you**. Data must be collected manually by students in the lab; AI is absolutely physically isolated during the in-lab stage. Generated reports are merely "data-analysis drafts", and final academic responsibility lies with the user and their institution.

## Known limitations

Honest edge cases — read before relying on any output or on the safety layer:

- **The approval layer is a policy gate, not containment**: once a human has approved anything in a workspace, the signing key persists in the per-user directory and a process running as that user can sign its own token. It reliably stops an agent that did not go looking; real containment needs an OS boundary (a separate user, a container, a syscall filter). It also guards `promote()`, not the `results/` directory — a file written there by hand needs no token, and an agent test did exactly that; `python cli.py audit` names such files after the fact. Measured and disclosed in [docs/SAFETY.md](docs/SAFETY.md), together with the executable whitelist's limits.
- **Automatic ROI detection can fail**: `video-tracker` may fail on low-contrast video; every run must be checked against the reference. Marked *experimental / unstable*.
- **Formula checking is not a mathematical proof**: `formula-validator` is a deterministic verdict. An `unknown` return means one check "abstained" — a legitimate state that must never be reinterpreted as a pass.
- **Longitudinal analysis depends on R**: some advanced statistical steps of `longitudinal-analysis` run through R scripts; if `Rscript` is absent those steps are skipped and logged — **never hand-write Python code to replace skipped R steps**.
- **Version tracking is structural, not semantic**: `document-evolution-tracker` diffs by block alignment; a concept counts as "present" only on a literal match.
- **DOI audit verifies existence only**: `reference-auditor` confirms a DOI exists in Crossref, not that it is the paper you meant to cite — citation correctness remains the author's responsibility.
- **The injection scan is a screen, not a sandbox**: `security-guard` flags known markers and dangerous call sites; it cannot prove a file is safe.
- **Data profiling never cleans data**: `data-profiler` only reports missing values / outliers / duplicate rows; it never modifies input files.
- **Determinism covers the scheduling layer only**: the router guarantees the same input routes to the same skill, but it cannot make a non-deterministic underlying algorithm deterministic.

## Report issues

**Regular bugs / feature requests**: file them on the repository's [Issues](https://github.com/JiamingShi-JsPhys/chelate-shell/issues) page. Include reproduction steps, expected behavior, actual behavior, and the environment (operating system, Python version).

**Security vulnerabilities (this category only)**: do **not** use the public Issues page. Email `jiamingshi_git@outlook.com` instead.

- **Subject**: must carry the prefix `_report` plus the specific product or skill name and a short summary.
  - Example: `report_chelate-shell: path traversal can read outside the task folder`
- **Body**: must include detailed reproduction steps and the environment.
- For serious "file loss or corruption" reports, attach the before/after directory trees (`tree` output) and the generated `verification_report.md`.

*Contributors who file clear, reproducible issues or pull requests will be credited in the next release's notes.*
## Acknowledgements

**NotFatJustRound** — [issue #1](https://github.com/JiamingShi-JsPhys/chelate-shell/issues/1) asked for CI and caught an incomplete npm `files` list.

**DeepSec** — the code-security auditor this tree is scanned with. It found the two command-injection paths closed in 1.3.2, and the 1.3.3 tree scans clean (0 findings).

[Full acknowledgements](docs/ACKNOWLEDGEMENTS.md)

## License

MIT. See [LICENSE](LICENSE). Each skill directory also carries its own `LICENSE` file with the same terms.

**Author & Maintainer**: Jiaming Shi (Westlake University)
