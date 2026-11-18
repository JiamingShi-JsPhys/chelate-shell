"""Chelate Shell CLI entry point.

Usage:
    python cli.py list
    python cli.py run "task-organizer" --root /path/to/workspace
    python cli.py pipeline --root /path/to/workspace --mode a
    python cli.py pipeline --root /path/to/workspace --mode b --input-kind csv
    python cli.py pipeline --root /path/to/workspace --mode c --selected formula-validator,reference-auditor
    python cli.py pipeline --root /path/to/workspace --dry-run
    python cli.py pipeline --root /path/to/workspace --mode c \
        --selected reference-auditor --skill-arg "reference-auditor:--input draft.md"
    python cli.py pipeline --root ./test_workspace --inputs draft.md data.csv
    python cli.py pipeline --root /path/to/workspace --mode c --selected data-profiler --debug
    python cli.py memory add "单位约定是 cgs" --root /path/to/workspace
    python cli.py memory brief --root /path/to/workspace

Caller: a user / agent subprocess. No other file imports this module.
Data schemas:
    Reads:  skills/<skill>/manifest.json (via core.registry).
    Writes: results/pipeline_report_<ts>.json + _broadcast/pipeline_index_<ts>.json.
User instruction: "cli.py — the command-line entry point (run: python cli.py run <task>)".
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core import approval
from core import broker as broker_mod
from core import hooks as hooks_mod
from core import memory as memory_mod
from core import skillkit
from core import recipes as recipes_mod
from core import runtime as runtime_mod
from core.registry import load_default_registry
from core.router import audit_results
from core import update as update_mod
from core.router import run as router_run
from core import router as router_mod
from lib.chelate_core import debug as debug_mod
from lib.chelate_core import paths


def cmd_list(args) -> int:
    reg = load_default_registry()
    print(f"{len(reg)} skills registered:")
    for rec in reg.all():
        deps = ",".join(rec.dependencies) if rec.dependencies else "-"
        print(f"  {rec.name:<28} stage={rec.stage:<10} deps=[{deps}]")
        if debug_mod.flag(args.debug):
            debug_mod.log(f"{rec.name}: entrypoint={rec.entrypoint} "
                          f"inputs={rec.input_types} outputs={rec.output_types} "
                          f"sandbox_required={rec.sandbox_required} "
                          f"run_path={rec.run_path}")
    return 0


def cmd_run(args) -> int:
    """Run a single skill directly (bypasses the pipeline).

    All skill-specific args (including --root) come after the skill name via
    argparse.REMAINDER, so any flag order works.
    """
    reg = load_default_registry()
    rec = reg.get(args.name)
    if rec is None:
        print(f"unknown skill: {args.name}; available: {reg.names()}",
              file=sys.stderr)
        return 1
    # --debug may sit before the skill name (parsed) or inside the REMAINDER
    # (swallowed by argparse); accept both and never forward it to the skill.
    skill_args = [a for a in (args.args or []) if a != "--debug"]
    debug_mod.flag(args.debug or "--debug" in (args.args or []))
    import subprocess
    cmd = [sys.executable, rec.run_path] + skill_args
    debug_mod.log(f"run: exec {' '.join(cmd)} (cwd={_REPO_ROOT})")
    proc = subprocess.run(cmd, cwd=_REPO_ROOT, env=decision_env(rec))
    return proc.returncode


def decision_env(rec):
    """Build the subprocess env for a skill (degraded deps -> UNVERIFIED)."""
    from core.sandbox import resolve_environment
    return resolve_environment(rec.dependencies).env()


def parse_skill_args(pairs) -> dict:
    """Parse repeated --skill-arg 'skill:flag [flag ...]' into {skill: [args]}."""
    out = {}
    for pair in pairs or []:
        if ":" not in pair:
            continue
        skill, _, rest = pair.partition(":")
        skill = skill.strip()
        args = rest.split()
        if skill and args:
            out.setdefault(skill, []).extend(args)
    return out


def cmd_approve(args) -> int:
    """Issue a one-time approval token for an irreversible action."""
    root = os.path.abspath(args.root)
    inputs, missing = paths.resolve_inputs(root, args.inputs)
    if missing:
        print("input file(s) not found (resolved against --root "
              f"{root}): " + ", ".join(missing), file=sys.stderr)
        return 2
    selected = [s.strip() for s in args.selected.split(",") if s.strip()] \
        if args.selected else []
    params = approval.pipeline_params(args.mode, args.input_kind,
                                      inputs, selected,
                                      allow_unverified=args.allow_unverified)
    # The token names the bytes, not just the plan: whatever is pending is
    # what this approval authorises, and a rebuilt manifest will not match.
    manifest_sha, manifest_nonce = _manifest_for_approval(root, params)
    try:
        token = _issue_token(root, args, params, manifest_sha, manifest_nonce)
    except approval.HumanRequired as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except (approval.ApprovalInvalid, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"approved promote for {root} — token valid for {args.ttl}s:",
          file=sys.stderr)
    print(json.dumps({"token": str(token), "action": "promote",
                      "ttl_seconds": args.ttl, "params": params,
                      "manifest_sha256": manifest_sha},
                     ensure_ascii=False, indent=2))
    return 0


def _issue_token(root, args, params, manifest_sha256="", nonce=""):
    """Mint the token where the key lives: here, or in the broker."""
    if (os.environ.get(runtime_mod.RUNTIME_ENV, "").strip().lower()
            != runtime_mod.BROKER):
        return approval.issue(root, "promote", params, ttl=args.ttl,
                              manifest_sha256=manifest_sha256, nonce=nonce)
    # The typed confirmation happens here, in the human's terminal; the key
    # stays in the broker, which answers only on the approve channel.
    approval.require_human("issuing an approval for 'promote'")
    try:
        reply = broker_mod.Client(root, "approve").call(
            "approve", action="promote", params=params, ttl=args.ttl,
            manifest_sha256=manifest_sha256, nonce=nonce)
    except broker_mod.BrokerError as exc:
        raise approval.HumanRequired(f"broker approval failed: {exc}")
    state = approval.state_dir(root)
    return state / "approvals" / f"promote-{reply['token']['nonce']}.json"


# -- publication: one manifest, one approval, one exact set of files --------

PENDING = os.path.join(".chelate", "pending", "manifest.json")


def _pending_path(root: str) -> str:
    return os.path.join(root, PENDING)


def _write_pending(root: str, manifest, params) -> str:
    """Record what was produced, so a person can approve those exact bytes."""
    path = _pending_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = {"manifest": manifest.to_dict(), "params": params,
            "manifest_sha256": manifest.digest()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, ensure_ascii=False, indent=2)
    return path


def _read_pending(root: str, path: str = ""):
    from contracts.action_manifest import ActionManifest
    path = path or _pending_path(root)
    with open(path, encoding="utf-8") as fh:
        body = json.load(fh)
    return (ActionManifest.from_dict(body.get("manifest") or {}),
            dict(body.get("params") or {}))


def _build_manifest(root: str, params, runtime=None):
    """Describe the bytes under process/ and record the plan beside them."""
    from contracts.action_manifest import ActionManifest
    runtime = runtime or runtime_mod.select()
    manifest = ActionManifest.from_workspace(
        root,
        runtime=runtime.name,
        broker_version=(broker_mod.BROKER_VERSION
                        if runtime.name == runtime_mod.BROKER else ""),
        skill_lock_sha256=router_mod.skill_lock_digest(),
        inputs=[{"path": str(item.get("path", "")),
                 "sha256": str(item.get("sha256") or "")}
                for item in params.get("inputs") or []])
    _write_pending(root, manifest, params)
    return manifest


def _manifest_for_approval(root: str, params):
    """(digest, nonce) of the manifest this token binds.

    The pending manifest is reused only when its plan is the same one; a
    different plan rebuilds it, because an approval for one plan must not be
    spendable on another. Building it here means `approve` works whether it
    runs before or after the pipeline.
    """
    manifest = None
    try:
        manifest, stored = _read_pending(root)
    except (OSError, ValueError):
        manifest = None
    else:
        if stored != params:
            manifest = None
    if manifest is None:
        manifest = _build_manifest(root, params)
    return manifest.digest(), manifest.nonce


def _publish(root: str, manifest, params, require_approval: bool = True):
    """Submit to the selected backend. A missing broker is an error, not a
    quieter mode."""
    return runtime_mod.select().submit(
        root, manifest, params=params, require_approval=require_approval)


def _publish_or_hold(root: str, result: dict, inputs, selected,
                     args) -> None:
    """The pipeline's one irreversible step, through the runtime."""
    params = approval.pipeline_params(args.mode, args.input_kind, inputs,
                                      selected,
                                      allow_unverified=args.allow_unverified)
    try:
        manifest = _build_manifest(root, params)
    except OSError as exc:
        result["blocked"] = "publication"
        result["reason"] = f"could not describe process/: {exc}"
        return
    result["manifest_sha256"] = manifest.digest()
    result["pending_manifest"] = _pending_path(root)
    if not manifest.outputs:
        result["blocked"] = "publication"
        result["reason"] = "process/ holds no files to publish"
        return
    try:
        published = _publish(root, manifest, params,
                             require_approval=not args.no_approval)
    except runtime_mod.RuntimeUnavailable as exc:
        result["blocked"] = "runtime"
        result["reason"] = str(exc)
        print(f"PUBLICATION REFUSED — {exc}", file=sys.stderr)
    except (runtime_mod.RuntimeRefused, runtime_mod.RuntimeConfigError) as exc:
        text = str(exc)
        result["blocked"] = "approval" if "approval" in text.lower() else "publication"
        result["reason"] = text
        print(f"PROMOTION WITHHELD — {text}", file=sys.stderr)
        if "approval" in text.lower():
            print(f"  next: python cli.py approve --root {root} --mode {args.mode}"
                  f"  (binds {os.path.basename(_pending_path(root))}), then "
                  f"python cli.py publish --root {root}", file=sys.stderr)
    else:
        result["promoted"] = published.get("promoted")
        result["published_files"] = published.get("files")


def cmd_publish(args) -> int:
    """Submit the pending manifest — the same bytes the approval names."""
    root = os.path.abspath(args.root)
    try:
        manifest, params = _read_pending(root, args.manifest)
    except (OSError, ValueError) as exc:
        print(f"no pending manifest under {root}: {exc}", file=sys.stderr)
        return 2
    try:
        published = _publish(root, manifest, params,
                             require_approval=not args.no_approval)
    except (runtime_mod.RuntimeRefused, runtime_mod.RuntimeUnavailable,
            runtime_mod.RuntimeConfigError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)},
                         ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, **published}, ensure_ascii=False, indent=2))
    return 0


def cmd_broker(args) -> int:
    """Start, query or adopt: the process that holds the key."""
    root = os.path.abspath(args.root)
    if args.broker_cmd == "adopt":
        print(json.dumps(broker_mod.adopt(root), ensure_ascii=False, indent=2))
        return 0
    if args.broker_cmd == "start":
        broker = broker_mod.Broker(root).start()
        submit, approve = broker_mod._addresses(root)
        print(json.dumps({"ok": True, "started": broker.started,
                          "pid": os.getpid(), "workspace": root,
                          "submit": submit, "approve": approve,
                          "note": "foreground; Ctrl-C stops it"},
                         ensure_ascii=False), file=sys.stderr)
        broker.serve_forever()
        return 0
    try:
        info = broker_mod.Client(root, "submit").call("status")
    except broker_mod.BrokerError as exc:
        print(json.dumps({"ok": False, "error": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_skill(args) -> int:
    """Scaffold the mechanical half, or lint the half people forget."""
    if args.skill_cmd == "new":
        try:
            report = skillkit.new(args.name, args.stage, version=args.version,
                                  root=os.path.abspath(args.root)
                                  if args.root else "")
        except skillkit.SkillKitError as exc:
            print(json.dumps({"ok": False, "error": str(exc)},
                             ensure_ascii=False))
            return 2
        print(json.dumps(dict(report, ok=True), ensure_ascii=False, indent=2))
        return 0
    report = skillkit.lint(os.path.abspath(args.root) if args.root else "")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def cmd_doctor(args) -> int:
    """What this machine can actually check, and what it would take."""
    import importlib.util
    import platform

    from lib.chelate_core.adapter import import_name

    root = os.path.abspath(args.root)
    reg = load_default_registry()
    rows, missing_dists = [], set()
    for rec in reg.all():
        absent = []
        for dep in rec.dependencies:
            try:
                present = importlib.util.find_spec(import_name(dep)) is not None
            except (ImportError, ValueError, ModuleNotFoundError):
                present = False
            if not present:
                absent.append(dep)
                missing_dists.add(dep)
        rows.append({"skill": rec.name, "stage": rec.stage,
                     "requires": list(rec.dependencies), "missing": absent})
    gates = [row for row in rows if row["stage"] == "gates"]
    degraded = [row["skill"] for row in gates if row["missing"]]

    workspace = {"path": root, "exists": os.path.isdir(root),
                 "approval_key": approval.has_key(root) if os.path.isdir(root)
                 else False}
    if os.path.isdir(root):
        workspace["memory"] = memory_mod.summary(root)
        workspace["gates"] = runtime_mod.PolicyRuntime().status(root)["freshness"]
    report = {
        "python": platform.python_version(),
        "skills": len(rows),
        "with_dependencies": sum(1 for row in rows if row["requires"]),
        "missing_anything": sum(1 for row in rows if row["missing"]),
        "gates_in_mode_a": len(gates),
        "gates_would_degrade": degraded,
        "install": ("pip install " + " ".join(sorted(missing_dists))
                    if missing_dists else ""),
        "workspace": workspace,
        "skills_detail": rows if args.verbose else
                         [row for row in rows if row["missing"]],
    }
    try:
        selected = runtime_mod.select(os.environ.get(runtime_mod.RUNTIME_ENV))
        report["runtime"] = selected.name
        report["containment"] = selected.containment
    except runtime_mod.RuntimeConfigError as exc:
        report["runtime"] = {"error": str(exc)}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_pipeline(args) -> int:
    debug_mod.flag(args.debug)  # sets CHELATE_DEBUG for skill subprocesses
    note = update_mod.notice()  # one line, cached for a day, never fatal
    if note:
        print(note, file=sys.stderr)
    root = os.path.abspath(args.root)
    inputs, missing = paths.resolve_inputs(root, args.inputs)
    if missing:
        print("input file(s) not found (resolved against --root "
              f"{root}): " + ", ".join(missing), file=sys.stderr)
        return 2
    selected = [s.strip() for s in args.selected.split(",") if s.strip()] if args.selected else None
    skill_args = parse_skill_args(args.skill_arg)
    result = router_run(
        root,
        mode=args.mode,
        input_kind=args.input_kind,
        inputs=inputs,
        selected=selected,
        dry_run=args.dry_run,
        skill_args=skill_args,
        timeout=args.timeout,
        debug=args.debug,
        allow_unverified=args.allow_unverified,
        publish=False,
    )
    # Publication is not the router's decision any more: it is a manifest
    # built from what the run produced, submitted through the selected
    # runtime (policy here, or the broker when one is configured).
    if not args.dry_run and not any(result.get(key) for key in
                                    ("terminated_by", "error", "blocked")):
        _publish_or_hold(root, result, inputs, selected, args)
    if getattr(args, "summary", False):
        # The per-skill line is already printed by the router; the full
        # decision record (every artifact, gate path and freshness field) is
        # a machine document, not something an agent needs to read back.
        planned = result.get("planned")
        if isinstance(planned, list):
            print(f"summary: {len(planned)} skill(s) planned (dry run)")
        else:
            tally = {}
            for rec in result.get("decisions") or []:
                key = str(rec.get("status", "?"))
                tally[key] = tally.get(key, 0) + 1
            counts = ", ".join(f"{k} {v}" for k, v in sorted(tally.items()))
            print(f"summary: {len(result.get('decisions') or [])} skill run(s)"
                  + (f" — {counts}" if counts else ""))
            line = f"promoted: {bool(result.get('promoted'))}"
            if result.get("blocked"):
                line += (f"  withheld: {result['blocked']} "
                         f"({result.get('reason', '')})")
            print(line)
        return 1 if (result.get("terminated_by") or result.get("error")
                      or result.get("blocked")) else 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # A withheld promotion is a refusal, not a success: a caller that
    # only reads the exit status must not see the run as complete.
    withheld = bool(result.get("blocked"))
    return 1 if (result.get("terminated_by") or result.get("error")
                  or withheld) else 0


def cmd_revoke(args) -> int:
    """Delete unused approval tokens for this workspace."""
    root = os.path.abspath(args.root)
    removed = approval.revoke(root, args.action or "")
    print(json.dumps({"root": root, "action": args.action or "*",
                      "revoked": removed}, indent=2))
    return 0


def cmd_rotate_key(args) -> int:
    """Replace the signing key; tokens issued before it stop verifying."""
    root = os.path.abspath(args.root)
    try:
        report = approval.rotate(root)
    except approval.HumanRequired as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"root": root, **report}, indent=2))
    return 0


def cmd_audit(args) -> int:
    """Report deliverables in results/ that no promotion put there."""
    note = update_mod.notice()  # the audit's verdict is worth trusting only
    if note:                    # from the published code
        print(note, file=sys.stderr)
    root = os.path.abspath(args.root)
    report = audit_results(root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def cmd_status(args) -> int:
    """Say which runtime is active and what a promotion would rest on."""
    root = os.path.abspath(args.root)
    try:
        report = runtime_mod.select().status(root)
    except (runtime_mod.RuntimeConfigError,
            runtime_mod.RuntimeUnavailable) as exc:
        print(json.dumps({"ok": False, "error": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    report = dict(report, ok=True, memory=memory_mod.summary(root))
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_recipe(args) -> int:
    """Run a workspace recipe serially; --dry-run and --graph stop first."""
    root = os.path.abspath(args.root)
    try:
        recipe = recipes_mod.load(root, args.name)
    except recipes_mod.RecipeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    if args.graph or args.dry_run:
        problems = recipes_mod.validate(recipe)
        if problems:
            print(json.dumps({"ok": False, "problems": problems},
                             ensure_ascii=False, indent=2))
            return 2
        payload = recipes_mod.graph(recipe) if args.graph \
            else {"recipe": recipe.name, "plan": recipes_mod.plan(recipe)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    try:
        report = recipes_mod.run(root, args.name, runtime=runtime_mod.select())
    except (recipes_mod.RecipeError, runtime_mod.RuntimeUnavailable,
            runtime_mod.RuntimeUnsupported,
            runtime_mod.RuntimeConfigError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["completed"] else 1


def cmd_hook(args) -> int:
    """Entry point a host hook calls: run this workspace's hooks for an event."""
    root = os.path.abspath(args.root)
    payload = {}
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = {"raw": raw}
    try:
        outcomes = hooks_mod.emit(root, args.event, payload)
    except hooks_mod.HookError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"event": args.event, "hooks": outcomes},
                     ensure_ascii=False, indent=2))
    return 0 if all(o.get("returncode") == 0 for o in outcomes) else 1


def cmd_memory(args) -> int:
    """Read or record a workspace note; only a person can reach `add`."""
    root = os.path.abspath(args.root)
    try:
        if args.memory_cmd == "add":
            entry = memory_mod.append(root, args.text, kind=args.kind,
                                      source=args.source, expires=args.expires,
                                      tags=args.tag)
            print(json.dumps({"ok": True, "entry": entry},
                             ensure_ascii=False, indent=2))
        elif args.memory_cmd == "forget":
            entry = memory_mod.forget(root, args.id, reason=args.reason)
            print(json.dumps({"ok": True, "tombstone": entry},
                             ensure_ascii=False, indent=2))
        elif args.memory_cmd == "list":
            rows = memory_mod.entries(root, include_all=args.all)
            if args.kind:
                rows = [row for row in rows if row.get("kind") == args.kind]
            print(json.dumps({"ok": True, "entries": rows},
                             ensure_ascii=False, indent=2, default=str))
        elif args.memory_cmd == "brief":
            sys.stdout.write(memory_mod.brief(root))
        else:
            state = memory_mod.verify(root)
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0 if state["ok"] else 2
    except memory_mod.MemoryStoreError as exc:
        print(json.dumps({"ok": False, "error": str(exc)},
                         ensure_ascii=False))
        return 2
    return 0


def cmd_update(args) -> int:
    """Say whether this copy is the published one, and refresh the hosts."""
    if args.apply:
        report = {
            "hosts": update_mod.installed_hosts(),
            "results": update_mod.apply(),
            "check": update_mod.check(force=True),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        failed = [r for r in report["results"]
                  if r.get("returncode") not in (0,)]
        return 1 if failed else 0

    result = update_mod.check(force=args.force)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not result["reachable"]:
        print("could not reach the repository; this copy's state is unknown")
    elif result["different"]:
        print("this copy differs from {}: {}".format(
            update_mod.BRANCH, ", ".join(str(f) for f in result["files"])))
        print("refresh it with: python cli.py update --apply")
    else:
        print("up to date ({} on {})".format(update_mod.BRANCH,
                                             result["local_version"]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cli.py", description="Chelate Shell microkernel CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    lp = sub.add_parser("list", help="list registered skills")
    lp.add_argument("--debug", action="store_true",
                    help="verbose stderr diagnostics (same as CHELATE_DEBUG=1)")
    lp.set_defaults(fn=cmd_list)

    pr = sub.add_parser("run", help="run a single skill")
    pr.add_argument("name")
    pr.add_argument("args", nargs=argparse.REMAINDER,
                    help="args passed to the skill run.py (incl. --root)")
    pr.add_argument("--debug", action="store_true",
                    help="verbose stderr diagnostics (same as CHELATE_DEBUG=1)")
    pr.set_defaults(fn=cmd_run)

    pp = sub.add_parser("pipeline", help="run a pipeline (mode a/b/c)")
    pp.add_argument("--root", default=".")
    pp.add_argument("--mode", choices=["a", "b", "c"], default="a")
    pp.add_argument("--input-kind", default="")
    pp.add_argument("--inputs", nargs="+", default=[], metavar="FILE",
                    help="input files for this run (workspace-relative or "
                         "absolute); each is forwarded as --input to the "
                         "plan skills that declare its type in the manifest")
    pp.add_argument("--selected", default="")
    pp.add_argument("--dry-run", action="store_true",
                    help="print the planned execution order without running")
    pp.add_argument("--summary", action="store_true",
                    help="print the per-skill lines and a one-line tally "
                         "instead of the full JSON decision record")
    pp.add_argument("--skill-arg", action="append", default=[],
                    metavar="SKILL:ARGS",
                    help='per-skill args, e.g. "reference-auditor:--input draft.md"')
    pp.add_argument("--timeout", type=int, default=600,
                    help="per-skill subprocess timeout in seconds")
    pp.add_argument("--debug", action="store_true",
                    help="verbose stderr diagnostics (same as CHELATE_DEBUG=1)")
    pp.add_argument("--no-approval", action="store_true",
                    help="skip the token and promote directly. Still needs a "
                         "human channel (a terminal, or "
                         f"{approval.UNSAFE_AUTO_ENV}=1), so an agent "
                         "subprocess cannot use it; for scripted runs a human "
                         "already supervises")
    pp.add_argument("--allow-unverified", action="store_true",
                    help="accept gates that ended UNVERIFIED (a check that "
                         "could not be made) and promote anyway. Bound into "
                         "the approval token: `approve --allow-unverified` "
                         "must have been used for the token to be spendable "
                         "here")
    pp.set_defaults(fn=cmd_pipeline)

    pa = sub.add_parser(
        "approve",
        help="issue a one-time approval token for an irreversible action "
             "(needs a terminal, or "
             "CHELATE_UNSAFE_AUTO_APPROVE=1)")
    pa.add_argument("--root", default=".")
    pa.add_argument("--action", default="promote",
                    choices=list(approval.IRREVERSIBLE_ACTIONS),
                    help="irreversible action to authorise (default: promote)")
    pa.add_argument("--mode", choices=["a", "b", "c"], default="a")
    pa.add_argument("--input-kind", default="")
    pa.add_argument("--inputs", nargs="+", default=[], metavar="FILE",
                    help="the same inputs you will pass to `pipeline`; their "
                         "content hashes are bound into the token")
    pa.add_argument("--selected", default="")
    pa.add_argument("--ttl", type=int, default=approval.DEFAULT_TTL_SECONDS,
                    help="seconds the token stays valid (default 900)")
    pa.add_argument("--allow-unverified", action="store_true",
                    help="bind this approval to a run that may promote past "
                         "an UNVERIFIED gate; without it, such a run is "
                         "refused even if the token is otherwise valid")
    pa.set_defaults(fn=cmd_approve)

    ppub = sub.add_parser(
        "publish",
        help="submit the pending manifest — the exact files an approval names")
    ppub.add_argument("--root", default=".")
    ppub.add_argument("--manifest", default="",
                      help="path to a pending manifest (default: "
                           ".chelate/pending/manifest.json)")
    ppub.add_argument("--no-approval", action="store_true",
                      help="skip the token. Every declared file is still "
                           "hashed while it is copied; for scripted runs a "
                           "human already supervises")
    ppub.set_defaults(fn=cmd_publish)

    pr_ = sub.add_parser(
        "revoke",
        help="delete unused approval tokens so they cannot be spent "
             "(tokens already consumed cannot be revoked)")
    pr_.add_argument("--root", default=".")
    pr_.add_argument("--action", default="promote",
                     help="which action's tokens to revoke (default: promote; "
                          "an empty string revokes all)")
    pr_.set_defaults(fn=cmd_revoke)

    pk = sub.add_parser(
        "rotate-key",
        help="replace this workspace's signing key. Tokens issued before the "
             "rotation stop working; promotion records written under the old "
             "key keep verifying. Needs a terminal")
    pk.add_argument("--root", default=".")
    pk.set_defaults(fn=cmd_rotate_key)

    pu = sub.add_parser(
        "audit",
        help="report files in results/ that no promotion accounts for "
             "(exit 1 when there are any)")
    pu.add_argument("--root", default=".")
    pu.set_defaults(fn=cmd_audit)

    ps = sub.add_parser(
        "status",
        help="show the active runtime (CHELATE_RUNTIME) and the gates a "
             "promotion would rest on")
    ps.add_argument("--root", default=".")
    ps.set_defaults(fn=cmd_status)

    prec = sub.add_parser(
        "recipe",
        help="run a workspace recipe serially; every step publishes nothing")
    prec.add_argument("--root", default=".")
    prec.add_argument("--name", required=True)
    prec.add_argument("--dry-run", action="store_true",
                      help="print what it would run and stop")
    prec.add_argument("--graph", action="store_true",
                      help="print the step graph and stop")
    prec.set_defaults(fn=cmd_recipe)

    ph = sub.add_parser(
        "hook",
        help="run this workspace's hooks for one event (the host's entry point)")
    ph.add_argument("--root", default=".")
    ph.add_argument("--event", required=True, choices=list(hooks_mod.EVENTS))
    ph.set_defaults(fn=cmd_hook)

    pm = sub.add_parser(
        "memory",
        help="workspace memory: notes a later session reads as data "
             "(only a person can add one)")
    mem = pm.add_subparsers(dest="memory_cmd", required=True)
    ma = mem.add_parser("add", help="record one note")
    ma.add_argument("--root", default=".")
    ma.add_argument("text", help="the note itself")
    ma.add_argument("--kind", default="fact", choices=list(memory_mod.KINDS))
    ma.add_argument("--source", default="human",
                    help="where the note came from (default: human)")
    ma.add_argument("--expires", default="",
                    help="YYYY-MM-DD after which the note stops being active")
    ma.add_argument("--tag", action="append", default=[],
                    help="one-word tag; repeat for more")
    ml = mem.add_parser("list", help="print the entries as JSON")
    ml.add_argument("--root", default=".")
    ml.add_argument("--all", action="store_true",
                    help="include withdrawn and expired entries")
    ml.add_argument("--kind", default="", choices=("",) + memory_mod.KINDS)
    mb = mem.add_parser("brief", help="the block a session should read first")
    mb.add_argument("--root", default=".")
    mf = mem.add_parser("forget", help="withdraw an entry (it stays on disk)")
    mf.add_argument("--root", default=".")
    mf.add_argument("--id", required=True, help="seq number or digest prefix")
    mf.add_argument("--reason", default="")
    mv = mem.add_parser("verify", help="recompute the hash chain")
    mv.add_argument("--root", default=".")
    pm.set_defaults(fn=cmd_memory)

    pbr = sub.add_parser(
        "broker",
        help="start, query or adopt the broker that holds the key and "
             "writes results/")
    bsub = pbr.add_subparsers(dest="broker_cmd", required=True)
    for name, help_text in (
            ("start", "serve the submit and approve channels (foreground)"),
            ("status", "ask the running broker what it is"),
            ("adopt", "take an existing 1.3.x workspace under the broker")):
        bsp = bsub.add_parser(name, help=help_text)
        bsp.add_argument("--root", default=".")
        bsp.set_defaults(fn=cmd_broker)

    psk = sub.add_parser(
        "skill",
        help="scaffold a new skill, or lint every skill's manifest and docs")
    ssub = psk.add_subparsers(dest="skill_cmd", required=True)
    snw = ssub.add_parser("new", help="write the mechanical half of a skill")
    snw.add_argument("name")
    snw.add_argument("--stage", required=True, choices=list(skillkit.STAGES))
    snw.add_argument("--version", default="1.4.0")
    snw.add_argument("--root", default="",
                     help="repository root (default: this checkout)")
    snw.set_defaults(fn=cmd_skill)
    sli = ssub.add_parser("lint", help="check manifest, docs and changelog")
    sli.add_argument("--root", default="")
    sli.set_defaults(fn=cmd_skill)

    pdoc = sub.add_parser(
        "doctor",
        help="which skills would degrade on this machine, and what to "
             "install to stop that")
    pdoc.add_argument("--root", default=".")
    pdoc.add_argument("--verbose", action="store_true",
                      help="list every skill, not only the degraded ones")
    pdoc.set_defaults(fn=cmd_doctor)

    pw = sub.add_parser(
        "update",
        help="check whether this installed copy is the published one, or "
             "refresh the hosts that have it installed (--apply)")
    pw.add_argument("--apply", action="store_true",
                    help="run each host's own update command")
    pw.add_argument("--force", action="store_true",
                    help="ignore the cached answer (24 h by default)")
    pw.add_argument("--json", action="store_true")
    pw.set_defaults(fn=cmd_update)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
