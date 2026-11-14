# Acknowledgements

People who reported a problem that changed this project, with what they reported and what it changed. The README carries the names; this page carries the detail.

**English** · [简体中文](ACKNOWLEDGEMENTS_zh.md)

## NotFatJustRound

[issue #1](https://github.com/JiamingShi-JsPhys/chelate-shell/issues/1).

The suite was green only on the machine that wrote it. With no `pytest.ini` at
the root, a fresh clone collected `skills/*/tests/` as well as `tests/`, and
those directories shadowed the root `conftest.py` — the run died during
collection with `ImportPathMismatchError` instead of testing anything. The
`pytest.ini` that scopes collection to `tests/`, and the workflow that runs it
on every push, come from this report.

The same issue found `package.json`'s `files` list shipping `skills/` without
`core/`, `lib/`, `cli.py`, `bootstrap.py` or `contracts/`, so an npm install
carried every skill and none of the code they import.

## DeepSec

The code-security auditor this tree is scanned with (`deepsec shield scan`).
Its L1 pattern set and SAST rules found the two command-injection paths that
1.3.2 closed — `multi-dim-manager` running a plugin template through
`shell=True`, and `core/sandbox.py` executing whatever program a manifest
named. It is also the scanner behind the "0 findings" line quoted in the
1.3.2 and 1.3.3 changelog entries, and it has no stake in the result: several rounds of fixes were rejected by it before one came back
clean.
