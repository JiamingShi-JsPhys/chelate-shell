# secret-gate — reference

Everything the one-screen SKILL.md leaves out: the rule set, the allowlist
format, the line pragma, outputs and limits.

## Rules

| Rule | Matches |
|---|---|
| `private-key-block` | `-----BEGIN [RSA/EC/DSA/OPENSSH/PGP ]PRIVATE KEY-----` |
| `aws-access-key` | `AKIA…` / `ASIA…` followed by 16 uppercase alphanumerics |
| `github-token` | `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_` + 36+ characters |
| `slack-token` | `xoxb-`, `xoxa-`, `xoxp-`, `xoxr-`, `xoxs-` |
| `google-api-key` | `AIza` + 35 characters |
| `provider-key` | `sk-` / `sk-ant-` + 20+ characters |
| `secret-assignment` | a key-ish name (`api_key`, `secret`, `token`, `password`, …) assigned a 16+ character value |
| `high-entropy-string` | a 32+ character value assigned on a `key = value` line with Shannon entropy ≥ 4.0 bits/char |

Shape rules run first and win the line; the assignment and entropy rules only
see lines no shape rule matched, so one credential is never reported twice.

## Allowlist

Default path: `<workspace>/.chelate/secret-allowlist.json`.

```json
{
  "fingerprints": ["3f9a1c07b2d4"],
  "entries": [
    {"rule": "secret-assignment", "path": "docs/example.md"},
    {"rule": "high-entropy-string", "path": "tests/fixtures/sample.py"}
  ]
}
```

- `fingerprints` suppress one exact string wherever it appears; the value is
  what the gate printed, so an allowlist is written by copying a finding, not
  by pasting the secret.
- `entries` suppress a rule within one file; omitting `rule` suppresses every
  rule in that file.
- An allowed finding is still counted: the `PASS` reason says
  `N allowlisted`, so a growing allowlist is visible rather than silent.

## Line pragma

A line containing `chelate-secret-allow` is exempt for that line only. With
`chelate-secret-allow: <rule>` only that rule is exempt. This is meant for
fixtures that must contain a fake key; it is an edit in the file under review,
so it shows up in a diff.

## What is scanned

- Any file that decodes as UTF-8 (NUL byte in the first 8 KiB ⇒ skipped).
- Skipped directories: `.git`, `.hg`, `.svn`, `node_modules`, `__pycache__`,
  `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.venv`, `venv`, `env`,
  `dist`, `build`, `.tox`, `.idea`, `.vscode`, `site-packages`.
- Files over 2 MiB and symlinks are skipped.

## Outputs

| Path | Content |
|---|---|
| `process/gates/secret-gate_<ts>.json` | gate result (PASS / FAIL / UNVERIFIED) |
| `process/secret_scan_<ts>.json` | every finding: path, line, rule, fingerprint, length |

## Failure handling

- A path outside the workspace is refused (`ensure_within`).
- An unreadable file is skipped, not failed; the count in the reason says how
  many files were actually scanned.
- No scannable files ⇒ `UNVERIFIED` — never a PASS, because zero files checked
  is not evidence of zero secrets.

## Limits — what this does not do

- **It is a screen, not a secrets manager.** A credential split across lines,
  base64-encoded, or stored in a binary is not detected.
- **Entropy has false positives.** Hash constants, base64 fixtures and long
  identifiers trip it; the allowlist exists for exactly that and says so.
- **A fingerprint is not proof of no leak elsewhere.** It identifies a string
  so the same one can be found again; it says nothing about where else it was
  copied.
- **No git history.** Only the working tree is read; a key deleted in a later
  commit is still in history, and `git log -S` remains the tool for that.

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
