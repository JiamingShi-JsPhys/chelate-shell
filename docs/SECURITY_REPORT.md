# Security report — 1.3.6

What this release measured, what it did not, and where the line is. Written
for a reader who will go looking for a containment claim and needs to find out
quickly that there isn't one.

Reproduce everything below with:

```bash
python -m pytest tests/test_irreversible_actions.py -q      # 26 adversarial cases
python -m pytest tests/test_promotion_integrity.py -q       # 17 promotion cases
python -m pytest tests/test_snapshots.py -q                 # 7 TOCTOU cases
python -m pytest tests/test_token_lifecycle.py -q           # 8 token cases
python -m pytest tests/test_path_hardening.py -q            # 6 link/special-file cases
python -m pytest tests/test_security_shield.py -q           # 26 injection cases
python -m pytest tests/test_results_audit.py -q             # 10 audit cases
python examples/graphene-tight-binding/run_demo.py          # end-to-end, 5 attacks
```

## Threat model — read this first

| Adversary | In scope? | What stops them |
|---|---|---|
| **A1.** An agent that works through the shell's own commands and flags, and tries the obvious bypasses (`--no-approval`, issuing its own token, editing a file after a check, replaying a spent token) | **Yes** | Policy checks in `core/approval.py` and `core/router.py` |
| **A2.** A process running as the same OS user that reads the signing key and sets `CHELATE_UNSAFE_AUTO_APPROVE=1` | **No** | Nothing. This is a working forgery in three lines, and the variable's name says so |
| **A3.** Another OS user, malware, a remote attacker | **No** | Nothing in this codebase. Out of scope by construction |

A2 and A3 are not a gap in the implementation; they are the boundary of what a
Python policy layer can do on a filesystem the agent can write. Closing them
needs a separate identity for the worker, a broker holding the key, and a
`results/` only the broker can write — the 1.4.0 target.

## Rates, measured inside the model

Definitions are the ones from the 1.3.6 plan, with the scope made explicit
because a rate without a threat model is a decoration.

**Unauthorized Execution Rate (UER)** — attempts by adversary A1 that succeeded,
divided by attempts made.

| Set | Attempts | Succeeded |
|---|---|---|
| `tests/test_irreversible_actions.py` | 26 | 0 |
| `tests/test_promotion_integrity.py` | 17 | 0 |
| `tests/test_snapshots.py` | 7 | 0 |
| `tests/test_path_hardening.py` | 6 | 0 |

**UER = 0% against A1.** Against A2 it is **100% by construction** — the key is
readable and the hatch is an environment variable. Reporting a single number
for both would be false, so there isn't one.

**Valid Authorization Success Rate (VASR)** — legitimate approvals that worked.

| Path | Result |
|---|---|
| Issue a token, run the pipeline, promote | promoted |
| Change an input, re-run the skill, approve again, promote | promoted (the expiry is cleared by the re-run, not by deleting the gate) |
| Rotate the key, issue a new token, promote | promoted |
| Approve with `--allow-unverified`, promote past an `UNVERIFIED` gate | promoted, override recorded |

**VASR = 100% on the four paths above**, which is the half a security change
usually breaks.

**Partial Publication Rate (PPR)** — interrupted promotions that left a
half-published deliverable.

| Fault injected | Result |
|---|---|
| `copytree` raises after copying half the tree | nothing under `results/` |
| A staging tree is left by an earlier crash | deleted before the next copy, never published |
| A FIFO in `process/` aborts the copy (POSIX) | nothing published; the next run starts clean |

**PPR = 0%.**

## Layers

| Layer | Content | Status |
|---|---|---|
| Unit | Approval binding, signatures, nonce consumption, path containment, gate status handling | pass |
| Integration | Router → adapter → gate → promotion, with real skills and a stub registry | pass |
| Adversarial | The 26-case matrix, plus replay, tampering, run-time hash swaps | all blocked |
| Concurrency | 20 processes racing one token (`test_token_lifecycle.py`) | exactly 1 winner, 19 refusals |
| Crash recovery | Mid-copy abort, leftover staging, special file | no partial publication |
| Platform | Windows 11, Python 3.10/3.12 | pass; POSIX-only cases skip and are marked |
| Host integration | Claude Code, Codex, DSH, zcode, opencode | exercised manually in 1.3.5; not re-run in 1.3.6 |

## What changed in 1.3.6, and what each change is worth

| Change | Closes | Does not close |
|---|---|---|
| Gates record input digests and skill code; a PASS expires | editing an input after the check; replacing the skill's code | a file the adapter opens without being told about it |
| Inputs are snapshotted before dispatch | an edit between the hash and the skill's `open()` | inputs above 256 MiB, which are bound by size |
| Promotion is staged and renamed | half-published deliverables | writing into `results/` by hand (still only detected) |
| `UNVERIFIED` blocks promotion unless a person bound the override into the token | a missing dependency quietly delivering a result | a gate forged in `process/gates/` |
| Scripted hatch renamed `CHELATE_UNSAFE_AUTO_APPROVE` | a reader mistaking it for proof that a person was present | an agent setting it |
| `revoke` / `rotate-key` | a leaked token; a key that may have been read | a token spent before the revocation |
| Chinese, homoglyph, HTML-comment and base64 injection patterns | the screen doing nothing for Chinese input | a novel phrasing no pattern covers |
| Symlink and hardlink refusal at promotion | `process/leak -> /etc/shadow` landing in `results/` | a file copied in rather than linked |

## Known gaps, stated rather than implied

1. **`results/` is writable by anyone who can write the workspace.** The
   approval gate guards `promote()`; `cli.py audit` names what arrived another
   way. Prevention needs a filesystem boundary.
2. **The key is readable by the same user.** See A2.
3. **`process/gates/` is agent-writable.** A forged PASS with no digests is
   recorded as `unbound`, which is visible in `gate_freshness` but not blocked.
4. **No network egress control.** A skill that calls out is not stopped.
5. **Large inputs are bound by size, not by digest.** A same-size replacement
   is not detected; the gate says `large:<bytes>` rather than pretending.
6. **Only declared inputs are bound.** A config found by convention, an
   environment variable, a network response — none of it is covered.
7. **The sandbox whitelist includes `python`.** A whitelisted interpreter can
   do anything the account can.

## Statement

1.3.6 makes a run read frozen inputs, expire checks whose bytes changed, refuse
to publish what it could not verify, publish atomically, and revoke what it
issued. It does **not** contain a compromised agent, and no part of this
document claims otherwise. `docs/SAFETY.md` carries the same limits in the
narrative form; if the two disagree, this file is the one that is wrong.
