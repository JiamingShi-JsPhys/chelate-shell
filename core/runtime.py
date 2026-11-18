"""Chelate Shell — the one runtime API every surface is allowed to call.

Caller: `cli.py`, the MCP server, host hooks, pipeline hooks and recipes.
        Nothing else reaches `core.router` directly once 1.4.0 lands.
Data schemas:
    Reads:  process/gates/*.json, results/.promotions.jsonl (through router).
    Writes: none of its own. `run_skill` writes what a pipeline writes;
            `submit` is the only call that can reach `results/`, and in 1.4.0
            only the broker performs it.
Design: two backends behind five calls.

    status(root)                  read-only census
    run_skill(root, skill, args)  execute one skill, in process/
    start_recipe(root, name)      schedule registered skills, in process/
    submit(root, manifest)        ask to publish; the broker's job
    audit(root)                   read-only: what is in results/ and why

`PolicyRuntime` wraps what 1.3.6 already does: policy checks inside one
process, one OS user, `containment: policy-only`.
`BrokerRuntime` is the 1.4.0 boundary: a separate identity holds the key and
owns `results/`, and every call crosses IPC.

Selection is `CHELATE_RUNTIME=policy|broker` (or the `runtime=` argument).
An unrecognised value is refused rather than defaulted — the one thing a
runtime switch must never do is pick a weaker mode because a name was
misspelled. A broker that is not reachable is `RuntimeUnavailable`, never a
quiet fall back to policy.

`DEFAULT_RUNTIME` is ``policy`` in 1.4.0: installing the release does not put
a broker in the path, and nothing silently upgrades itself either. Choose the
broker explicitly (``CHELATE_RUNTIME=broker``, or ``--runtime broker``), and
every status says which one is live — ``containment: policy-only`` or the
broker's ``containment_detail`` — so the weaker mode is never implicit.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core import router

RUNTIME_ENV = "CHELATE_RUNTIME"

_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "skills")


def egress_status() -> Dict[str, Any]:
    """What is true about outbound network calls: declared, never blocked.

    There is no egress control in this tree, and saying "egress controlled"
    because a manifest has a boolean in it would be the exact kind of claim
    this project spends its documentation avoiding. What a manifest can do
    honestly is declare that a skill reaches the network; the status then
    names those skills and states that nothing enforces the boundary.
    """
    from core import registry
    reg = registry.Registry().scan(_SKILLS_DIR)
    return {
        "controlled": False,
        "enforced_by": None,
        "declaring_network": sorted(r.name for r in reg.all() if r.network),
        "note": ("no layer in this tree blocks an outbound socket; this "
                 "lists the skills that declare `network` so the claim is "
                 "scoped to them rather than to the process"),
    }
POLICY = "policy"
BROKER = "broker"
DEFAULT_RUNTIME = POLICY


class RuntimeUnavailable(RuntimeError):
    """The selected backend cannot serve this call (fail closed)."""


class RuntimeUnsupported(RuntimeError):
    """The call is part of the contract but not implemented by this backend yet."""


class RuntimeConfigError(ValueError):
    """`CHELATE_RUNTIME` names something that is not a runtime."""


class Runtime:
    """The five calls. Subclasses implement all of them or raise."""

    name = ""
    containment = ""

    def status(self, root: str) -> Dict[str, Any]:
        raise NotImplementedError

    def run_skill(self, root: str, skill: str,
                  args: Optional[List[str]] = None, **options: Any) -> Dict[str, Any]:
        raise NotImplementedError

    def start_recipe(self, root: str, name: str,
                     args: Optional[List[str]] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def submit(self, root: str, manifest: Any,
               params: Optional[Dict[str, Any]] = None,
               require_approval: bool = True) -> Dict[str, Any]:
        raise NotImplementedError

    def audit(self, root: str) -> Dict[str, Any]:
        raise NotImplementedError


class PolicyRuntime(Runtime):
    """1.3.6 semantics: policy checks in one process, one OS user."""

    name = POLICY
    containment = "policy-only"

    def status(self, root: str) -> Dict[str, Any]:
        root = os.path.abspath(root)
        return {
            "runtime": self.name,
            "containment": self.containment,
            "workspace": root,
            "workspace_exists": os.path.isdir(root),
            "freshness": router.gate_freshness(root),
            "failed": router.failed_gates(root),
            "unverified": router.unverified_gates(root),
            "stale": router.stale_gates(root),
            "egress": egress_status(),
        }

    def run_skill(self, root: str, skill: str,
                  args: Optional[List[str]] = None, **options: Any) -> Dict[str, Any]:
        if "selected" in options:
            raise RuntimeConfigError(
                "run_skill selects the skill; pass it as `skill`, not in options")
        # A single skill run writes into process/ and stops there. Publishing
        # is `submit`, which is the one call that crosses into results/ — in
        # either backend.
        return router.run(root, selected=[skill], extra_args=list(args or []),
                          publish=False, **options)

    def start_recipe(self, root: str, name: str,
                     args: Optional[List[str]] = None) -> Dict[str, Any]:
        if args:
            raise RuntimeUnsupported(
                "recipe arguments are not part of the v1 recipe format")
        from core import recipes as recipes_mod  # local: recipes uses this module
        return recipes_mod.run(root, name, runtime=self)

    def submit(self, root: str, manifest: Any,
               params: Optional[Dict[str, Any]] = None,
               require_approval: bool = True) -> Dict[str, Any]:
        """Publish exactly the files the manifest declares, after the check.

        Policy mode keeps the checks in this process; it does not keep fewer
        of them. The manifest is validated, the approval token must be bound
        to this manifest's digest, the nonce must be the token's, and the
        files are hashed while they are copied.
        """
        from contracts.action_manifest import ActionManifest
        from core import approval
        root = os.path.abspath(root)
        if isinstance(manifest, ActionManifest):
            man = manifest
        elif isinstance(manifest, dict):
            man = ActionManifest.from_dict(manifest)
        else:
            raise RuntimeConfigError(
                "submit takes an ActionManifest or the dict it serialises to")
        problems = man.problems()
        if problems:
            raise RuntimeRefused("manifest refused: " + "; ".join(problems))
        if os.path.normcase(os.path.realpath(man.workspace)) != \
                os.path.normcase(os.path.realpath(root)):
            raise RuntimeRefused("manifest names a different workspace")
        if man.runtime != self.name:
            raise RuntimeRefused(
                f"manifest names runtime {man.runtime!r}; this is {self.name!r}")

        token: Dict[str, Any] = {}
        if require_approval:
            try:
                token = approval.consume(
                    root, "promote", dict(params or {}),
                    manifest_sha256=man.digest(), require_binding=True)
            except (approval.ApprovalRequired,
                    approval.ApprovalInvalid) as exc:
                raise RuntimeRefused(f"promotion withheld: {exc}")
            if token.get("nonce") != man.nonce:
                raise RuntimeRefused(
                    "manifest nonce does not match the approved token; the "
                    "manifest was rebuilt after it was approved")

        try:
            dst = router.promote(
                root, router._ts(),
                {"source": "submit", "nonce": token.get("nonce")},
                allow_unverified=bool((params or {}).get("allow_unverified")),
                files=man.outputs, manifest_sha256=man.digest())
        except router.PromotionLocked as exc:
            raise RuntimeRefused(f"promotion withheld: {exc}")
        return {"promoted": dst, "files": len(man.outputs),
                "manifest_sha256": man.digest(), "nonce": token.get("nonce")}

    def audit(self, root: str) -> Dict[str, Any]:
        return router.audit_results(os.path.abspath(root))


class RuntimeRefused(RuntimeError):
    """The backend answered and said no (a locked gate, a stale manifest)."""


class BrokerRuntime(Runtime):
    """The 1.4.0 boundary: publication crosses IPC, and the worker never
    holds a code path to `results/`.

    What runs where: `run_skill` still executes in *this* process — that is
    the worker's job, and moving it would mean shipping code to the broker.
    `submit` is the only call that reaches `results/`, and it is answered by
    the broker after the token check. A broker that is not listening is
    `RuntimeUnavailable`, never a quiet fall back to policy mode.
    """

    name = BROKER
    containment = "broker"

    # -- plumbing ---------------------------------------------------------
    def _call(self, root: str, op: str, channel: str = "submit", **payload):
        from core import broker as broker_mod
        client = broker_mod.Client(root, channel)
        try:
            return client.call(op, **payload)
        except broker_mod.BrokerUnavailable as exc:
            raise RuntimeUnavailable(str(exc))
        except broker_mod.BrokerRefused as exc:
            raise RuntimeRefused(str(exc))

    def _describe(self, root: str) -> Dict[str, Any]:
        """The broker's own view plus the one fact that decides the claim."""
        import getpass
        info = self._call(root, "status")
        same = str(info.get("identity", "")) == getpass.getuser()
        info["containment_detail"] = (
            "same-os-user: the channel split is real, but a process under "
            "this account can read the approve key — provision a second "
            "identity for an OS boundary (docs/SAFETY.md)"
            if same else
            "separate-os-user: the approve channel is an OS boundary")
        return info

    # -- the five calls ---------------------------------------------------
    def status(self, root: str) -> Dict[str, Any]:
        root = os.path.abspath(root)
        report = PolicyRuntime().status(root)
        report.update(runtime=self.name, containment=self.containment,
                      broker=self._describe(root))
        return report

    def run_skill(self, root: str, skill: str,
                  args: Optional[List[str]] = None, **options: Any) -> Dict[str, Any]:
        # Present but cheap: proves the broker is up before a run starts, so
        # a dead broker is reported as unavailable rather than after the work.
        self._call(root, "ping")
        return PolicyRuntime().run_skill(root, skill, args=args, **options)

    def start_recipe(self, root: str, name: str,
                     args: Optional[List[str]] = None) -> Dict[str, Any]:
        self._call(root, "ping")
        return PolicyRuntime().start_recipe(root, name, args=args)

    def submit(self, root: str, manifest: Any,
               params: Optional[Dict[str, Any]] = None,
               require_approval: bool = True) -> Dict[str, Any]:
        # require_approval is part of the shared signature; the broker always
        # consumes a bound token, so there is no switch here to turn off.
        from contracts.action_manifest import ActionManifest
        if not isinstance(manifest, (ActionManifest, dict)):
            raise RuntimeConfigError(
                "submit takes an ActionManifest or the dict it serialises to")
        body = (manifest.to_dict() if isinstance(manifest, ActionManifest)
                else dict(manifest))
        return self._call(root, "submit", manifest=body,
                          params=dict(params or {}))

    def audit(self, root: str) -> Dict[str, Any]:
        # `results/` is the broker's directory in this mode; a census read in
        # the worker would be the same quiet shortcut `submit` refuses.
        return self._call(root, "audit")


_BACKENDS = {POLICY: PolicyRuntime, BROKER: BrokerRuntime}


def select(name: Optional[str] = None) -> Runtime:
    """Return the backend the environment asks for, or refuse to guess."""
    chosen = (name or os.environ.get(RUNTIME_ENV, "") or DEFAULT_RUNTIME)
    chosen = chosen.strip().lower()
    if chosen not in _BACKENDS:
        raise RuntimeConfigError(
            f"{RUNTIME_ENV}={chosen!r} is not one of "
            f"{', '.join(sorted(_BACKENDS))}; refusing to guess")
    return _BACKENDS[chosen]()
