# code-gate — reference

## The rules

| Rule | Why it is a finding |
| --- | --- |
| `syntax-error` | the file does not parse, so nothing else about it is checked |
| `bare-except` | `except:` also catches `KeyboardInterrupt` and `SystemExit` |
| `swallowed-error` | `except X: pass` discards the failure it caught |
| `mutable-default` | a list/dict/set default is shared by every call |
| `eq-none` | `== None` is False for any object that overrides `__eq__` |
| `star-import` | `from x import *` hides where a name came from |
| `long-function` | past `--max-lines` (80) a function stops being reviewable |
| `too-many-args` | past `--max-args` (7) a call site needs a structure |

## The boundaries, stated

- **No severity slider, no "all linters" mode.** A rule set that depends on
  which package is installed gives two machines two verdicts for one file.
- **`--ruff` is opt-in.** When it runs, the report records the ruff version
  and the exact `--select`/`--ignore` it was given.
- **Dangerous calls are `security-guard`'s job**, not this gate's. Screening
  `eval`/`exec`/`subprocess` twice would give two answers to one question.

## Outputs

- `<WS>/process/gates/code-gate_<ts>.json` — the gate result.
- `<WS>/process/code_report_<ts>.json` — every finding with path, line, rule
  and the source line it came from.

## Failure handling

- An unreadable file is a finding, not a crash.
- No Python files under the target ⇒ `UNVERIFIED` (nothing was checked).
- A target outside the workspace is refused by `ensure_within`.

## Limitations

- Eight shapes only; anything else is out of scope by design.
- The parser is CPython's; syntax valid only under newer versions is a
  `syntax-error` here if this interpreter cannot parse it.
- Ruff reports are recorded, not normalised — two versions can differ.

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
