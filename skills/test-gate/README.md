# test-gate

Run the project's declared test command and gate on the result it actually
printed — `FAIL` on a red summary or a non-zero exit, `UNVERIFIED` when no
test ran or the time budget ran out.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

Nothing. Standard library only.

## Usage

```bash
python run.py --root <workspace> --action run
python run.py --root <workspace> --action run \
    --command '["python","-m","pytest","-q"]'
python run.py --root <workspace> --action run --input tests --timeout 60
```

## Declaration

`.chelate/test-gate.json` in the workspace:

```json
{"command": ["python", "-m", "pytest", "-q"], "timeout": 90}
```

`command` is an argument list, never a string: no shell is involved, and
`command[0]` must pass the sandbox executable whitelist. Unknown keys are
refused rather than ignored.

## What it will not do

- **Pass a run that collected nothing.** `no tests ran`, `collected 0 items`
  and `Ran 0 tests` are UNVERIFIED, whatever the exit code says.
- **Be fooled by a wrapper.** When the output counts failures, that count
  beats a green exit code.
- **Pass a command that merely exited 0.** With no readable summary in its
  output the verdict is UNVERIFIED, not PASS.
- **Blame the code for a timeout.** Running past the declared budget is
  UNVERIFIED: the result is unknown, which is not a failure.

## Outputs

| Path | Content |
|------|---------|
| `process/gates/test-gate_<ts>.json` | gate result (PASS / FAIL / UNVERIFIED) |
| `process/test_report_<ts>.json` | argv, cwd, exit code, seconds, parsed counts, summary line, and the last 40 lines of stdout |

## Notes

The gate runs inside the Router's isolated process, and its own `timeout`
should stay below that budget (120 s by default) so it can report why it
stopped instead of being killed.
