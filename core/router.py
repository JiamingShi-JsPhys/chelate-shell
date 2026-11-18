"""Chelate Shell router — microkernel dispatcher (manifest-driven pipeline).

Caller: cli.py (cmd_pipeline), tests/test_router.py.
Data schemas:
    Reads:  skills/<skill>/manifest.json via core.registry (routing table);
            each skill's GateResult JSON from process/gates/<skill>_<ts>.json
            (written by the skill's root-level run.py adapter).
    Writes: results/pipeline_report_<ts>.json, _broadcast/pipeline_index_<ts>.json,
            and — only when every gate passes — a promoted copy of process/
            under results/promoted_<ts>/.
User instruction: v1.1.0 blueprint section 3. The shape still holds; the
count below does not, and neither do the names, so the table is the only
list that matters (`python cli.py list` — 25 skills today):
    1. scan the manifests into an in-memory routing table;
    2. dispatch stage="ingest" skills matched by input type (e.g. PDF ->
       fulltext-extractor), then serially dispatch stage="gates" skills;
    3. hard block: the first gate returning FAIL terminates the pipeline
       immediately; intermediate products stay locked in process/ and never
       reach results/.

Adapter contract (every skill's root run.py):
    python run.py --root <workspace> --action <ingest|gate|process|workspace> [legacy args...]
    * writes a GateResult to process/gates/<skill>_<ts>.json (via bootstrap)
    * prints one JSON object {"gate": "<path>", "artifacts": [...]} on stdout
    * exits 0 on completion (including UNVERIFIED); non-zero only on crash

Pipeline modes:
    a  auto:      ingest (matched by --input-kind, or all) -> gates -> processors
    b  extract:   ingest only (matched by --input-kind, or all)
    c  gates:     gates only (--selected list, or every gates skill)
    --selected may name skills from any stage; they run in canonical
    stage order (workspace, ingest, gates, processors).

Degradation: skills whose manifest dependencies are missing still run; the
sandbox flags them degraded and the adapter is expected to emit an
UNVERIFIED gate (never a crash). Only FAIL terminates the pipeline.

Input wiring: `--inputs FILE ...` (cli.py pipeline, or router.run(inputs=...))
resolves each file against the workspace root, narrows the plan to the
skills whose manifest input_types declare the files' types (an explicit
--selected list always wins), and forwards each file as `--input` to the
matching adapters that define it (probed via --help). Explicit
--skill-arg flags are appended after the auto-wired ones, so they win
under argparse's last-value rule. A file whose extension declares no
manifest type wires to nothing and is reported as an [INPUT] warning.

Debug: pass --debug (or set CHELATE_DEBUG=1) to print the resolved command,
dependency verdict, return code and per-skill stderr tail to stderr for the
router and every skill subprocess; see lib/chelate_core/debug.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core import approval  # noqa: E402
from core.registry import Registry, load_default_registry  # noqa: E402
from core.sandbox import resolve_environment  # noqa: E402
from core import snapshot  # noqa: E402
from lib.chelate_core import debug as debug_mod  # noqa: E402
from lib.chelate_core import paths  # noqa: E402

STAGE_ORDER = ("workspace", "ingest", "gates", "processors")
STAGE_ACTION = {"workspace": "workspace", "ingest": "ingest",
                "gates": "gate", "processors": "process",
                "infrastructure": "gate", "generation": "process",
                "domain_extensions": "process"}

# File extension -> manifest input_types token. The Router wires each
# --inputs file to the plan skills that declare its type, so
# `--inputs draft.md` reaches reference-auditor without repeating the path
# through --skill-arg.
INPUT_TYPE_BY_EXT = {
    "md": "markdown", "markdown": "markdown",
    "txt": "plain_text", "text": "plain_text",
    "csv": "csv", "tsv": "csv",
    "pdf": "pdf",
    "bib": "bib",
    "cap": "cap",
    "tex": "latex_string",
    "yaml": "config", "yml": "config", "json": "config",
    "py": "python", "pyi": "python",
    "mp4": "video", "mov": "video", "avi": "video", "mkv": "video",
}

_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _color(text: str, code: str, stream=None) -> str:
    """ANSI-colorize when the target stream is a TTY and NO_COLOR is unset.

    Set CHELATE_FORCE_COLOR=1 to colorize even when the stream is not a TTY
    (used by the acceptance harness to verify the red FAIL output).
    """
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR"):
        return text
    if not os.environ.get("CHELATE_FORCE_COLOR"):
        try:
            if not stream.isatty():
                return text
        except Exception:
            return text
    return f"{code}{text}{_RESET}"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_plan(reg: Registry, mode: str, input_kind: str,
               selected: Optional[List[str]]) -> Dict[str, list]:
    """Return {stage: [SkillRecord, ...]} for the requested pipeline mode."""
    plan: Dict[str, list] = {s: [] for s in STAGE_ORDER}
    if mode == "b":
        plan["ingest"] = reg.by_input(input_kind, stage="ingest")
    elif mode == "c":
        pool = reg.by_stage("gates")
        if selected:
            wanted = [s.strip() for s in selected if s.strip()]
            pool = [r for r in reg.all() if r.name in wanted]
        plan["gates"] = pool
    else:  # mode "a" — full auto pipeline
        plan["ingest"] = reg.by_input(input_kind, stage="ingest")
        plan["gates"] = reg.by_stage("gates")
        plan["processors"] = reg.by_stage("processors")
    return plan


def _adapter_accepts_input(rec, cache: Optional[Dict[str, bool]] = None) -> bool:
    """True when the skill's run.py defines a --input flag (probed via --help).

    Probing keeps the wiring manifest-driven without hardcoding skill names:
    legacy adapters take their arguments through --legacy and must never
    receive --input. A probe failure is treated as "does not accept".
    `cache` (a per-run dict) memoizes the verdict per skill name, so a
    pipeline with N input files probes each skill at most once instead of
    N times.
    """
    if cache is None:
        cache = {}
    elif rec.name in cache:
        return cache[rec.name]
    try:
        proc = subprocess.run([sys.executable, rec.run_path, "--help"],
                              cwd=_REPO_ROOT, capture_output=True,
                              text=True, timeout=60)
    except Exception as exc:
        print(_color(
            f"[INPUT] warning: could not probe '{rec.name}' --help "
            f"({exc}); assuming it does not accept --input", _YELLOW))
        cache[rec.name] = False
        return False
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-2:]
        print(_color(
            f"[INPUT] warning: '{rec.name}' --help exited rc={proc.returncode}"
            f"{' (' + ' | '.join(tail) + ')' if tail else ''}; "
            f"assuming it does not accept --input", _YELLOW))
        cache[rec.name] = False
        return False
    result = "--input" in (proc.stdout or "") or "--input" in (proc.stderr or "")
    cache[rec.name] = result
    return result


def _ext_of(path: str) -> str:
    """Lower-case extension without the dot ("" when the path has none)."""
    return os.path.splitext(os.path.basename(str(path)))[1].lstrip(".").lower()


def _input_tokens_by_file(inputs) -> List[tuple]:
    """[(path, manifest input_type token)] per declared input file.

    The token is None when the file's extension declares no manifest type;
    such a file wires to nothing (run() reports it as an [INPUT] warning).
    """
    return [(str(raw), INPUT_TYPE_BY_EXT.get(_ext_of(raw)))
            for raw in inputs or []]


def _auto_input_args(flat, inputs, probe=None):
    """Map skill name -> ["--input", path] for the declared input types.

    `flat` is the [(stage, SkillRecord)] plan built for this run; `probe`
    decides whether a matched adapter accepts --input (defaults to the
    --help probe, injectable for tests). Returns (auto, warnings): `auto`
    holds the first matching file per skill (every adapter's --input is
    single-valued), `warnings` explains files whose type reached no
    --input-capable skill. Unknown extensions are skipped here — run()
    reports them before the plan is built.
    """
    probe = probe or _adapter_accepts_input
    cache: Dict[str, bool] = {}
    auto: Dict[str, List[str]] = {}
    warnings: List[str] = []
    for path, token in _input_tokens_by_file(inputs):
        if token is None:
            continue
        wired = False
        for _stage, rec in flat:
            types = [str(t).lower()
                     for t in getattr(rec, "input_types", [])]
            if token not in types:
                continue
            accepts = probe(rec, cache) if probe is _adapter_accepts_input \
                else probe(rec)
            if not accepts:
                continue
            if rec.name in auto:
                warnings.append(
                    f"{rec.name} accepts a single --input; keeping "
                    f"{auto[rec.name][1]}, ignoring {path}")
                continue
            auto[rec.name] = ["--input", path]
            wired = True
        if not wired:
            warnings.append(
                f"no skill in the plan accepts --input for type "
                f"'{token}' ({path})")
    return auto, warnings


def run_skill(rec, root: str, action: str, extra_args: List[str],
              timeout: int = 600, debug: bool = False) -> dict:
    """Execute one skill adapter and collect its decision.

    Skills whose manifest declares ``sandbox_required: true`` are dispatched
    through ``run_skill_sandboxed`` (a true ``multiprocessing`` child with a
    circuit-breaker) instead of a bare ``subprocess.run``.  The sandbox path
    reports a timeout as UNVERIFIED, never as FAIL, so a hung heavy
    dependency cannot hard-block the pipeline.  Skills without that flag use
    the lighter-weight v1.1.x subprocess path.
    """
    from core.sandbox import run_skill_sandboxed  # local import; safe cycle

    if getattr(rec, "sandbox_required", False):
        if debug:
            debug_mod.log(f"{rec.name}: dispatching via sandbox "
                          f"(timeout={timeout}s)")
        outcome = run_skill_sandboxed(rec, root, action, extra_args,
                                     timeout=timeout, debug=debug)
        # fold the sandbox outcome into the same record shape run_skill uses
        record = {
            "skill": rec.name,
            "stage": rec.stage,
            "action": action,
            "command": [sys.executable, rec.run_path, "--root", root,
                        "--action", action, *list(extra_args)],
            "degraded": bool(outcome.get("missing")),
            "missing": list(outcome.get("missing", [])),
        }
        record.update(
            status=outcome["status"],
            evidence_level=outcome.get("evidence_level", "UNVERIFIED"),
            reason=outcome.get("reason", ""),
            returncode=outcome.get("returncode", -1),
            gate=None,
            artifacts=list(outcome.get("artifacts", [])),
            seconds=outcome.get("seconds", 0),
            sandbox=outcome.get("timeout", False),
        )
        if debug:
            debug_mod.log(f"{rec.name}: sandbox outcome "
                          f"status={record['status']} "
                          f"seconds={record.get('seconds')} "
                          f"timeout={record['sandbox']}")
        return record

    debug_on = debug_mod.flag(debug)
    started = time.time()
    cmd = [sys.executable, rec.run_path, "--root", root, "--action", action]
    cmd += list(extra_args)
    decision = resolve_environment(rec.dependencies)
    env = decision.env()
    degraded = decision.degraded
    record = {
        "skill": rec.name,
        "stage": rec.stage,
        "action": action,
        "command": cmd,
        "degraded": degraded,
        "missing": list(decision.missing),
    }
    if debug_on:
        debug_mod.log(f"{rec.name}: exec {' '.join(cmd)} (cwd={_REPO_ROOT}, "
                      f"degraded={degraded}, missing={list(decision.missing)})")
    try:
        proc = subprocess.run(cmd, cwd=_REPO_ROOT, env=env, timeout=timeout,
                              capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        record.update(status="FAIL", evidence_level="UNVERIFIED",
                      reason=f"skill timed out after {timeout}s",
                      returncode=-1, gate=None, artifacts=[])
        return record
    record["returncode"] = proc.returncode
    if debug_on:
        debug_mod.log(f"{rec.name}: rc={proc.returncode} "
                      f"seconds={round(time.time() - started, 2)}")
        for line in (proc.stderr or "").strip().splitlines()[-5:]:
            debug_mod.log(f"{rec.name}: stderr| {line}")
    payload = _parse_stdout(proc.stdout)
    gate_path = payload.get("gate") if isinstance(payload, dict) else None
    if not gate_path:
        gate_path = _newest_gate(root, rec.name, started)
    record["gate"] = gate_path
    record["artifacts"] = list(payload.get("artifacts", [])) if isinstance(payload, dict) else []
    if gate_path and os.path.isfile(gate_path):
        try:
            from contracts import GateResult
            gate = GateResult.from_json(gate_path)
            record.update(status=gate.status.value,
                          evidence_level=gate.evidence_level.value,
                          reason=gate.reason,
                          artifacts=gate.artifacts or record["artifacts"])
        except Exception as exc:
            # A gate file that exists but cannot be parsed is a report we
            # cannot trust, not a proven failure: degrade to UNVERIFIED.
            # (A hard FAIL is reserved for the adapter itself crashing.)
            record.update(status="UNVERIFIED", evidence_level="UNVERIFIED",
                          reason=f"corrupt gate result ({exc}); "
                                 f"downgraded from FAIL to UNVERIFIED")
    elif proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        record.update(status="FAIL", evidence_level="UNVERIFIED",
                      reason="adapter crashed (rc=%d): %s" % (proc.returncode, " | ".join(tail)))
    else:
        record.update(status="UNVERIFIED", evidence_level="UNVERIFIED",
                      reason="adapter produced no gate result (contract violation)")
    record["seconds"] = round(time.time() - started, 2)
    return record


def _parse_stdout(stdout: str):
    """Extract the last JSON object printed by the adapter (best effort)."""
    from lib.chelate_core.adapter import last_json
    return last_json(stdout)


def _newest_gate(root: str, skill: str, after: float) -> Optional[str]:
    gates_dir = os.path.join(root, "process", "gates")
    if not os.path.isdir(gates_dir):
        return None
    candidates = [os.path.join(gates_dir, f) for f in os.listdir(gates_dir)
                  if f.startswith(skill + "_") and f.endswith(".json")]
    candidates = [p for p in candidates if os.path.getmtime(p) >= after - 1.0]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def _print_decision(record: dict) -> None:
    status = record.get("status", "UNVERIFIED")
    skill = record["skill"]
    reason = record.get("reason", "")
    line = f"[{status:<10}] {skill:<28} {reason}".rstrip()
    if status == "PASS":
        print(_color(line, _GREEN))
    elif status == "FAIL":
        print(_color(f"[GATE FAIL] {skill}: {reason}", _RED), file=sys.stderr)
        print(_color(line, _RED))
    else:
        print(_color(line, _YELLOW))


PROMOTION_LOG = ".promotions.jsonl"


class PromotionLocked(RuntimeError):
    """Raised when process/ still holds a gate that failed."""


def gate_records(root: str) -> Dict[str, Dict[str, Any]]:
    """The newest gate per skill, with its file name and parsed body.

    `{skill: {"gate": "process/gates/x.json", "data": {...}}}`.  Gates that
    cannot be parsed are skipped rather than guessed at.
    """
    gates_dir = os.path.join(root, "process", "gates")
    if not os.path.isdir(gates_dir):
        return {}
    newest: Dict[str, tuple] = {}
    for name in sorted(os.listdir(gates_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(gates_dir, name), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        skill = str(data.get("skill") or name.rsplit("_", 1)[0])
        stamp = str(data.get("timestamp") or "")
        newest[skill] = (stamp, name, data)
    return {skill: {"gate": f"process/gates/{name}", "data": data}
            for skill, (_stamp, name, data) in newest.items()}


def failed_gates(root: str) -> List[Dict[str, str]]:
    """The newest gate per skill, where that newest gate is a ``FAIL``.

    The pipeline stops at the first ``FAIL``, but a later run plans only its
    own stages: a ``FAIL`` left in ``process/gates/`` would otherwise be
    copied into ``results/`` by the next promotion, and the deliverable would
    carry a failed check that nobody looked at. Re-running the skill writes a
    newer gate, which is how a failure is cleared.
    """
    out: List[Dict[str, str]] = []
    for skill, rec in sorted(gate_records(root).items()):
        data = rec["data"]
        if str(data.get("status") or "").upper() == "FAIL":
            out.append({"skill": skill, "gate": str(rec["gate"]),
                        "reason": str(data.get("reason") or "")})
    return out


def unverified_gates(root: str) -> List[Dict[str, str]]:
    """The newest gate per skill, where that newest gate is ``UNVERIFIED``.

    ``UNVERIFIED`` means the check could not be made — a missing dependency,
    a timeout, an unreadable format.  It is not evidence of correctness, so
    it may not by itself carry a result into ``results/``; see promote().
    """
    out: List[Dict[str, str]] = []
    for skill, rec in sorted(gate_records(root).items()):
        data = rec["data"]
        if str(data.get("status") or "").upper() == "UNVERIFIED":
            out.append({"skill": skill, "gate": str(rec["gate"]),
                        "reason": str(data.get("reason") or "")})
    return out


def _current_skill_digest(skill: str) -> str:
    """Digest the skill's code the same way bootstrap.skill_provenance does."""
    import bootstrap  # local import: bootstrap sits at the repository root
    try:
        return str(bootstrap.skill_provenance(skill).get("skill_digest", ""))
    except Exception:
        return ""


def skill_lock_digest() -> str:
    """Digest over every registered skill's name, version and code bytes.

    A manifest carries this so an approval issued against one skill set
    cannot be spent after the code changed. `_current_skill_digest` is the
    same per-skill digest the gate freshness check uses, so the lock and the
    gates agree about what "this skill's code" means.
    """
    from core import registry
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "skills")
    digest = hashlib.sha256()
    for record in sorted(registry.Registry().scan(skills_dir).all(),
                         key=lambda r: r.name):
        digest.update(f"{record.name}:{record.version}:"
                      f"{_current_skill_digest(record.name)}\n".encode("utf-8"))
    return digest.hexdigest()


def stale_gates(root: str) -> List[Dict[str, str]]:
    """Gates whose recorded inputs or code no longer match the workspace.

    A gate answers a question about specific bytes.  If an input file changed
    after the gate ran, or the skill's own code changed, the answer no longer
    describes what is on disk — so it is not a PASS, it is an expired one.
    The fix is to re-run the skill, which writes a newer gate.

    Gates written before 1.3.6 carry no digests at all.  They are reported
    under ``unbound`` by :func:`gate_freshness` rather than silently trusted:
    they cannot be checked, and this function does not pretend otherwise.
    """
    out: List[Dict[str, str]] = []
    for skill, rec in sorted(gate_records(root).items()):
        data = rec["data"]
        if str(data.get("status") or "").upper() != "PASS":
            continue
        bound = data.get("inputs") or {}
        provenance = data.get("provenance") or {}
        if not isinstance(bound, dict):
            bound = {}
        if not isinstance(provenance, dict):
            provenance = {}
        if not bound and not provenance:
            continue  # unbound: reported separately, not called stale
        changed: List[str] = []
        for rel, recorded in sorted(bound.items()):
            recorded = str(recorded)
            # The adapter was handed a snapshot path; what the promotion has
            # to answer is whether the user's own file still holds the bytes
            # that were frozen, so the comparison runs against the original
            # named in the snapshot's manifest.
            origin = snapshot.origin_of(root, str(rel))
            if origin and origin.get("original"):
                rel = origin["original"]
                recorded = origin.get("sha256") or recorded
            if str(rel).startswith("external:"):
                full = str(rel)[len("external:"):]
            else:
                full = os.path.join(root, str(rel).replace("/", os.sep))
            try:
                if recorded.startswith("large:"):
                    # Bound by size, not by digest: large inputs are compared
                    # the same way they were recorded.
                    current = f"large:{os.path.getsize(full)}"
                else:
                    current = _sha256_file(full)
            except OSError:
                changed.append(f"{rel} (missing)")
                continue
            if recorded != current:
                changed.append(str(rel))
        recorded_digest = str(provenance.get("skill_digest") or "")
        if recorded_digest:
            current_digest = _current_skill_digest(skill)
            if current_digest and current_digest != recorded_digest:
                changed.append(f"skill code ({skill})")
        if changed:
            out.append({"skill": skill, "gate": str(rec["gate"]),
                        "reason": "changed after the gate ran: "
                                  + ", ".join(changed)})
    return out


def gate_freshness(root: str) -> Dict[str, object]:
    """A census of the gates that a promotion would rest on.

    ``bound``   — newest PASS gates carrying input/code digests
    ``unbound`` — newest PASS gates from before v1.3.6, which verify nothing
    ``stale``   — bound gates whose inputs or code changed since
    """
    records = gate_records(root)
    bound = unbound = 0
    for rec in records.values():
        data = rec["data"]
        if str(data.get("status") or "").upper() != "PASS":
            continue
        if data.get("inputs") or data.get("provenance"):
            bound += 1
        else:
            unbound += 1
    stale = stale_gates(root)
    return {"gates": len(records), "bound": bound, "unbound": unbound,
            "stale": stale,
            "unbound_skills": sorted(
                skill for skill, rec in records.items()
                if str(rec["data"].get("status") or "").upper() == "PASS"
                and not (rec["data"].get("inputs")
                         or rec["data"].get("provenance")))}


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digests_under(root: str, base: str) -> Dict[str, str]:
    """Map workspace-relative posix paths under *base* to their SHA-256."""
    out: Dict[str, str] = {}
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            full = os.path.join(dirpath, name)
            out[os.path.relpath(full, root).replace(os.sep, "/")] = (
                _sha256_file(full))
    return out


def _record_promotion(root: str, dst: str, stamp: str,
                      approval_info: Optional[Dict]) -> None:
    """Append one line to results/.promotions.jsonl.

    The log is what makes a bypass visible. Anything in `results/` that no
    entry lists was not put there by a promotion, and `audit_results()`
    says so by name.

    Each entry is HMAC-signed with the workspace's approval key, which lives
    outside the workspace. The key exists as soon as anything approved in
    this workspace, so a hand-written line — the obvious next move for an
    agent that has read this file — does not verify.
    """
    entry = {
        "action": "promote",
        "stamp": stamp,
        "at": _iso_now(),
        "promoted_to": os.path.relpath(dst, root).replace(os.sep, "/"),
        "approval": approval_info or {},
        "files": _digests_under(root, dst),
    }
    # A scripted run has no token, so nothing has created a key yet; it is
    # still a declared run (CHELATE_UNSAFE_AUTO_APPROVE=1), so it may
    # mint one — and the record says `unsafe_auto` rather than `human`.
    create = (approval_info or {}).get("source") == "scripted-run"
    mac = approval.sign(root, entry, create=create)
    if mac:
        entry["mac"] = mac
    log = os.path.join(root, "results", PROMOTION_LOG)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# Every pipeline report carries these; a file that lacks them is not one.
REPORT_KEYS = ("root", "mode", "started", "decisions", "promoted", "blocked")


def _looks_like_report(path: str) -> bool:
    """True when *path* parses as a pipeline report this shell wrote.

    The exemption for reports is by name and by shape. A deliverable that
    an agent renamed to `pipeline_report_*.json` will not have the fields a
    report always has, so it is still reported as unapproved.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and all(k in data for k in REPORT_KEYS)


def audit_results(root: str) -> Dict[str, object]:
    """Report files in results/ that no promotion accounts for.

    The approval gate binds `promote()`. It cannot stop a process that
    writes into `results/` with its own hands — a shell, an editor, an
    agent's file tool — so this is the monitoring half: every promoted
    file is logged with its digest, everything else is named.

    Entries are trusted only when they carry a valid signature from the
    per-workspace key, once that key exists. A forged or unreadable line is
    reported under `tampered` and grants nothing.

    Oracle for `python cli.py audit --root <ws>`; the pipeline embeds the
    same dict in every report as `results_audit`.
    """
    results_dir = os.path.join(root, "results")
    if not os.path.isdir(results_dir):
        return {"ok": True, "promotions": 0, "unapproved": [],
                "modified": [], "tampered": []}

    approved: Dict[str, str] = {}
    promotions = 0
    tampered: List[str] = []
    parsed: List[tuple] = []
    log = os.path.join(results_dir, PROMOTION_LOG)
    if os.path.isfile(log):
        with open(log, encoding="utf-8", errors="replace") as fh:
            for number, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    tampered.append(f"line {number}: not JSON")
                    continue
                if not isinstance(entry, dict):
                    tampered.append(f"line {number}: not an object")
                    continue
                parsed.append((number, entry))

    # One signed entry means this workspace was keyed when it ran, so every
    # entry has to verify. A key that cannot be found is not a reason to stop
    # checking — the key living elsewhere is exactly what the signature is
    # for — so that case fails closed instead.
    require_signature = approval.has_key(root) or any(
        "mac" in entry for _, entry in parsed)

    for number, entry in parsed:
        entry = dict(entry)
        mac = entry.pop("mac", None)
        if require_signature and not (isinstance(mac, str)
                                      and approval.verify(root, entry, mac)):
            tampered.append(f"line {number}: signature does not verify")
            continue
        files = entry.get("files")
        if not isinstance(files, dict):
            tampered.append(f"line {number}: no file list")
            continue
        promotions += 1
        for rel, digest in files.items():
            approved[str(rel).replace("\\", "/")] = digest

    unapproved: List[str] = []
    modified: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(results_dir):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel == f"results/{PROMOTION_LOG}":
                continue
            # The orchestrator writes its own reports here; they are not
            # deliverables and are not supposed to carry an approval.
            if (os.path.dirname(rel) == "results"
                    and name.startswith("pipeline_report_")
                    and _looks_like_report(full)):
                continue
            if rel not in approved:
                unapproved.append(rel)
            elif approved[rel] != _sha256_file(full):
                modified.append(rel)

    return {
        "ok": not unapproved and not modified and not tampered,
        "promotions": promotions,
        "unapproved": sorted(unapproved),
        "modified": sorted(modified),
        "tampered": tampered,
    }


def _process_tree_problems(root: str, src: str) -> List[str]:
    """Links inside process/ that would move bytes across the boundary.

    A promotion copies process/ into results/. Two shapes of link turn that
    copy into a way to move a file the workspace never held:

    * a symlink whose target resolves outside the workspace — ``copytree``
      follows it and the content lands in results/ (an agent can point one at
      any file the user can read);
    * a hardlink, which has no target to resolve: the same bytes are reachable
      under two names, and the name inside the workspace looks ordinary.

    Both are refused rather than copied. A symlink that stays inside the
    workspace is kept as a symlink and is harmless.
    """
    problems: List[str] = []
    if not os.path.isdir(src):
        return problems
    for dirpath, dirnames, filenames in os.walk(src):
        for name in list(dirnames) + list(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                info = os.lstat(full)
            except OSError:
                continue
            if os.path.islink(full):
                try:
                    paths.ensure_within(root, os.path.realpath(full),
                                        what="symlink target")
                except Exception:
                    problems.append(f"symlink leaves the workspace: {rel}")
                continue
            if not os.path.isfile(full):
                continue
            # st_nlink counts names for the inode; >1 means another name
            # exists somewhere — possibly outside the workspace.
            if getattr(info, "st_nlink", 1) > 1:
                problems.append(f"hardlinked file: {rel}")
    return problems


def _recover_staging(staging_root: str) -> None:
    """Delete leftover staging trees from an interrupted promotion.

    A staging tree is never a deliverable: it exists only between the copy
    and the rename that publishes it.  Anything still there on the next run
    belongs to a promotion that died half-way, and must not be resumed —
    ``promote()`` starts from a clean copy every time.
    """
    if not os.path.isdir(staging_root):
        return
    for name in os.listdir(staging_root):
        leftover = os.path.join(staging_root, name)
        try:
            if os.path.isdir(leftover) and not os.path.islink(leftover):
                shutil.rmtree(leftover)
            else:
                os.remove(leftover)
        except OSError:
            pass


_WINDOWS_DEVICES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)})


def _stage_declared(root: str, files: List[Dict[str, str]],
                    staging: str) -> None:
    """Copy exactly the declared files, hashing the bytes as they are written.

    Checking a digest and then copying leaves a window in which the file can
    change between the two reads. Here the bytes that are written are the
    bytes that are hashed, and the comparison is against the digest the
    person approved: a mismatch aborts the whole promotion, leaving nothing
    visible in ``results/``.
    """
    if not files:
        raise PromotionLocked("the manifest declares no files to publish")
    os.makedirs(staging, exist_ok=True)
    for item in files:
        rel = str(item.get("path", "")).replace("\\", "/")
        expected = str(item.get("sha256", "")).lower()
        if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
            raise PromotionLocked(f"declared output {rel!r} is not relative")
        parts = [part for part in rel.split("/") if part]
        if not parts or ".." in parts:
            raise PromotionLocked(f"declared output {rel!r} escapes the "
                                  f"workspace")
        # The manifest validator refuses these too; promotion checks them
        # again because it is the code that opens the file. On Windows ":"
        # starts an alternate data stream and a device name is not a file.
        if ":" in rel:
            raise PromotionLocked(f"declared output {rel!r} contains ':'")
        for part in parts:
            if part.split(".", 1)[0].strip().lower() in _WINDOWS_DEVICES:
                raise PromotionLocked(f"declared output {rel!r} names a "
                                      f"Windows device")
        src = os.path.join(root, *parts)
        paths.ensure_within(root, src, what="declared output")
        if os.path.islink(src) or not os.path.isfile(src):
            raise PromotionLocked(
                f"declared output {rel} is not a regular file in the workspace")
        target = parts[1:] if parts[0] == "process" else parts
        dst = os.path.join(staging, *target)
        paths.ensure_within(staging, dst, what="staged output")
        folder = os.path.dirname(dst)
        if folder:
            os.makedirs(folder, exist_ok=True)
        digest = hashlib.sha256()
        # O_NOFOLLOW where the platform has it: the islink() check above and
        # this open() are two syscalls, and a link swapped between them would
        # otherwise be followed. Windows has no such flag; there the tree
        # check in _process_tree_problems is the guard.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(src, flags)
        with os.fdopen(fd, "rb") as fin, open(dst, "wb") as fout:
            for chunk in iter(lambda: fin.read(1 << 20), b""):
                digest.update(chunk)
                fout.write(chunk)
        if digest.hexdigest() != expected:
            raise PromotionLocked(
                f"declared output {rel} changed between approval and "
                f"publication; re-run the skill and approve the new manifest")


def promote(root: str, stamp: str,
            approval_info: Optional[Dict] = None,
            allow_unverified: bool = False,
            files: Optional[List[Dict[str, str]]] = None,
            manifest_sha256: str = "") -> Optional[str]:
    """Publish process/ into results/promoted_<stamp>/ — atomically.

    Three checks stand between a run and a deliverable, and each of them
    fails closed:

    * a newest gate that is ``FAIL`` locks the workspace (as in 1.3.6);
    * a newest gate that is ``UNVERIFIED`` — a check that could not be made —
      blocks the promotion unless the caller asked for the override, which is
      recorded (see `allow_unverified`);
    * a newest gate that is ``PASS`` but whose recorded input digests or
      skill digest no longer match the workspace has *expired*: it judged
      bytes that are no longer there.

    The copy itself lands in `.<workspace>/.chelate/staging/` first and is
    then renamed onto `results/`.  A crash mid-copy leaves a partial tree in
    staging, which is invisible to every reader and is removed on the next
    run; `results/` only ever sees a complete set.
    """
    src = os.path.join(root, "process")
    if not os.path.isdir(src):
        return None
    failed = failed_gates(root)
    if failed:
        raise PromotionLocked(
            "process/ holds a failed gate ("
            + ", ".join(sorted({f["skill"] for f in failed}))
            + "); fix the input and re-run that skill")
    stale = stale_gates(root)
    if stale:
        raise PromotionLocked(
            "process/ holds an expired gate ("
            + ", ".join(sorted({s["skill"] for s in stale}))
            + "): its input or skill code changed after it ran; re-run that "
              "skill so the PASS describes the files on disk")
    unverified = unverified_gates(root)
    if unverified and not allow_unverified:
        raise PromotionLocked(
            "process/ holds an unverified gate ("
            + ", ".join(sorted({u["skill"] for u in unverified}))
            + "): the check could not be made, so it does not carry a result "
              "into results/. Re-run it with its dependency installed, or "
              "pass --allow-unverified to accept it deliberately")
    problems = _process_tree_problems(root, src)
    if problems:
        raise PromotionLocked(
            "process/ holds a link that would move bytes across the boundary ("
            + "; ".join(problems)
            + "); remove it, or replace it with the file itself if it belongs "
              "in the deliverable")
    dst = os.path.join(root, "results", f"promoted_{stamp}")
    # The promotion target is derived from a timestamp, but it is still a
    # write: prove it lands inside the workspace before copying anything.
    paths.ensure_within(root, dst, what="promotion target")
    staging_root = os.path.join(root, ".chelate", "staging")
    _recover_staging(staging_root)
    os.makedirs(staging_root, exist_ok=True)
    staging = os.path.join(staging_root, f"promoted_{stamp}")
    if files is None:
        shutil.copytree(src, staging, symlinks=True)
    else:
        _stage_declared(root, files, staging)
    # results/ appears only once the set is complete: a refused promotion
    # leaves no empty directory that reads like a deliverable.
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(staging, dst)  # one rename: the whole set, or nothing
    info = dict(approval_info or {})
    info["allow_unverified"] = bool(allow_unverified)
    info["freshness"] = gate_freshness(root)
    if files is not None:
        info["manifest_sha256"] = str(manifest_sha256 or "")
        info["files"] = len(files)
    _record_promotion(root, dst, stamp, info)
    return dst


def write_reports(root: str, result: dict) -> Dict[str, str]:
    """Write results/pipeline_report_<ts>.json + _broadcast/pipeline_index_<ts>.json."""
    stamp = _ts()
    paths: Dict[str, str] = {}
    results_dir = os.path.join(root, "results")
    os.makedirs(results_dir, exist_ok=True)
    report_path = os.path.join(results_dir, f"pipeline_report_{stamp}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    paths["report"] = report_path
    broadcast_dir = os.path.join(root, "_broadcast")
    os.makedirs(broadcast_dir, exist_ok=True)
    index = {
        "generated": result.get("finished"),
        "terminated_by": result.get("terminated_by"),
        "promoted": result.get("promoted"),
        "inputs": result.get("inputs", []),
        "entries": [
            {"skill": d["skill"], "stage": d["stage"], "status": d.get("status"),
             "evidence_level": d.get("evidence_level"), "gate": d.get("gate"),
             "artifacts": d.get("artifacts", [])}
            for d in result.get("decisions", [])
        ],
    }
    index_path = os.path.join(broadcast_dir, f"pipeline_index_{stamp}.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    paths["broadcast"] = index_path
    return paths


# Extensions whose content is worth scanning for prompt-injection markers
# before the pipeline processes them. Binary / heavy formats are skipped.
_TEXT_INPUT_EXTS = frozenset({
    "md", "markdown", "txt", "text", "json", "yaml", "yml", "tex", "bib",
    "csv", "py", "html", "xml", "rst",
})


def _scan_inputs_for_injection(inputs, root: str):
    """Pre-dispatch guard (#132): scan text inputs for injection markers.

    An external file carrying a high-confidence prompt-injection marker is a
    poisoned input that must not be allowed to steer the downstream skills.
    On a hit we write a FAIL gate (mirroring security-guard) and return a
    decision record that hard-blocks the pipeline; on a miss we return None
    and the pipeline proceeds normally.

    Conservative by design: only the narrow, high-confidence pattern set in
    ``core.security_shield.INJECTION_PATTERNS`` blocks, so legitimate
    scientific prose is never wrongly dropped.
    """
    from core.security_shield import scan_text

    gates_dir = os.path.join(root, "process", "gates")
    os.makedirs(gates_dir, exist_ok=True)
    for raw in inputs or []:
        p = pathlib.Path(raw)
        if p.suffix.lstrip(".").lower() not in _TEXT_INPUT_EXTS:
            continue
        if not p.is_file():
            alt = pathlib.Path(root) / raw
            p = alt if alt.is_file() else p
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        verdict = scan_text(text)
        if not verdict.get("blocked"):
            continue
        stamp = _ts()
        gate_path = os.path.join(gates_dir, f"injection-scan_{stamp}.json")
        payload = {
            "skill": "injection-scan",
            "status": "FAIL",
            "blocked": True,
            "reason": "prompt-injection markers in input: "
                      + ", ".join(verdict.get("hits", [])),
            "artifacts": [str(p)],
        }
        with open(gate_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return {
            "skill": "injection-scan",
            "stage": "ingest",
            "action": "scan",
            "status": "FAIL",
            "evidence_level": "UNVERIFIED",
            "reason": payload["reason"],
            "gate": gate_path,
            "artifacts": [str(p)],
            "seconds": 0,
        }
    return None


def _skill_arg_inputs(skill_args, root: str) -> List[str]:
    """Files named by ``--skill-arg ... --input <file>``, as absolute paths."""
    found: List[str] = []
    for args in (skill_args or {}).values():
        previous = ""
        for token in args:
            if previous == "--input" and token and not token.startswith("-"):
                absolute = token if os.path.isabs(token)                     else os.path.join(root, token)
                if os.path.isfile(absolute):
                    found.append(absolute)
            previous = token
    return found


def _rewrite_skill_args(skill_args, mapping: Dict[str, str]):
    """Replace every frozen input path in ``--skill-arg`` with its snapshot."""
    if not skill_args:
        return skill_args
    rewritten: Dict[str, List[str]] = {}
    for skill, args in skill_args.items():
        out: List[str] = []
        previous = ""
        for token in args:
            replaced = token
            if previous == "--input":
                for original, frozen_path in mapping.items():
                    if os.path.abspath(token) in (original,
                                                  os.path.abspath(original)):
                        replaced = frozen_path
                        break
            out.append(replaced)
            previous = token
        rewritten[skill] = out
    return rewritten


def run(root: str, mode: str = "a", input_kind: str = "",
        inputs: Optional[List[str]] = None,
        selected: Optional[List[str]] = None, dry_run: bool = False,
        extra_args: Optional[List[str]] = None,
        skill_args: Optional[Dict[str, List[str]]] = None,
        timeout: int = 600, debug: bool = False,
        require_approval: bool = True,
        allow_unverified: bool = False,
        publish: bool = True) -> dict:
    """Execute the pipeline; returns the full decision record (see module doc).

    `extra_args` are appended to every skill invocation; `skill_args` maps a
    skill name to additional arguments for that skill only (e.g.
    {"reference-auditor": ["--input", "draft.md"]}).     `inputs` is the list of
    resolved input files declared via --inputs; they narrow the plan to the
    skills whose manifest input_types declare the files' types (unless
    `selected` names skills explicitly) and each file is forwarded as
    --input to the matching adapters (auto wiring runs first, so explicit
    --skill-arg flags win). `debug` (or the CHELATE_DEBUG environment
    variable) enables verbose stderr diagnostics for the router and every
    skill subprocess.
    """
    debug_on = debug_mod.flag(debug)
    root = os.path.abspath(root)
    os.makedirs(os.path.join(root, "process", "gates"), exist_ok=True)
    reg = load_default_registry()
    if debug_on:
        debug_mod.log(f"registry: {len(reg)} skills, "
                      f"errors={list(reg.errors)}")
        for rec in reg.all():
            debug_mod.log(f"registry: {rec.name} stage={rec.stage} "
                          f"inputs={getattr(rec, 'input_types', [])} "
                          f"outputs={getattr(rec, 'output_types', [])} "
                          f"deps={getattr(rec, 'dependencies', [])} "
                          f"sandbox={getattr(rec, 'sandbox_required', None)}")
    result = {
        "root": root,
        "mode": mode,
        "input_kind": input_kind,
        "inputs": [str(p) for p in (inputs or [])],
        "started": _iso_now(),
        "decisions": [],
        "terminated_by": None,
        "promoted": False,
        "blocked": None,
        "registry_errors": list(reg.errors),
    }
    plan = build_plan(reg, mode, input_kind, selected)
    # A name that does not exist would otherwise narrow the plan to nothing
    # and finish with exit 0 — a typo, or an agent naming a skill it invented,
    # would read as a successful run that did no work.
    known = set(reg.names())
    unknown_selected = [s for s in (selected or []) if s not in known]
    if unknown_selected:
        result["error"] = ("unknown skill(s) in --selected: "
                           + ", ".join(unknown_selected)
                           + "; known: " + ", ".join(sorted(known)))
        result["results_audit"] = audit_results(root)
        result["finished"] = _iso_now()
        return result
    file_tokens = _input_tokens_by_file(inputs) if inputs else []
    for path, token in file_tokens:
        if token is None:
            print(_color(
                f"[INPUT] no manifest input type is declared for "
                f"'{_ext_of(path)}' files ({path}); pass it via "
                f"--skill-arg if a skill consumes it", _YELLOW))
    if inputs and not selected:
        # declared inputs narrow the plan to the skills that can consume
        # them; an explicit --selected list always wins over this filter
        tokens = {t for _, t in file_tokens if t}
        plan = {
            stage: [r for r in recs
                    if tokens & {str(x).lower()
                                 for x in getattr(r, "input_types", [])}]
            for stage, recs in plan.items()
        }
        debug_mod.log(f"inputs: plan filtered to types {sorted(tokens)}")
    flat = [(stage, rec) for stage in STAGE_ORDER for rec in plan[stage]]
    if not flat:
        result["note"] = "no skills matched the requested pipeline"
        result["results_audit"] = audit_results(root)
        result["finished"] = _iso_now()
        return result

    # Freeze the declared inputs before anything reads them. From here on the
    # skills are handed snapshot paths, so a file edited while the run is in
    # flight cannot change what a skill opened — the check and the use are the
    # same bytes. Large inputs are dispatched from their original path and
    # reported as such.
    dispatch_inputs = list(inputs or [])
    # `--skill-arg "x:--input f"` is the documented way to wire a file the
    # manifest types do not cover; those files must be frozen too, or the
    # snapshot protection has an obvious hole beside it.
    extra_inputs = _skill_arg_inputs(skill_args, root)
    freeze = list(dispatch_inputs) + extra_inputs
    if freeze:
        try:
            frozen = snapshot.materialise(root, freeze)
        except OSError as exc:
            frozen = {"id": "", "files": {}, "skipped": [], "error": str(exc)}
        if frozen.get("id"):
            skill_args = _rewrite_skill_args(skill_args, frozen["files"])
            dispatch_inputs = [frozen["files"].get(os.path.abspath(str(p)),
                                                   str(p))
                               for p in dispatch_inputs]
            result["snapshot"] = {
                "id": frozen["id"],
                "dir": frozen["dir"],
                "manifest": frozen["manifest"],
                "files": {os.path.relpath(src, root).replace(os.sep, "/"):
                          os.path.relpath(dst, root).replace(os.sep, "/")
                          for src, dst in frozen["files"].items()},
                "direct": [os.path.relpath(p, root).replace(os.sep, "/")
                           for p in frozen.get("skipped", [])],
            }
            debug_mod.log(f"snapshot: id={frozen['id']} "
                          f"files={len(frozen['files'])} "
                          f"direct={len(frozen.get('skipped', []))}")
        if frozen.get("skipped"):
            print(_color(
                "[INPUT] too large to snapshot, dispatched from the original "
                "path (no TOCTOU protection): "
                + ", ".join(os.path.basename(p)
                            for p in frozen.get("skipped", [])), _YELLOW))

    auto_args, input_warnings = _auto_input_args(flat, dispatch_inputs)
    if auto_args:
        result["auto_inputs"] = {name: args[1]
                                 for name, args in auto_args.items()}
    for warning in input_warnings:
        print(_color(f"[INPUT] {warning}", _YELLOW))

    if dry_run:
        print(_color("DRY RUN — planned execution order:", _BOLD))
        for stage, rec in flat:
            wired = auto_args.get(rec.name)
            suffix = f"  + --input {wired[1]}" if wired else ""
            print(f"  {stage:<10} -> {rec.name}  (entrypoint "
                  f"{rec.entrypoint}){suffix}")
        result["planned"] = [
            {"stage": s, "skill": r.name,
             **({"input": auto_args[r.name][1]} if r.name in auto_args else {})}
            for s, r in flat]
        result["finished"] = _iso_now()
        return result

    # v1.3.0 (#132): pre-dispatch injection scan of text inputs. A poisoned
    # input hard-blocks the pipeline with a FAIL gate (mirroring
    # security-guard) so it cannot steer the downstream skills.
    scan_hit = _scan_inputs_for_injection(inputs, root)
    if scan_hit:
        result["decisions"].append(scan_hit)
        result["terminated_by"] = "injection-scan"
        result["finished"] = _iso_now()
        paths = write_reports(root, result)
        result["report"] = paths["report"]
        result["broadcast"] = paths["broadcast"]
        print(_color(
            f"PIPELINE TERMINATED at gate injection-scan — "
            f"prompt-injection markers detected in input", _RED),
            file=sys.stderr)
        return result

    terminated = False
    for stage, rec in flat:
        action = STAGE_ACTION[stage]
        # auto-wired inputs first, explicit flags last (argparse last-wins)
        call_args = list(auto_args.get(rec.name, []))
        call_args += list(extra_args or [])
        call_args += list((skill_args or {}).get(rec.name, []))
        record = run_skill(rec, root, action, call_args, timeout=timeout,
                           debug=debug_on)
        result["decisions"].append(record)
        _print_decision(record)
        if record.get("status") == "FAIL":
            result["terminated_by"] = rec.name
            terminated = True
            break

    failed = failed_gates(root)
    if not terminated and failed:
        names = ", ".join(sorted({f["skill"] for f in failed}))
        result["blocked"] = "gate"
        result["reason"] = (
            "promotion withheld: " + names + " failed in this workspace and "
            "has not been re-run since; fix the input and run that skill again")
        print(_color(f"PROMOTION WITHHELD — {result['reason']}", _RED),
              file=sys.stderr)
        terminated = True

    if not terminated and publish:
        stamp = _ts()
        # Promotion is the pipeline's one irreversible write: intermediate
        # products become deliverables and later stages stop seeing them as
        # provisional. It needs a token a human issued for this exact plan.
        params = approval.pipeline_params(mode, input_kind, inputs, selected,
                                          allow_unverified=allow_unverified)
        if require_approval:
            try:
                token = approval.consume(root, "promote", params)
            except (approval.ApprovalRequired,
                    approval.ApprovalInvalid) as exc:
                result["blocked"] = "approval"
                result["reason"] = f"promotion withheld: {exc}"
                print(_color(f"PROMOTION WITHHELD — {exc}", _RED),
                      file=sys.stderr)
            else:
                try:
                    promoted = promote(root, stamp, {
                        "source": "token",
                        "nonce": token.get("nonce"),
                    }, allow_unverified=allow_unverified)
                except PromotionLocked as exc:
                    result["blocked"] = "gate"
                    result["reason"] = f"promotion withheld: {exc}"
                    promoted = None
                result["promoted"] = promoted is not None
                result["promoted_to"] = promoted
        else:
            # `--no-approval` is not a synonym for "no human".  It only means
            # the human is supervising a script instead of signing a token,
            # so the same human channel is still required.
            try:
                approval.require_human("skipping the approval for promotion",
                                       "promote")
            except approval.HumanRequired as exc:
                result["blocked"] = "approval"
                result["reason"] = f"promotion withheld: {exc}"
                print(_color(f"PROMOTION WITHHELD — {exc}", _RED),
                      file=sys.stderr)
            else:
                try:
                    promoted = promote(root, stamp, {
                        "source": "scripted-run",
                        "unsafe_auto": True,
                    }, allow_unverified=allow_unverified)
                except PromotionLocked as exc:
                    result["blocked"] = "gate"
                    result["reason"] = f"promotion withheld: {exc}"
                    promoted = None
                result["promoted"] = promoted is not None
                result["promoted_to"] = promoted
    elif not terminated:
        # `publish=False` is a recipe step, not a pipeline: it produces into
        # process/ and stops there. Publishing is a separate, approved act —
        # `Runtime.submit` once the broker exists, `cli.py pipeline` today.
        result["promoted"] = False
        result["promotion"] = "skipped"
    # results/ itself, so every run reports what is there without a
    # promotion behind it. `cli.py audit` runs the same check on demand.
    # Snapshots hold copies of the user's data. Keep the newest ones and any
    # still referenced by a gate; delete the rest, so a long-lived workspace
    # does not accumulate a shadow archive of everything it ever read.
    result["snapshots_pruned"] = snapshot.prune(
        root, keep=20, protect=snapshot.referenced(root))
    result["results_audit"] = audit_results(root)
    # What the promotion (or refusal) rested on: how many of the newest PASS
    # gates carry bound digests, how many predate 1.3.6 and verify nothing,
    # and which ones expired between the check and now.
    result["gate_freshness"] = gate_freshness(root)
    result["finished"] = _iso_now()
    paths = write_reports(root, result)
    result["report"] = paths["report"]
    result["broadcast"] = paths["broadcast"]

    if terminated:
        print(_color(
            f"PIPELINE TERMINATED at gate {result['terminated_by']!r} — "
            f"intermediate products remain locked in {os.path.join(root, 'process')}",
            _RED), file=sys.stderr)
    else:
        print(_color(
            f"PIPELINE COMPLETE — {len(result['decisions'])} skills, "
            f"promoted={result['promoted']}", _GREEN))
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="router.py",
                                description="Chelate Shell microkernel router")
    p.add_argument("--root", default=".", help="workspace root")
    p.add_argument("--mode", choices=["a", "b", "c"], default="a")
    p.add_argument("--input-kind", default="")
    p.add_argument("--inputs", nargs="+", default=[], metavar="FILE",
                   help="input files (workspace-relative or absolute); each "
                        "is wired to the plan skills that declare its type")
    p.add_argument("--selected", default="",
                   help="comma-separated skill names (mode c)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--debug", action="store_true",
                   help="verbose stderr diagnostics (same as CHELATE_DEBUG=1)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    selected = [s.strip() for s in args.selected.split(",") if s.strip()] if args.selected else None
    resolved, missing = paths.resolve_inputs(args.root, args.inputs)
    for item in missing:
        print(f"[INPUT] not found (resolved against --root {args.root}): "
              f"{item}", file=sys.stderr)
    result = run(root=args.root, mode=args.mode, input_kind=args.input_kind,
                 inputs=resolved, selected=selected, dry_run=args.dry_run,
                 timeout=args.timeout, debug=args.debug)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # A withheld promotion is a refusal, not a success: a caller that
    # only reads the exit status must not see the run as complete.
    withheld = bool(result.get("blocked"))
    return 1 if (result.get("terminated_by") or result.get("error")
                  or withheld) else 0


if __name__ == "__main__":
    sys.exit(main())
