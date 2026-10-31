---
name: task-organizer
version: 1.2.0
description: >
  Mandatory entry point for task folders. Builds the standard four-zone
  workspace, files every deliverable by provenance, verifies each run with
  automatic rollback, and keeps the `_broadcast/` index that lets a later
  session read one summary instead of every original. Fires whenever a task
  folder is named or attached and work starts inside it.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# task-organizer

Builds and maintains the workspace skeleton — `material/initial/`,
`material/downloaded/`, `process/`, `results/` and `_broadcast/` — files each
deliverable by provenance, and verifies each run. It never edits the content of
your documents; it only decides where files belong.

- **Stage:** `workspace` · **Sandbox:** no · **Dependencies:** stdlib only (`openpyxl` adds the xlsx index, `PyYAML` the YAML rules)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action doctor
```

- `doctor` is read-only and always safe: it reports `healthy` or `incomplete`
  and writes nothing. Run it before asking the user anything.
- `init` creates the whole skeleton and lifts pre-existing content into
  `material/initial/`. It moves files, so **propose it once and wait for a
  yes** when the folder was merely referenced.
- Every run writes its gate to `<WS>/process/gates/task-organizer_<ts>.json`.

## When to use

- At session start on a known task folder — run `doctor` first.
- At task start on a new or empty folder, or on an explicit "set this up" request — run `init`.
- At final delivery — run `organize`, then `broadcast` (the index is mandatory, not optional).
- A fetched file must be declared provenance — `mark-downloaded`, so `material/downloaded/` means "the assistant fetched it" rather than a guess from the filename.

## When NOT to use

- No workspace has been chosen — do not organize an unnamed folder.
- The user declined the `init` proposal — carry on as asked, at most one proposal per folder.
- You were asked to summarize or describe this skill — that is a failure mode, not a result.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `doctor` | Read-only structure check | — |
| `init` | Build the four zones; pre-existing content moves to `material/initial/` | — |
| `organize` | Full pipeline: file, validate (C1–C8), verify, rollback on failure | `--mode full\|quick\|incremental` (after `--`) |
| `broadcast` | Rebuild the read-only `_broadcast/INDEX.md` | `--ai`, `--max-files N`, `--keywords K` |
| `index` | Alias of `broadcast` | same as `broadcast` |
| `snapshot` | Hash snapshot of the current tree | — |
| `dedupe` | Report duplicate files by content hash | — |
| `mark-downloaded` | Record a fetched file's source URL | `<file> --url <source-url>` |
| `mark-user` | Declare a file as user material | `<file>` |
| `undo / redo` | Reverse or replay a verified run | `<history_file>` |

## Hard constraints

- **Act, do not summarize.** A trigger under "When to use" means run the tool and report what it did.
- **Never move user material.** Only `init` relocates pre-existing content, and only after the user agrees.
- **A failed verification has already rolled back.** Report it; do not blindly re-run.

## Outputs

- `<WS>/process/gates/task-organizer_<ts>.json` — the gate result.
- `<WS>/_broadcast/INDEX.md` — the context-compression index.
- `<WS>/process/history/` — the reverse-able run history used by `undo`.

## Failure handling

- `verification: failed` — the tool restored the before-state already; report that and stop.
- A user-material name clash is left in place and reported, never overwritten.
- Hidden files, empty folders and symlinks are skipped by design.
- Exit `0` success, `2` usage or validation error.

## Limitations

- Filing is by provenance and name pattern, not by semantics.
- `broadcast` indexes what is on disk; it cannot judge whether a file is correct.
