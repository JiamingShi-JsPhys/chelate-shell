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
  an explicit ``CHELATE_HUMAN=1`` for a supervised scripted run.  An agent
  subprocess has neither, so it cannot call ``issue()``, ``cli.py approve``,
  or ``--no-approval`` at all.

What is left is the disclosed boundary: a process running as the same OS user
that goes looking for the key file *and* sets ``CHELATE_HUMAN=1`` can still
forge approval.  That is a process that has decided to defeat the control,
and no in-process policy layer can stop it.  Real containment needs an OS
boundary: a separate user, a container, a syscall filter.

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
_HUMAN_ENV = "CHELATE_HUMAN"


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
    refusal.  ``CHELATE_HUMAN=1`` is the declared escape hatch for CI, where
    a human supervises the run but nothing is attached.

    This raises the cost of the bypass; it does not make it impossible.  A
    process running as the same user with a terminal *can* read the prompt
    and type the answer.  That is the disclosed boundary — see the module
    docstring and docs/SAFETY.md.
    """
    if os.environ.get(_HUMAN_ENV) == "1":
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


def require_human(what: str, action: str = "promote") -> None:
    """Raise ``HumanRequired`` unless an approval may be issued right now."""
    if _human_channel(action):
        return
    raise HumanRequired(
        f"{what} needs a human at the keyboard: run it from an interactive "
        f"terminal and type the confirmation, or set {_HUMAN_ENV}=1 for a "
        f"supervised scripted run")


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


# ------------------------------------------------------------------ canonical

def canonical(payload: Any) -> bytes:
    """Stable JSON encoding used for both signing and comparison."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("utf-8")


def params_digest(params: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical(params)).hexdigest()


def pipeline_params(mode: str, input_kind: str,
                    inputs: Optional[Iterable[str]],
                    selected: Optional[Iterable[str]]) -> Dict[str, Any]:
    """Parameters a ``promote`` approval is bound to.

    Deliberately includes the content hash of every input: an approval issued
    for a draft cannot be spent on a different file that happens to have the
    same name.
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
    }


# ------------------------------------------------------------------- issuing

def issue(workspace: str, action: str, params: Dict[str, Any],
          ttl: int = DEFAULT_TTL_SECONDS) -> Path:
    """Create a one-time token for *action* and return its path.

    Requires a human channel: this is the signature the whole control rests
    on, so it is not reachable from an agent subprocess.
    """
    require_human(f"issuing an approval for {action!r}", action)
    if action not in IRREVERSIBLE_ACTIONS:
        raise ValueError(f"unknown irreversible action: {action!r}")
    if not ttl or ttl <= 0:
        raise ValueError("approval ttl must be a positive number of seconds")
    key = _load_key(workspace, create=True)
    payload = {
        "v": _TOKEN_VERSION,
        "action": action,
        "workspace": os.path.realpath(str(workspace)),
        "params_sha256": params_digest(params),
        "issued": int(time.time()),
        "expires": int(time.time()) + int(ttl),
        "nonce": secrets.token_hex(16),
    }
    token = {**payload,
             "mac": hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()}
    path = _approvals_dir(workspace) / f"{action}-{payload['nonce']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(token, indent=2, sort_keys=True),
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------- consuming

def _token_files(workspace: str, action: str) -> List[Path]:
    folder = _approvals_dir(workspace)
    return sorted(folder.glob(f"{action}-*.json"))


def _verify(token: Dict[str, Any], key: bytes, workspace: str,
            action: str, params: Dict[str, Any]) -> None:
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


def consume(workspace: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Spend one valid token for *action*; raise when there is none."""
    if action not in IRREVERSIBLE_ACTIONS:
        raise ValueError(f"unknown irreversible action: {action!r}")
    key = _load_key(workspace)  # raises ApprovalRequired when absent
    last_error: Optional[ApprovalInvalid] = None
    for path in _token_files(workspace, action):
        try:
            token = json.loads(path.read_text(encoding="utf-8"))
            _verify(token, key, workspace, action, params)
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
