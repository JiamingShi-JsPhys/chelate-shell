# Chelate Shell

> **The missing orchestrator for your local agent skills.**
> Orchestrating scattered local skills into a deterministic research and engineering workflow.

**English** · [简体中文](README_zh.md)

**Version:** 1.0.0 | **Core Skills:** 9 | **Layers:** 4

---

## Why Chelate Shell?

In the current AI ecosystem, individual skills excel at solving isolated problems: validating formulas, tracking videos, or organizing files. However, when an Agent faces a complex task, it often struggles to determine **which skill to invoke, in what order, and where to place the outputs**.

Chelate Shell is an **Orchestrator**. It does not write low-level code to solve domain-specific problems. Instead, acting like a senior project manager, it decomposes user intents, enforces a standardized workspace directory structure, and **deterministically** routes tasks to the appropriate skills.

### Core Architecture
Our 9 skills are strictly divided into 4 layers (listed alphabetically within each layer) to ensure the AI never scatters files randomly in the workspace:

```text
Chelate Shell (Router)
│
├── Base Infrastructure Layer
│   ├── multi-dim-manager      # Multi-dimensional state management (snapshots/rollbacks)
│   └── task-organizer         # Standardized workspace (material/process/results)
│
├── Data Pipeline Layer
│   ├── capstone-labmate       # PASCO data parsing and charting
│   ├── longitudinal-analysis  # Longitudinal statistical modeling
│   └── video-tracker          # Video tracking and FFT spectrum
│
├── Cognitive & QC Layer
│   ├── ai-trace-remover       # Remove AI traces, optimize human readability
│   ├── conflict-detector      # Cross-document contradiction detection (numeric/boolean)
│   └── formula-validator      # Deterministic formula validation (dimension/limit/symbolic)
│
└── Monitor Layer
    └── document-evolution-tracker # Track document version evolution
```
All above skills can be found in my repository: [agent-skills](https://github.com/JiamingShi-JsPhys/agent-skills)

### Routing Rules
*   **Simple Task Bypass**: For single formula checks or one-off AI-trace removal, skip the base layer and invoke the QC skill directly without creating a directory.
*   **Complex Task Enforcement**: For any multi-step task producing deliverables, the **first step MUST be invoking `task-organizer`** to establish the three-tier structure: `material/initial/`, `process/`, and `results/`.
*   **Data Flow**: Read inputs from `material/initial/`, write intermediates to `process/`, and final outputs to `results/`.
*   **Factory QC**: Every final deliverable in `results/` must pass dual inspections by `conflict-detector` and `ai-trace-remover`.
*   *For the complete dispatcher contract, see [ORCHESTRATOR.md](ORCHESTRATOR.md).*

---

## Installation

This repository is a cross-platform Agent skill suite supporting **Claude Code, WorkBuddy, OpenAI Codex, and DeepSeek Harness (DSH)**. Please choose the installation method that best suits you:

### Option 1: Let AI Install It (Highly Recommended, Agent-Native)

Copy and paste the following prompt to your AI Agent, and it will automatically clone, configure, and mount the skills:

> "Please visit the GitHub repository `https://github.com/JiamingShi-JsPhys/chelate-shell`, clone it, and based on the current Agent platform's specifications (e.g., Claude Code or OpenAI Codex), register all skills under the `skills/` directory into your system."

### Option 2: Download Release Package (For Non-Developers)

1. Go to the [Releases](https://github.com/JiamingShi-JsPhys/chelate-shell/releases) page and download the latest `.zip` package.
2. Extract the archive and place the entire `chelate-shell` folder into your corresponding AI platform's skill directory:
   - **Claude Code**: `~/.claude/skills/`
   - **Codex**: `~/.codex/skills/`
   - **DSH**: `~/.dsh/skills/`
   - **WorkBuddy**: `~/.workbuddy/skills/`
3. Restart the AI client and enter `/skills` to confirm successful loading.

### Option 3: Git Clone (For Developers)

```bash
# 1. Clone the repository
git clone https://github.com/JiamingShi-JsPhys/chelate-shell.git

# 2. Move the skills to your platform directory (using Claude Code as an example)
cp -r chelate-shell/skills/* ~/.claude/skills/
```

> **Dependency Note**: The core dispatcher and most skills rely solely on the Python standard library. A few data-processing skills (e.g., `formula-validator`, `video-tracker`) require third-party libraries such as `sympy`, `numpy`, and `opencv-python`. If dependencies are missing, the system will degrade gracefully with a prompt rather than crashing. See the dependency matrix below for details.

---

## Quick Start

All commands should be executed in the `chelate-shell` plugin root directory. **Never hardcode absolute paths.**

**1. Initialize a Complex Task Workspace**
```bash
cd skills/task-organizer
python -m scripts.run init <root>
python -m scripts.run organize <root> # Auto-archive, auto-rollback on failure
```

**2. Deterministic Formula Validation (Bypass Mode)**
```bash
cd skills/formula-validator
python scripts/cli.py validate --expr "sqrt(k/m) = omega" \
    --units "k=kg/(s**2)" --units "m=kg"
```

**3. Remove AI Traces from a Draft**
```bash
cd skills/ai-trace-remover
python -m src.cli <file> --json
```

**4. Track Document Version Evolution**
```bash
cd skills/document-evolution-tracker
python -m src.cli run --config config/examples/family.json --concepts "entropy,partition function"
```

---

## Skill Dependency Matrix

| Skill | Required Dependencies | Optional Dependencies (Degrades if missing) |
| --- | --- | --- |
| `task-organizer` | None | `openpyxl`, `PyYAML` |
| `multi-dim-manager` | None | `PyYAML` |
| `capstone-labmate` | `numpy`, `matplotlib`, `pypdf` | None |
| `longitudinal-analysis` | `numpy`, `pandas`, `statsmodels`, `scipy` | `python-docx`, `R (lme4, lavaan)` |
| `video-tracker` | `numpy`, `opencv-contrib-python` | `matplotlib` |
| `ai-trace-remover` | None | None |
| `conflict-detector` | None | `PyYAML` |
| `formula-validator` | `sympy`, `numpy`, `scipy`, `mpmath` | None |
| `document-evolution-tracker` | None | `PyYAML` |

---

## Known Limitations

Honest declaration of edge cases; please read before relying on any outputs:

- **Auto ROI detection may fail**: `video-tracker` may fail on low-contrast videos. It is marked as *experimental/unstable*; every run must be verified against a reference before citing its numbers.
- **Formula validation is deterministic judgment, not mathematical proof**: `formula-validator` returns a verdict. `unknown` means a specific check "abstains" (a legitimate state), and must never be forced into a positive conclusion.
- **Longitudinal analysis relies on R**: Some advanced statistical steps in `longitudinal-analysis` are executed via R scripts. If `Rscript` is missing from the environment, these steps are skipped and logged. **Never attempt to replace the skipped R steps with handwritten Python code.**
- **Version tracking is structural, not semantic**: `document-evolution-tracker` performs block-level diffs; a concept is considered "present" only when its literal text matches.
- **Determinism only applies to the orchestration layer**: The dispatcher guarantees that the same input routes to the same skill, but it cannot make an inherently non-deterministic underlying algorithm deterministic.

---

## Report Issues

**General Bugs / Feature Requests**:
Please submit via the repository's [Issues](https://github.com/JiamingShi-JsPhys/chelate-shell/issues) page. Include reproduction steps, expected behavior, actual behavior, and the runtime environment (OS, Python version).

**Security Vulnerability Reports (Strictly for this type)**:
Do **NOT** submit security vulnerabilities on the public Issues page. Please email `jiamingshi_git@outlook.com`.
- **Subject**: Must include the prefix `agent-skill_report` followed by the specific skill name and a brief description.
  - Example: `agent-skill_report task-organizer: Path traversal allows reading outside the task folder`
- **Body**: Must include detailed reproduction steps and the runtime environment.
- For severe reports like "file loss or corruption", attach the before/after directory tree (`tree` output) and the generated `verification_report.md`.

*Contributors who submit clear, reproducible Issues or Pull Requests will be listed in the acknowledgements of the next Release notes.*

---

## License & Author

This repository is licensed under the [MIT License](LICENSE), see the `LICENSE` file in the root directory. Individual skill packages may also contain their own `LICENSE` declarations.

**Author & Maintainer**: Jiaming Shi (Westlake University)

---

## Security & Open Source Statement

> **Disclaimer**: This repository contains auxiliary tools developed by the author to automate research workflows. It is not a peer-reviewed academic project. Some boilerplate or utility scripts may have been generated with the assistance of AI, and have been integrated with high-level review and modifications by the author. The author assumes no responsibility for any third-party code issues, but commits to promptly addressing any valid claims.
> 
> This tool **will never do the experiment for you**. Data must be collected manually by students in the lab; AI is absolutely physically isolated during the in-lab stage. Generated reports are merely "data-analysis drafts", and final academic responsibility lies with the user and their institution.
