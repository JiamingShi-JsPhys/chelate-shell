---
name: test-gate
version: 1.4.0
description: >
  Runs the declared test command and gates on what it printed: no test run is
  UNVERIFIED, not PASS.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# test-gate

This gate decides whether the code passes the tests the project declared. The
verdict is read from what the command printed, not from its exit status alone.

- **Stage:** `gates` · **Sandbox:** yes (isolated process) · **Dependencies:** none

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action run
python run.py --root <WS> --action run --command '["python","-m","pytest","-q"]'
```

- The command is an **argument list, never a string** (no shell), declared in
  `<WS>/.chelate/test-gate.json`; `command[0]` must pass the sandbox
  executable whitelist.
- Results land in `<WS>/process/gates/`, the full report in `<WS>/process/`.

## Verdicts

| Status | When |
| --- | --- |
| `PASS` | the output counts passes, no failures, and the exit code is 0 |
| `FAIL` | the output counts failures or errors, or the command exits non-zero |
| `UNVERIFIED` | no test ran, no readable summary was printed, the command timed out, or it could not be started |

Three rules are deliberate:

- **A green exit code with nothing run is UNVERIFIED.** `Ran 0 tests` and
  `collected 0 items` are caught.
- **A red summary beats a green exit code.** A wrapper that swallows its
  child's status cannot turn a failing run into a PASS.
- **A green exit code with no readable summary is UNVERIFIED too.** No pass
  and no skip in the output is not evidence that a test ran.

## When to use

- Code changed and the pipeline must not continue unless its tests pass.
- A report claims "the tests pass" and the claim has to be checked.

## When NOT to use

- You want the source *style* checked — that is `code-gate`.
- You want a security screen of the source — that is `security-guard`.
- The suite needs a GPU, a network, or more than the sandbox budget: run it in
  CI and gate on the artifact instead.

## More

- [declaring the command, outputs, failure handling and limits](references/test-gate-reference.md)
