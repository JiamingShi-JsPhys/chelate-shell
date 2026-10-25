# Contributing to task-organizer

Thank you for considering a contribution. This document explains how to
set up the development environment, run tests, and submit changes that fit
the project's standards.

## Development environment

```bash
# 1. Clone the repository
git clone https://github.com/JiamingShi-JsPhys/agent-skills.git
cd agent-skills/skills/task-organizer

# 2. Create a virtual environment and install dependencies
python -m venv .venv
# Windows:
#   .venv\Scripts\activate
# macOS/Linux:
#   source .venv/bin/activate

pip install -r requirements.txt
```

**Python 3.10+** is required. `openpyxl` is needed to generate the xlsx
index; when it is missing the feature gracefully degrades to md-only
indexing, so the standard-library-only organize + verify pipeline still
runs.

## Running tests

```bash
# all tests
pytest

# with coverage (target >= 80%)
pytest --cov=scripts --cov-report=term-missing

# a single module
pytest tests/test_verify.py -v
```

Before submitting, make sure:
- all tests pass;
- coverage stays at or above 80% (new public logic needs matching tests);
- `pytest -W error::SyntaxWarning` reports no warnings.

## Code style

- **PEP 8**: line width recommended <= 88; use `black` (optional) to keep
  the style consistent.
- **Type hints + docstrings**: every public function/method must have type
  hints and a docstring; private helpers are encouraged to have them too.
- **Error handling**: expected I/O errors are caught with `try/except` and
  degraded (recorded in `session.skipped_files` or
  `RollbackResult.conflicts`); **never** let the organize/verify/rollback
  main flow crash in a half-finished state.
- **Single responsibility**: each function does one thing; see the
  module docstrings at the top of each file in `scripts/` for the
  responsibility split.

## Placement and provenance model

The keyword rule table lives in `BUILTIN_PLACEMENT` in `scripts/rules.py`.
When you modify it, **be sure** to update:
1. the placement table in `SKILL.md`;
2. the related unit tests (`tests/test_rules.py`, `tests/test_organize.py`).

Provenance (`user` vs `downloaded`) is decided by
`scripts/sources.py` + `scripts/organize.py::_match_rule`, **not** by
keywords. Two invariants must never be broken:

- `material/initial/` is reserved for the user's own material -- the tool
  never writes anything of its own there;
- user material is **verbatim**: never renamed, never modified. A name clash
  leaves the file in place and is *reported*, never suffixed.

`tests/test_sources.py` and `tests/test_organize.py` pin these down; if you
change the model, change those tests in the same commit.

## Verification protocol

The 8 checks of the forced before/after scan verification are defined in
`scripts/verify.py`; that module is the authoritative spec. When adding a
check:
- add `_run_cN` in `verify.py` and include it in the `checks` list;
- update the check table in `verify.py` / `SKILL.md`;
- add test cases in `tests/test_verify.py`.

## Commit and PR workflow

1. Branch from `main`: `git checkout -b feat/your-feature`.
2. Small commits, imperative commit messages (`add: rollback sealing of
   logs`).
3. Run `pytest --cov=scripts` locally and make sure everything is green.
4. Open the PR; the description states: what changed / why / how it was
   verified (paste coverage).
5. Merged after at least one maintainer review.

## Reporting issues

- Use the [Issue template]: reproduction steps, expected behavior, actual
  behavior, environment (Python version, OS, whether openpyxl is
  installed).
- For "file lost/corrupted" issues, attach the before/after directory
  trees (`tree` output) and the `verification_report.md`.

## Code signing

Sign the CLA (if any) before submitting a PR. We use a lightweight DCO
substitute: append `Signed-off-by: Your Name <you@example.com>` to the
final commit (`git commit -s`).
