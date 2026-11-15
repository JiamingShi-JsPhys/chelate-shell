# Contributing to Chelate Shell

Thanks for considering a contribution. This repository is a deterministic
orchestrator for local agent skills: it routes work through a gated pipeline
and never generates results itself. The rules below exist so that a change
cannot quietly weaken a gate or break a release.

## Before you start

- Open an issue first for anything larger than a bug fix or a documentation
  correction — especially a new skill or a change to the gate contract.
- Security problems do **not** belong in an issue. See [SECURITY.md](SECURITY.md).

## Development environment

Python 3.10 or newer. There is nothing to build or install: every entry point
runs from the repository root.

```bash
git clone https://github.com/JiamingShi-JsPhys/chelate-shell.git
cd chelate-shell
python -m pip install pytest
```

The optional dependencies each skill needs are listed in
[docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) (and its Chinese twin). A skill
whose dependency is missing degrades to an `UNVERIFIED` gate; it never
crashes the pipeline.

## Running the tests

```bash
python -m pytest                      # the root suite (pytest.ini scopes it to tests/)
python -m pytest skills/data-profiler/tests   # one skill's own suite
```

Each skill suite has to run in its own pytest process. Several of them define
a top-level `tests` package, and one process cannot host two of those — that
is the `ImportPathMismatchError` the CI layout avoids. Never combine several
skill directories into a single `pytest` invocation.

CI runs three jobs on Python 3.10 and 3.12: `bare` (pytest only, so the
degraded path stays exercised), `extras` (the optional dependencies
installed), and one pytest process per skill suite. Keep local results
consistent with all three where you can.

## What CI and the repo guards enforce

These are checks, not suggestions — most of them fail with a message that
names the file to fix.

- **One version everywhere.** `EXPECTED_VERSION` in
  `tests/test_repo_consistency.py` must match every `skills/*/manifest.json`,
  the `SKILL.md` frontmatter, the `CHANGELOG.md` section for that version, the
  host plugin manifests, `package.json`, and the version strings under `lib/`.
  A release touches all of them together.
- **Documentation comes in pairs.** Every `docs/X.md` has a `docs/X_zh.md`,
  and the tables in both must agree with the manifests.
- **The gate contract is fixed.** Every gate emits a result; the first `FAIL`
  terminates the pipeline and locks `process/`. Do not add a path that
  promotes work past a failed gate.
- **No writes outside the workspace.** Adapters resolve `--input` against
  `--root` and write only under it.
- **No secrets in the tree.** Credentials come from environment variables at
  run time. The repository is scanned for key-shaped strings and for contact
  addresses; use a placeholder such as `you@example.com` in examples.

## Before you open a pull request

1. Run the root suite, plus the suite of every skill you touched.
2. Add a `CHANGELOG.md` entry under the current version; the format follows
   [Keep a Changelog](https://keepachangelog.com/).
3. If you changed behaviour, update the paired documentation files.
4. Keep the diff focused. Unrelated reformatting makes a gate change hard to
   review.
5. Use a commit message that says what changed and why, in the imperative
   mood.

## License

By contributing you agree that your contribution is licensed under the MIT
License, the same terms as [LICENSE](LICENSE).
