# test-gate — reference

## Declaring the command

`<WS>/.chelate/test-gate.json`:

```json
{"command": ["python", "-m", "pytest", "-q"], "timeout": 90}
```

The command is an **argument list, never a string**. No shell is involved, so
a semicolon inside a test name stays a character in an argument instead of
becoming an operator. `command[0]` must pass the sandbox executable whitelist
(`python`, `node`, `gcc`, `clang`, …).

Keep `timeout` below the router's own sandbox budget (120 s by default). Past
it the router kills the adapter before it can report, and the pipeline records
that as UNVERIFIED — the same verdict, without the output that explains it.

`--command '[...]'` overrides the declared command for one run; `--input`
points at a test path; `--timeout` overrides the declaration.

## Outputs

- `<WS>/process/gates/test-gate_<ts>.json` — the gate result.
- `<WS>/process/test_gate_<ts>.json` — counts, exit code and the output tail.

## Failure handling

- No declaration and no `--command` ⇒ `UNVERIFIED` with the expected path.
- The command cannot start (not on the whitelist, missing binary) ⇒
  `UNVERIFIED`.
- A timeout ⇒ `UNVERIFIED`.

## Limitations

- The summary parser recognises pytest and unittest output; another runner
  that prints neither is `UNVERIFIED`, never a pass.
- One command per run; a matrix of Python versions belongs in CI.
- The gate reads the output text, so a runner that prints "1 failed" in a
  skip reason can mislead it — the raw tail is in the report for a person to
  check.

## Delivering results

This skill writes intermediates to `process/`. `results/` is filled only by
`python cli.py pipeline` after a human approved that exact plan.

- Do not copy a skill's output into `results/` yourself, and do not do it
  because the user asked for a shortcut: say that only `cli.py pipeline`
  writes there, offer to run the pipeline instead, and if they still insist,
  tell them `cli.py audit` will report the file as unapproved.
- Never set `CHELATE_UNSAFE_AUTO_APPROVE=1` (formerly `CHELATE_HUMAN`) and
  never run `cli.py approve` on the user's behalf. If an approval is needed,
  ask the human to issue it in their own terminal.
- Before telling the user a deliverable is ready — and after any write you
  make under `results/` — run `python cli.py audit --root <ws>`. Exit 1 means
  files there have no approval behind them: report that and name them, do not
  describe the state as delivered.
