---
name: secret-gate
version: 1.4.0
description: >
  Scans a tree for credential shapes and reports fingerprints, never the
  secret itself.
metadata:
  version: 1.4.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# secret-gate

Finds credentials that were about to be committed, packaged or pasted into a
report — and reports them without printing them.

- **Stage:** `gates` · **Sandbox:** no · **Dependencies:** none (standard library)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action scan [--path process/]
```

- Scans text files under `--path` (default: the workspace root), skipping
  `.git`, dependency caches and build output.
- A finding is reported as `path:line (rule, fingerprint)`; the matched string
  never appears in the gate, the report, stdout or this conversation.
- The report lands in `<WS>/process/secret_scan_<ts>.json`; the gate in
  `<WS>/process/gates/secret-gate_<ts>.json`.

## What it checks

| Class | Examples |
|---|---|
| Credential shapes | AWS access keys, GitHub tokens, Slack tokens, Google API keys, `sk-` keys, `-----BEGIN … PRIVATE KEY-----` |
| Assignments | `api_key = "…"`, `password: "…"`, `token = "…"` with a value of 16+ characters |
| Entropy | a 32+ character string assigned on a `key = value` line whose Shannon entropy is ≥ 4.0 bits/char |

## Verdicts

| Status | When |
| --- | --- |
| `PASS` | every scanned file is free of unallowlisted credential shapes |
| `FAIL` | at least one finding; the reason names `path:line`, rule and fingerprint |
| `UNVERIFIED` | there was nothing scannable under `--path` |

## When to use

- Before a commit, an npm/PyPI pack, a Release zip or a screenshot of a
  config file.
- Before handing a workspace to someone else.
- As the last gate in a pipeline whose outputs are going to travel.

## When NOT to use

- You want to know whether an *installed* package's key is valid — this gate
  never calls the provider; it only reads files.
- You are scanning a binary blob: binaries are skipped, so a key compiled
  into an executable is out of scope (the pack-time sweep in `docs/SAFETY.md`
  is the place for that).

## More

- [rules, allowlist, limits and outputs](references/secret-gate-reference.md)
