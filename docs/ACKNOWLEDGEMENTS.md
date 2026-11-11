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
