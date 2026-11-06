# Contributing to formula-validator

Thank you for considering a contribution. This document explains how to set
up the development environment, run tests, and submit changes that fit the
project's standards.

## What this project is

A deterministic verifier for physics and mathematics formulas. The language
model is a translator, never an arithmetician: it extracts the formula from
the user's text and reads the report, while every verdict - dimensional
consistency, limit behaviour, numerical agreement, symbolic identity, matrix
properties - is produced by SymPy and NumPy. **Do not add a code path that
lets the model compute a result itself.** That is the one design rule this
repository exists to hold.

## Development environment

```bash
# 1. Clone the repository
git clone https://github.com/JiamingShi-JsPhys/agent-skills.git
cd agent-skills/skills/formula-validator

# 2. Create a virtual environment and install dependencies
python -m venv .venv
# Windows:
#   .venv\Scripts\activate
# macOS/Linux:
#   source .venv/bin/activate

pip install -r requirements.txt
```

**Python 3.10+** is required. `sympy` and `numpy` are hard requirements;
`scipy` is needed only for the functions NumPy lacks (`erf`, `gamma`,
`besselj`, `zeta`), and is imported on demand rather than at start-up.

## Running tests

```bash
# all tests
pytest

# a single module
pytest tests/test_dimensions.py -v

# with coverage (target >= 80%)
pytest --cov=scripts --cov-report=term-missing
```

Before submitting, make sure:

- all tests pass;
- coverage stays at or above 80% - new public logic needs matching tests;
- `pytest -W error::SyntaxWarning` reports no warnings.

## Code style

- **PEP 8**, line width recommended <= 88; use `black` (optional) to keep the
  style consistent.
- **Type hints + docstrings**: every public function needs both. Private
  helpers are encouraged to have them too.
- **Docstrings carry reasoning, not description.** A comment that says what
  the code does is noise; a comment that says why a non-obvious choice was
  made is the most valuable thing in the file. See `_compile` in
  `scripts/core/numeric.py` and `_zero_test` in `scripts/core/symbolic.py`
  for the register expected here.
- **Never crash on a check.** A stage that raises is converted into an
  `unknown` verdict with a reason, never propagated as a traceback. The
  wrapper is `_timed` in `scripts/core/pipeline.py`.
- **Abstain rather than guess.** If a check cannot be made, return
  `unknown` with the reason. A wrong guess that produces a false error is
  worse than admitting ignorance; this is why `auto_infer` defaults to
  `False`.

## Where the checks are defined

| Concern | File | Authority |
| ------- | ---- | --------- |
| D1 parse | `scripts/core/parsing.py` | `tests/test_parsing.py` |
| D2 dimension | `scripts/core/dimensions.py` | `tests/test_dimensions.py` |
| D3 limit | `scripts/core/limits.py` | `tests/test_limits.py` |
| D4 numeric | `scripts/core/numeric.py` | `tests/test_numeric.py` |
| D5 symbolic | `scripts/core/symbolic.py` | `tests/test_symbolic.py` |
| orchestration | `scripts/core/pipeline.py` | `tests/test_end_to_end.py` |
| report rendering | `scripts/core/report.py` | `tests/test_end_to_end.py` |
| MCP server | `mcp_server/server.py` | `tests/test_mcp.py` |
| CLI contract | `scripts/cli.py` | `tests/test_end_to_end.py` |

The rationale behind the check set (why these checks and not others) is
recorded in the changelog and in `SKILL.md` Limitations; upstream
market-analysis notes are kept out of the shipped tree.

## Invariants that must never be broken

1. **The model does not compute.** Every number in a report comes from
   SymPy or NumPy. `tests/test_skill_docs.py` greps `SKILL.md` for the
   statement of this rule.
2. **`unknown` is not `pass`.** A check that abstains must never be rendered
   as a green result, and must always carry its reason.
3. **The three canonical cases must keep their verdicts.** They are the
   contract, pinned in `tests/test_end_to_end.py`:
   a dimensional error, a divergence at an automatically found pole, and a
   correct formula that must come back clean.
4. **`derive` output stays O(1) in chain length.** Report the first break
   plus one summary line. If you add per-step detail, justify the token cost
   explicitly.
5. **Version numbers agree in three places**: `SKILL.md` frontmatter,
   `scripts/__init__.py`, and the newest `CHANGELOG.md` section.
   `tests/test_skill_docs.py` enforces this.
6. **This skill stands alone.** It must not reference, depend on, or claim
   integration with any other skill. Every skill in this repository is
   independent; a mention of a sibling skill - above all one that does not
   exist - is a defect, not documentation.

## Commit and PR workflow

1. Branch from `main`: `git checkout -b fix/your-fix`.
2. Small commits, imperative messages (`fix: defer the SciPy import`).
3. Run `pytest --cov=scripts` locally and make sure everything is green.
4. Open the PR; the description states what changed, why, and how it was
   verified (paste the test count and the coverage figure).
5. Merged after at least one maintainer review.

## Reporting issues

- Use the repository's **Issues** page.
- Include reproduction steps, expected vs. actual behaviour, and the
  environment (Python version, OS, SymPy and NumPy versions).
- For a false positive - a correct formula reported as wrong - attach the
  exact input line and the generated report from `_reports/latest.md`. These
  are the highest-value bugs in this project.
