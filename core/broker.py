"""The broker — the process that holds the key and writes `results/`.

Caller: `cli.py broker …` (starts and talks to it), `core/runtime.BrokerRuntime`
        (submits), tests/test_broker.py.

Data schemas:
    State:  <workspace>/.chelate/broker/
                submit.key    random bytes, read by the worker's submit client
                approve.key   random bytes, read by the human's approve CLI
                keys/         approval signing key (approval.KEY_ROOT)
                broker.json   {pid, started, version, workspace, results}
                log.jsonl     one line per accepted or refused request
    Wire:   newline-free JSON over `multiprocessing.connection` byte channels,
            one request and one reply per message. **No pickle**: the broker
            deserialises JSON only, so a peer that can connect cannot hand it
            an object graph.

Design — why this file exists at all.

    In 1.3.6 the promotion code ran **inside the agent's process**: the same
    process that could read the signing key also called `router.promote`.
    Approval was a policy boundary and said so. The broker's job is to remove
    that code path from the worker: the worker can now *ask* for a
    publication, and only the broker runs it.

    Two channels, because one door would leave the design as it was. The
    submit channel serves the worker and refuses `approve`; the approve
    channel serves a human's CLI and serves nothing else. A single channel
    would let an agent connect again and mint its own approval — the exact
    attack the split exists to stop. Refusals are logged (op, channel), so a
    probe is visible afterwards even when it changed nothing.

    What this does **not** do, stated here rather than discovered later: on
    one OS account the worker can read `approve.key` and rewrite the DACL,
    exactly as it could read the signing key in 1.3.6. The channel split is
    only an OS boundary once the broker runs as a **different identity** —
    `docs/SAFETY.md` states the provisioning step and the measured test. What
    changes on any machine, provisioned or not, is that the worker no longer
    holds a code path to `results/`: it can only send a manifest.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

BROKER_VERSION = "1.4.0"
STATE_DIR = os.path.join(".chelate", "broker")
LOG_NAME = "log.jsonl"
INFO_NAME = "broker.json"
SUBMIT = "submit"
APPROVE = "approve"

# What each channel serves. Membership is the control; there is no second
# check deeper in the handler, so a new op added to this table is a decision.
CHANNEL_OPS: Dict[str, frozenset] = {
    SUBMIT: frozenset({"submit", "audit", "status", "ping"}),
    APPROVE: frozenset({"approve", "revoke", "rotate", "status", "ping"}),
}

MAX_MESSAGE = 1 << 20          # a manifest is small; 1 MiB is generous
MAX_PENDING = 8                # writes are one at a time on purpose


class BrokerError(RuntimeError):
    """The broker refused the request; the message says why."""


class BrokerUnavailable(BrokerError):
    """No broker is listening. Callers fail closed, they never fall back."""


class BrokerRefused(BrokerError):
    """The broker answered and said no."""


# --------------------------------------------------------------------------
# state and keys
# --------------------------------------------------------------------------

def state_dir(workspace: str) -> str:
    return os.path.join(os.path.abspath(workspace), STATE_DIR)


def key_root(workspace: str) -> str:
    return os.path.join(state_dir(workspace), "keys")


def _addresses(workspace: str) -> Tuple[str, str]:
    """(submit, approve) endpoints — named pipes on Windows, sockets elsewhere.

    The name is derived from the real path, so two workspaces never share a
    channel and a moved workspace gets a fresh one.
    """
    import hashlib
    digest = hashlib.sha256(
        os.path.realpath(os.path.abspath(workspace)).encode("utf-8")
    ).hexdigest()[:12]
    if os.name == "nt":
        return (rf"\\.\pipe\chelate-{digest}-submit",
                rf"\\.\pipe\chelate-{digest}-approve")
    folder = state_dir(workspace)
    return os.path.join(folder, "submit.sock"), os.path.join(folder, "approve.sock")


def _family() -> str:
    return "AF_PIPE" if os.name == "nt" else "AF_UNIX"


def _write_private(path: str, data: bytes) -> None:
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    tmp = path + ".tmp"
    # O_BINARY matters: on Windows `os.open` defaults to text mode, and a
    # random 32-byte key contains 0x0a about 12% of the time — written as
    # text it becomes 33 bytes, silently, on the machine that generated it.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
    finally:
        os.close(fd)
    os.replace(tmp, path)


def ensure_state(workspace: str) -> Dict[str, str]:
    """Create the two channel keys if they are absent; return their paths."""
    folder = state_dir(workspace)
    os.makedirs(folder, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    paths = {}
    for channel in (SUBMIT, APPROVE):
        path = os.path.join(folder, f"{channel}.key")
        if not os.path.isfile(path) or os.path.getsize(path) < 16:
            _write_private(path, secrets.token_bytes(32))
        paths[channel] = path
    os.makedirs(key_root(workspace), exist_ok=True)
    return paths


def read_key(workspace: str, channel: str) -> bytes:
    path = os.path.join(state_dir(workspace), f"{channel}.key")
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise BrokerUnavailable(
            f"no {channel} key in {os.path.dirname(path)}; run "
            f"`python cli.py broker start --root <ws>` first ({exc})")


# --------------------------------------------------------------------------
# the wire
# --------------------------------------------------------------------------

def _send(conn, payload: Dict[str, Any]) -> None:
    conn.send_bytes(json.dumps(payload, ensure_ascii=False,
                               sort_keys=True).encode("utf-8"))


def _close(conn) -> None:
    try:
        conn.close()
    except OSError:
        pass


def _recv(conn) -> Dict[str, Any]:
    raw = conn.recv_bytes(MAX_MESSAGE)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise BrokerError("request must be a JSON object")
    return data


class Client:
    """One request per connection, so a refusal cannot be half-applied."""

    def __init__(self, workspace: str, channel: str = SUBMIT,
                 timeout: float = 30.0):
        if channel not in CHANNEL_OPS:
            raise ValueError(f"unknown channel {channel!r}")
        self.workspace = os.path.abspath(workspace)
        self.channel = channel
        self.timeout = timeout

    def call(self, op: str, **payload) -> Dict[str, Any]:
        from multiprocessing.connection import Client as _Client
        address = _addresses(self.workspace)[0 if self.channel == SUBMIT else 1]
        key = read_key(self.workspace, self.channel)
        try:
            conn = _Client(address, family=_family(), authkey=key)
        except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
            raise BrokerUnavailable(
                f"no broker listening on the {self.channel} channel of "
                f"{self.workspace} ({exc}); start one with "
                f"`python cli.py broker start --root <ws>`, or run with "
                f"CHELATE_RUNTIME=policy and accept containment: policy-only")
        try:
            _send(conn, dict(payload, op=op, channel=self.channel))
            reply = _recv(conn)
        except (EOFError, OSError) as exc:
            raise BrokerUnavailable(f"the broker closed the connection: {exc}")
        finally:
            conn.close()
        if not reply.get("ok"):
            raise BrokerRefused(str(reply.get("error") or "refused"))
        return reply.get("result") or {}


# --------------------------------------------------------------------------
# the server
# --------------------------------------------------------------------------

class Broker:
    """Serves the two channels from one process and owns `results/`."""

    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace)
        self._stop = threading.Event()
        self._listeners = []
        self._threads = []
        self.started = ""

    # -- lifecycle --------------------------------------------------------
    def start(self) -> "Broker":
        from multiprocessing.connection import Listener
        ensure_state(self.workspace)
        os.environ["CHELATE_KEY_ROOT"] = key_root(self.workspace)
        addresses = dict(zip((SUBMIT, APPROVE), _addresses(self.workspace)))
        for channel, address in addresses.items():
            listener = Listener(address, family=_family(),
                                authkey=read_key(self.workspace, channel))
            self._listeners.append(listener)
            thread = threading.Thread(target=self._serve, args=(listener, channel),
                                      daemon=True)
            thread.start()
            self._threads.append(thread)
        self.started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._log({"event": "started", "pid": os.getpid(),
                   "version": BROKER_VERSION})
        try:
            _write_private(os.path.join(state_dir(self.workspace), INFO_NAME),
                           json.dumps({"pid": os.getpid(), "started": self.started,
                                       "version": BROKER_VERSION,
                                       "workspace": self.workspace,
                                       "results": os.path.join(self.workspace,
                                                               "results")},
                                      indent=2).encode("utf-8"))
        except OSError:
            pass
        return self

    def stop(self) -> None:
        self._stop.set()
        for listener in self._listeners:
            try:
                listener.close()
            except OSError:
                pass
        self._listeners = []
        self._log({"event": "stopped"})

    def serve_forever(self) -> None:
        """Block until stop() is called (the CLI's foreground mode)."""
        try:
            while not self._stop.wait(0.5):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    # -- accept loop ------------------------------------------------------
    def _serve(self, listener, channel: str) -> None:
        while not self._stop.is_set():
            try:
                conn = listener.accept()
            except (OSError, EOFError):
                return
            if self._stop.is_set():
                # Windows does not interrupt a blocked accept() when the
                # listener is closed, so a connection can still arrive after
                # stop(). Dropping it unanswered is the fail-closed answer:
                # the client sees EOF and reports "no broker", rather than a
                # pong from a process that has already shut down.
                _close(conn)
                return
            threading.Thread(target=self._handle, args=(conn, channel),
                             daemon=True).start()

    def _handle(self, conn, channel: str) -> None:
        try:
            request = _recv(conn)
            op = str(request.pop("op", ""))
            if op not in CHANNEL_OPS[channel]:
                self._log({"event": "refused", "channel": channel, "op": op,
                           "reason": "not served by this channel"})
                _send(conn, {"ok": False,
                             "error": (f"the {channel} channel does not serve "
                                       f"{op!r}; use the approve channel"),
                             "code": "channel"})
                return
            handler = getattr(self, f"_op_{op}")
            try:
                result = handler(request, channel)
            except BrokerError as exc:
                _send(conn, {"ok": False, "error": str(exc),
                             "code": type(exc).__name__})
                return
            _send(conn, {"ok": True, "result": result})
        except (EOFError, OSError):
            pass
        except Exception as exc:  # never leave a client hanging
            try:
                _send(conn, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            except OSError:
                pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # -- operations -------------------------------------------------------
    def _op_ping(self, request, channel) -> Dict[str, Any]:
        return {"pong": True, "channel": channel}

    def _op_status(self, request, channel) -> Dict[str, Any]:
        results = os.path.join(self.workspace, "results")
        import getpass
        return {"broker": True, "version": BROKER_VERSION,
                "pid": os.getpid(), "started": self.started,
                "identity": getpass.getuser(),
                "workspace": self.workspace,
                "results": results, "results_exists": os.path.isdir(results),
                "key_root": key_root(self.workspace)}

    def _op_audit(self, request, channel) -> Dict[str, Any]:
        """A read-only census of `results/` — the directory this side owns.

        It belongs on the submit channel because that is the worker's
        channel, and audit answers the worker's question ("what did I
        publish?"). It grants nothing: no token is read and no file moves.
        """
        from core import router
        return router.audit_results(self.workspace)

    def _op_approve(self, request, channel) -> Dict[str, Any]:
        from core import approval
        action = str(request.get("action") or "promote")
        params = request.get("params") or {}
        ttl = int(request.get("ttl") or approval.DEFAULT_TTL_SECONDS)
        # The human channel check happened in the CLI that called us; on this
        # side the control is the channel itself.
        token = approval.mint(
            self.workspace, action, params, ttl=ttl,
            manifest_sha256=str(request.get("manifest_sha256") or ""),
            nonce=str(request.get("nonce") or ""))
        self._log({"event": "approved", "action": action,
                   "nonce": token["nonce"], "expires": token["expires"]})
        return {"token": token}

    def _op_revoke(self, request, channel) -> Dict[str, Any]:
        from core import approval
        removed = approval.revoke(self.workspace,
                                  str(request.get("action") or "promote"))
        self._log({"event": "revoked", "removed": removed})
        return {"removed": removed}

    def _op_rotate(self, request, channel) -> Dict[str, Any]:
        from core import approval
        report = approval.rotate(self.workspace)
        self._log({"event": "rotated"})
        return dict(report or {}, rotated=True)

    def _op_submit(self, request, channel) -> Dict[str, Any]:
        """Validate the manifest, spend the token, publish — in that order."""
        from core import approval, router
        from contracts.action_manifest import ActionManifest

        manifest = ActionManifest.from_dict(request.get("manifest") or {})
        problems = manifest.problems()
        if problems:
            self._log({"event": "refused", "channel": channel, "op": "submit",
                       "reason": problems[0]})
            raise BrokerError("manifest refused: " + "; ".join(problems))
        if os.path.normcase(os.path.realpath(manifest.workspace)) != \
                os.path.normcase(os.path.realpath(self.workspace)):
            raise BrokerError("manifest names a different workspace")
        if manifest.runtime != "broker":
            raise BrokerError(
                f"manifest names runtime {manifest.runtime!r}; this broker "
                f"serves 'broker' only")
        if manifest.broker_version and manifest.broker_version != BROKER_VERSION:
            raise BrokerError(
                f"manifest was built for broker {manifest.broker_version!r}; "
                f"this is {BROKER_VERSION!r}")
        lock = router.skill_lock_digest()
        if manifest.skill_lock_sha256 and manifest.skill_lock_sha256 != lock:
            raise BrokerError(
                "the skill set changed since the manifest was built; rebuild "
                "and re-approve it")
        manifest_sha = manifest.digest()
        missing = self._check_outputs(manifest.outputs)
        if missing:
            raise BrokerError("; ".join(missing))

        params = request.get("params") or {}
        token = approval.consume(self.workspace, "promote", dict(params),
                                 manifest_sha256=manifest_sha,
                                 require_binding=True)
        if token.get("nonce") != manifest.nonce:
            raise BrokerError(
                "manifest nonce does not match the approved token; the "
                "manifest was rebuilt after it was approved")
        stamp = str(request.get("stamp") or datetime.now(timezone.utc)
                    .strftime("%Y%m%dT%H%M%SZ"))
        try:
            promoted = router.promote(
                self.workspace, stamp,
                approval_info={"nonce": token.get("nonce"),
                               "issued": token.get("issued"),
                               "manifest_sha256": manifest_sha},
                allow_unverified=bool(params.get("allow_unverified")),
                files=manifest.outputs, manifest_sha256=manifest_sha)
        except Exception as exc:  # locked, stale, unverified, link
            self._log({"event": "refused", "channel": channel, "op": "submit",
                       "reason": str(exc)})
            raise BrokerError(f"promotion refused: {exc}")
        self._log({"event": "published", "stamp": stamp,
                   "nonce": token.get("nonce"),
                   "files": len(manifest.outputs)})
        return {"promoted": promoted, "stamp": stamp,
                "nonce": token.get("nonce")}

    def _check_outputs(self, outputs) -> list:
        """Every declared artifact exists and matches its digest."""
        import hashlib
        problems = []
        for item in outputs:
            path = os.path.join(self.workspace,
                                *str(item.get("path", "")).split("/"))
            if not os.path.isfile(path):
                problems.append(f"declared output is missing: {item.get('path')}")
                continue
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            if str(item.get("sha256")) and digest != str(item.get("sha256")):
                problems.append(
                    f"declared output changed after the manifest was built: "
                    f"{item.get('path')}")
        return problems

    # -- logging ----------------------------------------------------------
    def _log(self, event: Dict[str, Any]) -> None:
        record = dict(event, at=datetime.now(timezone.utc)
                      .strftime("%Y-%m-%dT%H:%M:%SZ"),
                      pid=os.getpid())
        path = os.path.join(state_dir(self.workspace), LOG_NAME)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(record, ensure_ascii=False,
                                    sort_keys=True) + "\n")
        except OSError:
            pass


# --------------------------------------------------------------------------
# adopt
# --------------------------------------------------------------------------

def adopt(workspace: str) -> Dict[str, Any]:
    """Take a 1.3.x workspace under the broker without breaking its history.

    The old tree already has `results/` and `results/.promotions.jsonl`; the
    promotion log must still verify afterwards, which is what
    `router.audit_results` answers.
    """
    from core import router
    workspace = os.path.abspath(workspace)
    ensure_state(workspace)
    results = os.path.join(workspace, "results")
    os.makedirs(results, exist_ok=True)
    marker = os.path.join(state_dir(workspace), "adopted.json")
    audit = router.audit_results(workspace)
    record = {"adopted": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "workspace": workspace,
              "promotions": audit.get("promotions"),
              "audit_ok": audit.get("ok")}
    _write_private(marker, json.dumps(record, indent=2).encode("utf-8"))
    return record
