# secret-gate

Find credentials that are about to leave the machine — in a commit, a package,
a Release zip or a screenshot — and report them **without printing them**.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

Nothing. Standard library only.

## Usage

```bash
python run.py --root <workspace> --action scan
python run.py --root <workspace> --action scan --path process/
python run.py --root <workspace> --action scan --allowlist .chelate/secret-allowlist.json
```

## What it finds

| Class | Examples |
|---|---|
| Credential shapes | AWS access keys, GitHub tokens, Slack tokens, Google API keys, `sk-` provider keys, PEM private-key headers |
| Assignments | `api_key = "…"`, `password: "…"`, `token = "…"` (16+ character value) |
| Entropy | 32+ character values on assignment lines with Shannon entropy ≥ 4.0 |

A finding is `path:line (rule, fingerprint)`. The fingerprint is
`sha256(secret)[:12]`: it lets the same string be recognised later and is
useless for using it.

## Allowlist

`.chelate/secret-allowlist.json` in the workspace:

```json
{"fingerprints": ["3f9a1c07b2d4"],
 "entries": [{"rule": "secret-assignment", "path": "docs/example.md"}]}
```

A single line can exempt itself with a `chelate-secret-allow` comment; see
[references/secret-gate-reference.md](references/secret-gate-reference.md).

## Verdicts

| Status | When |
|---|---|
| `PASS` | no unallowlisted credential shapes in the scanned files |
| `FAIL` | at least one finding |
| `UNVERIFIED` | nothing scannable under `--path` — zero files is not zero secrets |

## Outputs

| Path | Content |
|------|---------|
| `process/gates/secret-gate_<ts>.json` | gate result |
| `process/secret_scan_<ts>.json` | findings (path, line, rule, fingerprint, length) |

## Limits

A screen, not a secrets manager: split, encoded or compiled-in credentials are
out of scope, entropy has false positives (that is what the allowlist is for),
and git history is not read. The full list is in the reference.
