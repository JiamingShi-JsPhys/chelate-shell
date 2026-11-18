"""One-time approval tokens for irreversible actions.

The problem this module addresses is not a remote attacker: it is an agent
that has been given a job and keeps going past the point where a human would
have stopped.  Every irreversible step therefore needs a token that a human
had to create beforehand, and that can be spent exactly once.

What is protected
-----------------
* ``promote`` — copying ``process/`` into ``results/``.  This is the one
  irreversible step the *agent-facing* entry point (``cli.py pipeline``)
  performs on its own initiative: it hardens provisional intermediates into
  deliverables.

Actions the user starts directly — ``cli.py run``, and the multi-dim-manager
plugin sweep — are not gated here: the human who typed the command is the
approval.  Add an action to ``IRREVERSIBLE_ACTIONS`` when an agent can reach
it without a human in the loop.

Threat model, stated plainly
----------------------------
Approval has to come from somewhere the agent's own process does not control,
so two things were moved out of its reach:

* the signing key no longer lives in the workspace (see *Key layout* below);
* issuing a token requires a **human channel** — an interactive terminal, or
  an explicit ``CHELATE_UNSAFE_AUTO_APPROVE=1`` for a supervised scripted run.
  An agent subprocess has neither, so it cannot call ``issue()``, ``cli.py
  approve``, or ``--no-approval`` at all.

The second half of that sentence is policy, not enforcement, and 1.3.6 names
it that way instead of hiding behind a friendlier variable name.  An agent
that can set an environment variable on the process it spawns can set
``CHELATE_UNSAFE_AUTO_APPROVE=1``; a process running as the same OS user can
read the key file.  Together that is a complete forgery, in three lines, and
no in-process policy layer can prevent it.  What the control buys is the
distinction between a workflow that stayed inside the shell and one that
went around it — plus an audit trail that says which happened.

Real containment needs an OS boundary: a separate user for the worker, keys
the worker cannot read, a protected results directory only the issuer can
write.  That is planned for 1.4.0, not claimed here.

Key layout
----------
``<data-dir>/chelate/keys/<sha256(realpath(workspace))[:16]>.key``
    32 random bytes, hex, mode 0600.  ``<data-dir>`` is ``%LOCALAPPDATA%`` on
    Windows and ``$XDG_DATA_HOME`` (default ``~/.local/share``) elsewhere.
    Outside the workspace on purpose: the workspace is the directory the
    agent is allowed to write.

Token layout
------------
``<workspace>/.chelate/approvals/<action>-<nonce>.json``
    ``{v, action, workspace, params_sha256, issued, expires, nonce, mac}``
    where ``mac = HMAC-SHA256(key, canonical_json(payload))``.  A token is
    useless without the key, so it can stay in the workspace where a human
    can see what was issued.

Consumption renames the token with ``O_CREAT|O_EXCL`` before deleting it, so
two concurrent consumers cannot both succeed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

IRREVERSIBLE_ACTIONS = ("promote",)
DEFAULT_TTL_SECONDS = 900  # 15 minutes: long enough for a pipeline, short
                           # enough that a stale approval cannot be replayed
_TOKEN_VERSION = 1
_STATE_DIR = ".chelate"
_APPROVALS_DIR = "approvals"
_HUMAN_ENV = "CHELATE_UNSAFE_AUTO_APPROVE"
UNSAFE_AUTO_ENV = _HUMAN_ENV
_LEGACY_UNSAFE_ENV = "CHELATE_HUMAN"


class ApprovalRequired(RuntimeError):
    """Raised when an irreversible action has no valid, unused approval."""


class ApprovalInvalid(RuntimeError):
    """Raised when a token exists but is malformed, expired, or replayed."""


class HumanRequired(RuntimeError):
    """Raised when approval is requested with no human channel present."""


# ------------------------------------------------------------ human channel

_CONFIRM_PHRASE = "approve promote"


def _human_channel(action: str = "promote") -> bool:
    """True when a person has just authorised *action* at the keyboard.

    A TTY alone is not enough.  A subprocess an agent spawns often inherits
    the terminal, so ``isatty()`` says nothing about who is reading.  What an
    agent does not normally do is *type an answer*: this asks the person to
    type ``approve promote``, and treats EOF (a pipe or a closed stdin) as a
    refusal.

    ``CHELATE_UNSAFE_AUTO_APPROVE=1`` is the scripted hatch, and its name is
    the warning: it is an environment variable, and anything that can set an
    environment variable on a process it spawns — an agent included — can set
    this one.  Treat it as a declaration made by whoever wrote the job, not
    as proof that a person was watching.  It is kept for CI because the
    alternative there is a broken job, not a safer one.

    This raises the cost of the bypass; it does not make it impossible.  A
    process running as the same user can read the prompt and type the answer,
    and can set the variable above.  That is the disclosed boundary — see the
    module docstring and docs/SAFETY.md.
    """
    if unsafe_auto_declared():
        return True
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        interactive = False
    if not interactive:
        return False
    print(f"Chelate Shell is about to authorise {action!r}. "
          f"Type `{_CONFIRM_PHRASE}` to continue, anything else to refuse: ",
          end="", file=sys.stderr, flush=True)
    try:
        answer = input()
    except EOFError:
        print("", file=sys.stderr)
        return False
    return answer.strip() == _CONFIRM_PHRASE


def unsafe_auto_declared() -> bool:
    """True when the scripted hatch was declared in this process's environment.

    Read from the environment on purpose: it is a *declaration*, and a
    declaration is exactly what an agent can also make.  Nothing downstream
    may describe a run authorised this way as "human-approved".
    """
    if os.environ.get(UNSAFE_AUTO_ENV) == "1":
        return True
    if os.environ.get(_LEGACY_UNSAFE_ENV) == "1":
        print(f"warning: {_LEGACY_UNSAFE_ENV} is the pre-1.3.6 name of "
              f"{UNSAFE_AUTO_ENV}; it still works and means the same thing — "
              f"no person is verifying this run at the keyboard",
              file=sys.stderr)
        return True
    return False


def require_human(what: str, action: str = "promote") -> None:
    """Raise ``HumanRequired`` unless an approval may be issued right now."""
    if _human_channel(action):
        return
    raise HumanRequired(
        f"{what} needs a human at the keyboard: run it from an interactive "
        f"terminal and type the confirmation, or set {UNSAFE_AUTO_ENV}=1 for "
        f"a supervised scripted run")


# --------------------------------------------------------------- key handling

def state_dir(workspace: str) -> Path:
    """Workspace directory holding unused tokens and pipeline state."""
    path = Path(workspace).resolve() / _STATE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _approvals_dir(workspace: str) -> Path:
    path = state_dir(workspace) / _APPROVALS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _key_root() -> Path:
    """Per-user data directory, outside any workspace the agent can write.

    ``CHELATE_KEY_ROOT`` overrides it, which is how the test suite stays
    hermetic instead of littering the user's real key directory.
    """
    override = os.environ.get("CHELATE_KEY_ROOT")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or \
            str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or \
            str(Path.home() / ".local" / "share")
    return Path(base) / "chelate" / "keys"


def _key_path(workspace: str) -> Path:
    """One key per workspace, named by the resolved path's digest."""
    ident = hashlib.sha256(
        os.path.realpath(str(workspace)).encode("utf-8")).hexdigest()[:16]
    return _key_root() / f"{ident}.key"


def _load_key(workspace: str, create: bool = False) -> bytes:
    path = _key_path(workspace)
    if path.is_file():
        try:
            return bytes.fromhex(path.read_text(encoding="utf-8").strip())
        except ValueError as exc:
            raise ApprovalInvalid(f"approval key is corrupt: {path}") from exc
    if not create:
        raise ApprovalRequired(
            "this workspace has no approval key yet; a human must run "
            "`python cli.py approve ...` in it first")
    root = path.parent
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    key = secrets.token_bytes(32)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # a concurrent issuer won the race
        return _load_key(workspace)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key.hex())
    return key


def has_key(workspace: str) -> bool:
    """True once this workspace has a signing key (an approval happened)."""
    return _key_path(workspace).is_file()


def _retired_keys(workspace: str) -> List[Path]:
    """Keys this workspace used before the last rotation, newest first.

    They stay readable so signatures written before a rotation still verify:
    rotating a key must not turn yesterday's promotion log into "tampered".
    They are never used to *sign* anything new.
    """
    current = _key_path(workspace)
    prefix = current.name[: -len(".key")] + ".retired-"
    try:
        found = sorted(current.parent.glob(prefix + "*.key"), reverse=True)
    except OSError:
        return []
    return found


def _read_key(path: Path) -> Optional[bytes]:
    try:
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def rotate(workspace: str) -> Dict[str, Any]:
    """Replace this workspace's signing key; retire the old one.

    Every token issued before the rotation stops verifying, which is the
    point: a key that may have been read by someone else cannot be trusted
    again, and the only remedy is a key they never saw. Promotion log entries
    written under the old key keep verifying, because the old key is retired
    rather than deleted.

    Returns ``{"rotated": True, "key": <path>, "retired": <path or "">,
    "tokens_invalidated": <count>}``.
    """
    require_human("rotating the approval key", "promote")
    path = _key_path(workspace)
    retired_name = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    if path.is_file():
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        retired = path.parent / f"{path.name[:-len('.key')]}.retired-{stamp}.key"
        os.replace(path, retired)
        retired_name = str(retired)
    key = secrets.token_bytes(32)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key.hex())
    return {"rotated": True, "key": str(path), "retired": retired_name,
            "tokens_invalidated": revoke(workspace)}


def revoke(workspace: str, action: str = "promote") -> int:
    """Delete unused approvals for this workspace; return how many went.

    An issued token is a bearer instrument with a 15-minute life. Revoking
    removes the ones not yet spent, so a token that leaked — pasted into a
    chat, caught in a log, left in a shared folder — stops being spendable
    now rather than when it expires. Tokens already consumed cannot be
    revoked and do not need to be: consumption is one-way.
    """
    folder = Path(workspace).resolve() / _STATE_DIR / _APPROVALS_DIR
    if not folder.is_dir():
        return 0
    pattern = f"{action}-*.json" if action else "*.json"
    removed = 0
    for path in folder.glob(pattern):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def sign(workspace: str, payload: Dict[str, Any],
         create: bool = False) -> Optional[str]:
    """HMAC-SHA256 of a canonical payload with this workspace's key.

    Returns ``None`` when the workspace has no key and *create* is false —
    the caller decides whether an unsigned record is acceptable.
    """
    try:
        key = _load_key(workspace, create=create)
    except ApprovalRequired:
        return None
    return hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()


def verify(workspace: str, payload: Dict[str, Any], mac: str) -> bool:
    """Constant-time check of a ``sign()`` result; False if no key fits.

    Tries the current key first, then every retired one: a rotation must
    invalidate *tokens* (they are checked against the current key only), not
    the promotion log written before it.
    """
    candidates: List[Path] = [_key_path(workspace)] + _retired_keys(workspace)
    for candidate in candidates:
        key = _read_key(candidate)
        if not key:
            continue
        expected = hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, str(mac)):
            return True
    return False


# ------------------------------------------------------------------ canonical

def canonical(payload: Any) -> bytes:
    """Stable JSON encoding used for both signing and comparison."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("utf-8")


def params_digest(params: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical(params)).hexdigest()


def pipeline_params(mode: str, input_kind: str,
                    inputs: Optional[Iterable[str]],
                    selected: Optional[Iterable[str]],
                    allow_unverified: bool = False) -> Dict[str, Any]:
    """Parameters a ``promote`` approval is bound to.

    Deliberately includes the content hash of every input: an approval issued
    for a draft cannot be spent on a different file that happens to have the
    same name.

    ``allow_unverified`` is part of the binding on purpose.  Accepting an
    unverified gate is a decision a person makes, not a switch a caller flips
    after the token was issued: a token minted for the strict path cannot be
    spent on a run that would carry an unchecked result into ``results/``.
    """
    files = []
    for path in sorted(str(p) for p in (inputs or [])):
        try:
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError:
            digest = None
        files.append({"path": os.path.basename(path), "sha256": digest})
    return {
        "mode": mode,
        "input_kind": input_kind,
        "selected": sorted(str(s) for s in (selected or [])),
        "inputs": files,
        "allow_unverified": bool(allow_unverified),
    }


# ------------------------------------------------------------------- issuing

def issue(workspace: str, action: str, params: Dict[str, Any],
          ttl: int = DEFAULT_TTL_SECONDS,
          manifest_sha256: str = "", nonce: str = "") -> Path:
    """Create a one-time token for *action* and return its path.

    Requires a human channel: this is the signature the whole control rests
    on, so it is not reachable from an agent subprocess.
    """
    require_human(f"issuing an approval for {action!r}", action)
    token = mint(workspace, action, params, ttl=ttl,
                 manifest_sha256=manifest_sha256, nonce=nonce)
    return _approvals_dir(workspace) / f"{action}-{token['nonce']}.json"


def mint(workspace: str, action: str, params: Dict[str, Any],
         ttl: int = DEFAULT_TTL_SECONDS,
         manifest_sha256: str = "", nonce: str = "") -> Dict[str, Any]:
    """Sign and write a token, with no human-channel check of its own.

    Two callers exist and each makes that check where it can actually be
    made: `issue()` requires a terminal in the caller's process, and the
    broker's approve channel answers only the CLI that reached the approve
    channel. A third caller would need a third argument, not a quiet reuse.

    ``manifest_sha256`` binds the token to one exact manifest. A caller that
    publishes must present a manifest whose digest matches; a token minted
    for a different set of bytes cannot be spent on this one.
    """
    if action not in IRREVERSIBLE_ACTIONS:
        raise ValueError(f"unknown irreversible action: {action!r}")
    if not ttl or ttl <= 0:
        raise ValueError("approval ttl must be a positive number of seconds")
    # An approval for a manifest adopts that manifest's nonce: the token and
    # the manifest must name the same act, and the digest — which covers the
    # nonce — is what the broker compares.
    if nonce and (len(nonce) != 32 or set(nonce.lower()) - set("0123456789abcdef")):
        raise ValueError(f"nonce {nonce!r} is not 32 hex characters")
    key = _load_key(workspace, create=True)
    payload = {
        "v": _TOKEN_VERSION,
        "action": action,
        "workspace": os.path.realpath(str(workspace)),
        "params_sha256": params_digest(params),
        "issued": int(time.time()),
        "expires": int(time.time()) + int(ttl),
        "nonce": str(nonce) or secrets.token_hex(16),
        "manifest_sha256": str(manifest_sha256 or ""),
    }
    token = {**payload,
             "mac": hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()}
    path = _approvals_dir(workspace) / f"{action}-{payload['nonce']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(token, indent=2, sort_keys=True),
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return token


# ---------------------------------------------------------------- consuming

def _token_files(workspace: str, action: str) -> List[Path]:
    folder = _approvals_dir(workspace)
    return sorted(folder.glob(f"{action}-*.json"))


def _verify(token: Dict[str, Any], key: bytes, workspace: str,
            action: str, params: Dict[str, Any],
            manifest_sha256: Optional[str] = None,
            require_binding: bool = False) -> None:
    if token.get("v") != _TOKEN_VERSION:
        raise ApprovalInvalid(f"unsupported token version: {token.get('v')!r}")
    if token.get("action") != action:
        raise ApprovalInvalid(
            f"token is for {token.get('action')!r}, not {action!r}")
    expected = hmac.new(key, canonical({k: v for k, v in token.items()
                                        if k != "mac"}),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(token.get("mac", "")), expected):
        raise ApprovalInvalid("token signature does not match")
    if token.get("workspace") != os.path.realpath(str(workspace)):
        raise ApprovalInvalid("token was issued for a different workspace")
    if token.get("params_sha256") != params_digest(params):
        raise ApprovalInvalid(
            "token was issued for a different plan; re-approve the current "
            "mode/selection/inputs")
    expires = token.get("expires")
    if not isinstance(expires, int) or expires < int(time.time()):
        raise ApprovalInvalid("token has expired")
    # The plan digest says which inputs and mode were approved; the manifest
    # digest says which bytes may be published. A token carrying one cannot
    # be spent by a caller that cannot present it, and a caller that requires
    # the binding refuses a token minted without it.
    bound = str(token.get("manifest_sha256") or "")
    if bound:
        if not manifest_sha256:
            raise ApprovalInvalid(
                "token is bound to a manifest; pass the manifest digest it "
                "was issued for")
        if bound != str(manifest_sha256):
            raise ApprovalInvalid(
                "token was issued for a different manifest; the files or the "
                "skill set changed since it was approved")
    elif require_binding:
        raise ApprovalInvalid(
            "token carries no manifest binding; approve the current manifest "
            "with `cli.py approve --root <ws>`")


def _claim(path: Path) -> bool:
    """Atomically take ownership of *path*; True when this caller won."""
    claim = path.with_suffix(".claimed")
    try:
        fd = os.open(str(claim), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    os.close(fd)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return True


def consume(workspace: str, action: str, params: Dict[str, Any],
            manifest_sha256: Optional[str] = None,
            require_binding: bool = False) -> Dict[str, Any]:
    """Spend one valid token for *action*; raise when there is none.

    ``manifest_sha256`` is the digest of the manifest the caller is about to
    publish. When the token was minted with a binding, it must match; when
    ``require_binding`` is set, an unbound token is refused as well, so a
    caller on the publication path cannot fall back to a weaker token.
    """
    if action not in IRREVERSIBLE_ACTIONS:
        raise ValueError(f"unknown irreversible action: {action!r}")
    key = _load_key(workspace)  # raises ApprovalRequired when absent
    last_error: Optional[ApprovalInvalid] = None
    for path in _token_files(workspace, action):
        try:
            token = json.loads(path.read_text(encoding="utf-8"))
            _verify(token, key, workspace, action, params,
                    manifest_sha256=manifest_sha256,
                    require_binding=require_binding)
        except (OSError, ValueError, ApprovalInvalid) as exc:
            last_error = exc if isinstance(exc, ApprovalInvalid) else \
                ApprovalInvalid(f"unreadable token {path.name}: {exc}")
            continue
        if not _claim(path):
            continue  # another consumer spent it first
        return token
    detail = f" ({last_error})" if last_error else ""
    raise ApprovalRequired(
        f"{action} needs a fresh approval{detail}; run "
        f"`python cli.py approve ...` and retry")
