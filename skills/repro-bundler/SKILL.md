---
name: repro-bundler
version: 1.4.0
description: >
  Packs a run's products, gates and versions into a deterministic zip and
  verifies it in memory.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# repro-bundler

Turns "these are my results" into "these are my results, and here is what they
were made from". The bundle carries the files, their SHA-256 digests, the gate
records that judged them, and the skill versions that produced them.

- **Stage:** `processors` · **Sandbox:** no · **Dependencies:** none (standard library)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action bundle --name paper-x
python run.py --root <WS> --action verify --bundle process/repro/paper-x-<stamp>.zip
```

- Bundles land in `<WS>/process/repro/`, the gate in `<WS>/process/gates/`.
- `--include` takes workspace-relative paths; the default is every file under
  `process/` except `gates/`, `repro/` and caches. Cap: 256 MiB.

## Verdicts

| Status | When |
| --- | --- |
| `PASS` | the bundle was written, or every listed file matches its digest |
| `FAIL` | a declared file is missing, the bundle is over the size limit, or verification finds missing / mismatched / unexpected / unsafe entries |
| `UNVERIFIED` | the path is not a zip, or has no manifest |

## Two properties worth knowing

- **Deterministic.** Sorted entries, fixed timestamps (1980-01-01) and modes
  (0644); the only clock value is in the manifest. Unchanged inputs produce
  byte-identical bundles.
- **Reads are hostile by default.** `verify` never extracts: it refuses the
  whole archive if any entry has an absolute path, a drive letter, a `..`
  component or is a symlink.

## When to use

- A result is about to leave the machine and must be checkable later.
- You received a bundle and want to know whether it is intact.

## When NOT to use

- You need the *input* files as well — a bundle carries `process/` products;
  input snapshots are recorded by digest in the manifest, not copied.

## More

- [bundle layout, outputs, failure handling and limits](references/repro-bundler-reference.md)
