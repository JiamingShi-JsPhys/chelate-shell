# Security report — through 1.4.0

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
Python policy layer can do on a filesystem the agent can write. 1.4.0 ships
the first half of what closing them needs — a broker holding the key, with
`submit` and `approve` on separate channels — and reports which half it got:
`cli.py status` prints `containment_detail`, `same-os-user` while the broker
shares the worker's account, `separate-os-user` once a second identity exists.
The worker still runs as the same user and `results/` is still an ordinary
directory, so A2 is not closed yet.

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
| Host integration | Claude Code, Codex, DSH, zcode, opencode | exercised manually in 1.3.5; not re-run since |

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

## What changed in 1.4.0, and what each change is worth

| Change | Closes | Does not close |
|---|---|---|
| Manifest paths refuse `:` and Windows device names; declared files are opened with `O_NOFOLLOW` where the platform has it | writing into an NTFS alternate data stream, publishing to `NUL`, and swapping a symlink between the link check and the open | a hardlink that already points outside the workspace — the tree check names it, it does not undo it |
| Approval bound to the manifest's digest and nonce; publication copies only the declared files, hashing as it copies | editing `process/` between approval and publication; publishing a file the manifest never named; spending an approval on a rebuilt manifest | a process that can reach the approve key and mint its own token (A2) |
| `Runtime.submit` is the only publication path; `pipeline`, `publish` and the MCP surface all go through it | a caller publishing by calling `router.promote` itself without the manifest checks | a caller that imports `router` directly — the same code is still importable in-process |
| Broker: two channels, separate 32-byte keys, fixed op sets, JSON bytes | an agent that has only reached the `submit` channel | a process running as the same user that reads the approve key — reported as `containment_detail: same-os-user` |
| `core/runtime.py`, fail-closed `BrokerRuntime` | a silent fall back to policy mode when no broker is running | a caller that instantiates `PolicyRuntime` directly; it is still the default backend |
| `contracts/action_manifest.py` validation | absolute paths, `..` escapes, stale expiry and a replayed nonce reaching the broker | an operator who reads a manifest instead of re-checking it |
| Hash-chained memory, written only by `cli.py memory add` | a later session treating an edited note as history | a person writing the wrong thing, correctly |
| Recipes run every step with `publish=False` | a recipe publishing by accident | a step that writes into `results/` itself |
| Hooks take argv only, scrubbed environment, non-blocking exit code | shell injection through a hook; an approval variable inheriting into it | a hook that is permitted to act and then acts badly |
| MCP exposes five tools, no approval and no memory write | an agent approving its own promotion over MCP | an agent calling `cli.py approve` directly |
| `egress` declares `controlled: false` and names the skills whose manifests declare `network` | a status report implying a firewall | the network calls themselves |
| `secret-gate` reports `path:line (rule, fingerprint)` | a credential reaching a gate record or a transcript | a credential outside a text file, or one already in `results/` |

### What the scanners said

`python -m deepsec shield scan . --layer all --no-remote-l3` over the release
tree reports one medium: `sast_ssrf_fetch_use` at
`lib/chelate_core/scholar_search.py`, "HTTP request appears to use a
user-controlled URL". That is true about the shape of the code — a search
phrase and a DOI both reach a URL — and not true about the risk, because the
host is a literal in all five templates: `_get` refuses anything whose scheme
is not `https` or whose host is not `api.crossref.org` /
`eutils.ncbi.nlm.nih.gov`, and `resolve_doi` refuses a string that is not a
DOI before a URL is built. Both checks have tests
(`tests/test_literature_sources.py`); the rule cannot see across them, so the
finding is reported here rather than suppressed with an ignore file.

## Known gaps, stated rather than implied

1. **`results/` is writable by anyone who can write the workspace.** The
   approval gate guards `promote()`; `cli.py audit` names what arrived another
   way. Prevention needs a filesystem boundary.
2. **The key is readable by the same user.** See A2. 1.4.0 splits the channel
   in code and reports the split as `same-os-user`; it is a control over code
   paths, not over processes.
3. **`process/gates/` is agent-writable.** A forged PASS with no digests is
   recorded as `unbound`, which is visible in `gate_freshness` but not blocked.
4. **No network egress control.** A skill that calls out is not stopped.
   Manifests can declare `network`, and `cli.py status` reports
   `egress: {controlled: false, declaring_network: [...]}` — a scope for the
   claim, not a control.
5. **Large inputs are bound by size, not by digest.** A same-size replacement
   is not detected; the gate says `large:<bytes>` rather than pretending.
6. **Only declared inputs are bound.** A config found by convention, an
   environment variable, a network response — none of it is covered.
7. **The sandbox whitelist includes `python`.** A whitelisted interpreter can
   do anything the account can.

## The 1.4.0 broker, as it stands in the tree

Not released, and not described above. What is implemented and tested:

- **Two channels.** `submit` serves `submit|audit|status|ping`; `approve`
  serves `approve|revoke|rotate|status|ping`. Each listener has its own
  32-byte authkey; the operation set is the control, a cross-channel call is
  refused and logged with its op and channel, and payloads are JSON bytes
  (never pickle).
- **Publication is the broker's.** `runtime.submit()` crosses IPC; the broker
  validates the manifest, checks the outputs' digests, consumes the one-time
  token, and calls `router.promote()` in its own process. `audit` crosses the
  same channel. No broker ⇒ `RuntimeUnavailable`, never policy mode.
- **What that is worth is conditional, and the report says which.** With the
  broker on the worker's own OS user, `containment_detail` reads
  `same-os-user`: the channel split constrains code paths, and a process that
  hunts the approve key defeats it. With a second identity it reads
  `separate-os-user`, which is the claim the design exists for. The mechanism
  behind the latter — a DACL naming Administrators and SYSTEM refusing an
  ordinary process — is exercised in `tests/test_broker.py` and skips where
  the account can rewrite the ACL.
- **Still missing before the claim holds:** the broker owning `results/` as
  an installer step, and the cross-user test in CI. Gap 1 is therefore
  narrowed, not closed.

## Statement

1.3.6 makes a run read frozen inputs, expire checks whose bytes changed, refuse
to publish what it could not verify, publish atomically, and revoke what it
issued. It does **not** contain a compromised agent, and no part of this
document claims otherwise. `docs/SAFETY.md` carries the same limits in the
narrative form; if the two disagree, this file is the one that is wrong.
