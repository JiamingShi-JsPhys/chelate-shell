"""reference-auditor — gates-stage DOI verification against Crossref (thin).

The audit policy (extract -> verify -> verdict) lives in
lib/chelate_core/doi_audit.py; this file only parses CLI arguments and maps
the verdict onto the gate contract:

    python run.py --root <workspace> --action audit --input draft.md
    python run.py --root <workspace> --action audit --text "... 10.1234/fake ..."

Verdicts: PASS = every DOI resolves (EXACT); FAIL = a DOI returns 404
(pipeline terminates); UNVERIFIED = network failure or no DOIs found.
Outputs: process/gates/reference-auditor_<ts>.json + per-DOI details in
process/reference_audit_<ts>.json. See SKILL.md / README.md for the full
contract.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from lib.chelate_core import adapter, doi_audit, paths  # noqa: E402

SKILL = "reference-auditor"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ("requests",)


def _configure(ap) -> None:
    ap.add_argument("--input", default="",
                    help="path to the draft manuscript (markdown/text)")
    ap.add_argument("--text", default="",
                    help="inline draft text (alternative to --input)")
    ap.add_argument("--timeout", type=int, default=None,
                    help="per-DOI HTTP timeout in seconds (default: config)")


def _audit(args) -> dict:
    cfg = adapter.load_config(SKILL_ROOT)
    adapter.require_deps(DEPENDENCIES, "DOI verification")
    draft = str(paths.resolve_input(args.root, args.input)) if args.input \
        else ""
    try:
        text, source = doi_audit.read_draft(draft, args.text)
    except (FileNotFoundError, ValueError) as exc:
        raise adapter.Failed(str(exc))
    if not doi_audit.extract_dois(text):
        raise adapter.Degraded(f"no DOIs found in {source}; nothing to audit")

    timeout = args.timeout or int(cfg.get("timeout_seconds", 20))
    verdict = doi_audit.audit(text, source, timeout=timeout,
                              details_dir=str(Path(args.root) / "process"))
    artifacts = [verdict["details_path"]] if verdict["details_path"] else []
    if verdict["status"] == "FAIL":
        raise adapter.Failed(verdict["reason"], verdict["evidence_level"],
                             artifacts)
    if verdict["status"] == "UNVERIFIED":
        raise adapter.Degraded(verdict["reason"], artifacts=artifacts)
    return {"status": "PASS",
            "evidence_level": verdict["evidence_level"],
            "reason": verdict["reason"], "artifacts": artifacts,
            "data": {"total": len(verdict["records"]),
                     "valid": sum(1 for r in verdict["records"]
                                  if r["status"] == "valid")}}


HANDLERS = {"audit": _audit}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS,
        description="Verify every DOI in a draft against the Crossref API."))
