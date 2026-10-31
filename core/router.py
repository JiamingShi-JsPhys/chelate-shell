"""Chelate Shell router — microkernel dispatcher (manifest-driven pipeline).

Caller: cli.py (cmd_pipeline), tests/core/test_router.py.
No existing file in chelate-shell-v1.1.0/ serves this purpose.
Data schemas:
    Reads:  skills/<skill>/manifest.json via core.registry (routing table);
            each skill's GateResult JSON from process/gates/<skill>_<ts>.json
            (written by the skill's root-level run.py adapter).
    Writes: results/pipeline_report_<ts>.json, _broadcast/pipeline_index_<ts>.json,
            and — only when every gate passes — a promoted copy of process/
            under results/promoted_<ts>/.
User instruction: v1.1.0 blueprint section 3:
    1. scan the 14 manifests into an in-memory routing table;
    2. dispatch stage="ingest" skills matched by input type (e.g. PDF ->
       fulltext-extractor), then serially dispatch stage="gates" skills
       (formula-validator, reference-auditor, ...);
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
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.registry import Registry, load_default_registry  # noqa: E402
from core.sandbox import resolve_environment  # noqa: E402
from lib.chelate_core import debug as debug_mod  # noqa: E402
from lib.chelate_core import paths  # noqa: E402

STAGE_ORDER = ("workspace", "ingest", "gates", "processors")
STAGE_ACTION = {"workspace": "workspace", "ingest": "ingest",
                "gates": "gate", "processors": "process"}

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
        outcome = run_skill_sandboxed(rec, _REPO_ROOT, action, extra_args,
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


def promote(root: str, stamp: str) -> Optional[str]:
    """Copy process/ into results/promoted_<stamp>/ (full-pass promotion)."""
    src = os.path.join(root, "process")
    if not os.path.isdir(src):
        return None
    dst = os.path.join(root, "results", f"promoted_{stamp}")
    os.makedirs(os.path.join(root, "results"), exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
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


def run(root: str, mode: str = "a", input_kind: str = "",
        inputs: Optional[List[str]] = None,
        selected: Optional[List[str]] = None, dry_run: bool = False,
        extra_args: Optional[List[str]] = None,
        skill_args: Optional[Dict[str, List[str]]] = None,
        timeout: int = 600, debug: bool = False) -> dict:
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
        "registry_errors": list(reg.errors),
    }
    plan = build_plan(reg, mode, input_kind, selected)
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
        result["finished"] = _iso_now()
        return result

    auto_args, input_warnings = _auto_input_args(flat, inputs)
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

    if not terminated:
        stamp = _ts()
        promoted = promote(root, stamp)
        result["promoted"] = promoted is not None
        result["promoted_to"] = promoted

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
    p = argparse.ArgumentParser(pro="router.py",
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
    return 1 if result.get("terminated_by") else 0


if __name__ == "__main__":
    sys.exit(main())
