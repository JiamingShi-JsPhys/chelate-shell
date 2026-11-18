# repro-bundler — reference

## What is inside

| Entry | Content |
| --- | --- |
| `manifest.json` | bundle name, creation time, Python and platform, every file with size and SHA-256, the gate records, and skill name → version |
| `files/<path>` | the bundled products, at their workspace-relative paths |

## Outputs

- `<WS>/process/repro/<name>-<stamp>.zip` — the bundle.
- `<WS>/process/gates/repro-bundler_<ts>.json` — the gate result.

## Failure handling

- A declared `--include` path that does not exist ⇒ `FAIL`, naming the path.
- Over 256 MiB ⇒ `FAIL`; narrow `--include` rather than raising the cap.
- A non-zip or a zip without `manifest.json` ⇒ `UNVERIFIED`.
- An unsafe entry name in a bundle being verified ⇒ `FAIL` for the whole
  archive, never a partial pass.

## Limitations

- `process/` products only; inputs are recorded by digest, not copied.
- The manifest records the Python version of the machine that built it, not a
  pinned environment.
- A bundle proves integrity against the manifest, not that the manifest was
  honest when it was written — that is what the promotion log is for.

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
