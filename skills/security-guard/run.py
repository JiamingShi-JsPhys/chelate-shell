"""security-guard — v1.3.0 infrastructure gate (thin adapter).

Scanning lives in core/security_shield.py (stdlib only): anti-injection text
scan + AST static scan of Python source. This adapter wires the uniform
--root/--action contract onto it and writes the gate into the workspace.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = next((p for p in (_HERE, _HERE.parent, _HERE.parent.parent,
                          _HERE.parent.parent.parent)
             if (p / "core" / "security_shield.py").is_file()), _HERE.parents[1])
sys.path.insert(0, str(_REPO))

from core.security_shield import resolve_input, scan_text, shield_report  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="security-guard")
    ap.add_argument("--root", required=True, help="workspace root")
    ap.add_argument("--action", default="gate", help="gate | scan")
    ap.add_argument("--input", default=None, help="file path or inline text")
    ap.add_argument("--mode", choices=("text", "source", "auto"), default="auto")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args(argv)
    if args.action not in ("gate", "scan"):
        print(f"unknown action: {args.action}", file=sys.stderr)
        return 2

    payload, mode, error = resolve_input(args.root, args.input, args.mode)
    if error:
        print(f"security-guard: {error}", file=sys.stderr)
        return 2
    if payload is None:
        report = {"note": "no --input provided; scanner passed through"}
    elif mode == "source":
        report = {"source": shield_report(payload)}
    elif mode == "text":
        report = {"text": scan_text(payload)}
    else:
        report = {"text": scan_text(payload), "source": shield_report(payload)}
    blocked = bool(report.get("text", {}).get("blocked")) or \
        report.get("source", {}).get("violation_count", 0) > 0
    result = {"skill": "security-guard", "action": args.action, "blocked": blocked,
              "status": "FAIL" if blocked else "PASS", "report": report}

    # v1.1.1 convention: gates land inside the workspace, never beside the skill.
    gates = Path(args.root) / "process" / "gates"
    gates.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (gates / f"security-guard_{stamp}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False,
                     indent=2 if args.as_json else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
