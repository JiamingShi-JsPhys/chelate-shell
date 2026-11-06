#!/usr/bin/env python
"""Command line entry point.

Output contract:
  * a compact JSON summary goes to stdout - this is what an agent reads;
  * the full Markdown report is written to ``_reports/`` (the path is in the
    summary), so large detail never has to enter the context window.

Exit codes:
  0 = pass    1 = fail / conflict    2 = unknown (abstained)
  3 = parse error                    4 = usage or internal error
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import traceback
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = SKILL_ROOT / "_reports"

if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts import __version__                                  # noqa: E402
from scripts.core import breakpoint as bp_mod                    # noqa: E402
from scripts.core import pipeline                                # noqa: E402
from scripts.core.errors import FVError, ParseError              # noqa: E402
from scripts.core.matrixprops import PROPERTIES, check_matrix, parse_matrix  # noqa: E402
from scripts.core.parsing import parse_expr                      # noqa: E402
from scripts.core.report import render                           # noqa: E402


def _fix_console() -> None:
    """Windows consoles default to cp936; symbols in a report would raise."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                stream._WRAPPER = io.TextIOWrapper(
                    stream.buffer, encoding="utf-8", errors="replace")
            except Exception:
                pass


def _csv(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _pairs(values: list[str] | None) -> dict:
    out: dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise SystemExit(f"expected name=value, got: {item!r}")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _report_slug(result: dict) -> str:
    """A short, stable prefix for a report file name.

    Batch validation used to overwrite a single ``latest.md`` on every run,
    so only the last formula's detail survived. Report files are now named
    from the request content plus a timestamp, so each run keeps its own
    file and ``latest.md`` stays only as a pointer to the most recent one.
    """
    mode = result.get("mode", "") or "run"
    inp = result.get("input", {})
    if mode == "matrix":
        text = inp.get("text", "")
    elif mode == "derivation":
        text = "\n".join(inp.get("steps", []))
    else:
        text = inp.get("text", "")
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{mode}-{digest}"


def _write_report(result: dict, explicit: str | None) -> str | None:
    if explicit == "-":
        return None
    try:
        markdown = render(result)
    except Exception as exc:
        markdown = f"# Report\n\nReport rendering failed: {exc}\n"
    if explicit:
        path = Path(explicit)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
    else:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        unique = REPORT_DIR / f"{_report_slug(result)}-{ts}.md"
        unique.write_text(markdown, encoding="utf-8")
        # keep a 'latest.md' pointer to the most recent report so scripts that
        # read a fixed path still work, without losing the per-run files
        (REPORT_DIR / "latest.md").write_text(markdown, encoding="utf-8")
        path = unique
    return str(path)


def _emit(payload: dict, exit_code: int, pretty: bool = False) -> int:
    print(json.dumps(payload, ensure_ascii=True, indent=2 if pretty else None))
    return exit_code


_EXIT = {"pass": 0, "fail": 1, "conflict": 1, "unknown": 2}


def cmd_validate(args) -> int:
    try:
        units = _pairs(args.units)
        positive = (set(p.strip() for p in args.positive.split(","))
                    if args.positive else None)
        result = pipeline.validate_equation(
            text=args.expr, units=units, n=args.samples, tol=args.tol,
            seed=args.seed, critical=args.critical, auto_infer=args.infer,
            positive=positive, ranges=None,
            run_symbolic=not args.no_symbolic, max_ops=args.max_ops,
            symbol_names=_csv(args.symbols))
    except ParseError as exc:
        return _emit({"verdict": "parse_error", "message": exc.message,
                      "detail": exc.detail}, 3)
    except FVError as exc:
        return _emit({"verdict": "error", **exc.as_dict()}, exc.exit_code)

    path = _write_report(result, args.report)
    if args.stdout_report:
        print(render(result))
        return _EXIT[result["verdict"]]
    return _emit(pipeline.summarize(result, path), _EXIT[result["verdict"]],
                 pretty=args.json_pretty)


def cmd_check(args) -> int:
    try:
        result = pipeline.inspect_expression(
            args.expr, _pairs(args.units), args.infer,
            set(p.strip() for p in args.positive.split(",")) if args.positive else None,
            symbol_names=_csv(args.symbols), expect_zero=args.expect_zero)
    except ParseError as exc:
        return _emit({"verdict": "parse_error", "message": exc.message,
                      "detail": exc.detail}, 3)
    path = _write_report(result, args.report)
    if args.stdout_report:
        print(render(result))
        return _EXIT[result["verdict"]]
    return _emit(pipeline.summarize(result, path), _EXIT[result["verdict"]],
                 pretty=args.json_pretty)


def cmd_derive(args) -> int:
    lines: list[str] = []
    if args.steps_file:
        lines += [l.strip() for l in
                  Path(args.steps_file).read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.strip().startswith("#")]
    lines += [s for s in (args.steps or []) if s.strip()]
    if len(lines) < 2:
        return _emit({"verdict": "error",
                      "message": "at least two derivation steps are required"}, 4)

    parsed: list = []
    for i, line in enumerate(lines):
        # A pasted derivation usually keeps its left-hand side ("E**2 = ...").
        # Two consecutive steps can name different left-hand sides, so the
        # chain is compared on the right-hand sides.
        body = line
        if "=" in line:
            head, _, tail = line.partition("=")
            if head.strip() and tail.strip():
                body = tail.strip()
        try:
            expr, strategy = parse_expr(body, _csv(args.symbols))
            parsed.append(expr)
        except ParseError as exc:
            return _emit({"verdict": "parse_error", "step": i, "text": line,
                          "message": exc.message, "detail": exc.detail}, 3)

    try:
        positive = (set(p.strip() for p in args.positive.split(","))
                    if args.positive else None)
        bp = bp_mod.locate_breakpoint(
            parsed, declared_units=_pairs(args.units), n=args.samples,
            tol=args.tol, seed=args.seed, auto_infer=args.infer,
            positive=positive)
    except FVError as exc:
        return _emit({"verdict": "error", **exc.as_dict()}, exc.exit_code)

    result = {
        "mode": "derivation",
        "input": {"steps": lines},
        "verdict": {"pass": "pass", "fail": "fail"}.get(bp["status"], "unknown"),
        "checks": {},
        "errors": [],
        "caveats": [],
        "breakpoint": bp,
    }
    fb = bp.get("first_break")
    if fb:
        d = fb.get("diagnosis") or {}
        result["errors"].append({
            "check": "breakpoint", "severity": "error",
            "message": (f"the chain breaks at step {fb['step']} "
                        f"({d.get('summary') or 'sides disagree'})"),
            "evidence": {"worst_point": fb.get("worst_point")},
        })
    path = _write_report(result, args.report)
    if args.stdout_report:
        print(render(result))
        return _EXIT[result["verdict"]]
    return _emit(pipeline.summarize(result, path), _EXIT[result["verdict"]],
                 pretty=args.json_pretty)


def cmd_matrix(args) -> int:
    text = args.matrix
    if args.matrix_file:
        text = Path(args.matrix_file).read_text(encoding="utf-8").strip()
    if not text:
        return _emit({"verdict": "error",
                      "message": "no matrix supplied"}, 4)
    try:
        matrix = parse_matrix(text)
        props = [p.strip() for p in args.props.split(",") if p.strip()]
        mres = check_matrix(matrix, props or None, max_ops=args.max_ops)
    except ParseError as exc:
        return _emit({"verdict": "parse_error", "message": exc.message,
                      "detail": exc.detail}, 3)

    verdict = {"pass": "pass", "fail": "fail"}.get(mres["status"], "unknown")
    result = {"mode": "matrix", "input": {"text": text}, "verdict": verdict,
              "checks": {}, "errors": [], "caveats": [], "matrix": mres}
    for p in mres["failed"]:
        result["errors"].append({
            "check": "matrix", "severity": "error",
            "message": f"the matrix is not {p.replace('_', ' ')}",
            "evidence": mres["properties"][p]})
    path = _write_report(result, args.report)
    summary = {"verdict": verdict, "shape": mres["shape"],
               "failed": mres["failed"], "unresolved": mres["unresolved"]}
    if path:
        summary["report"] = path
    return _emit(summary, _EXIT[verdict], pretty=args.json_pretty)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="formula-validator",
        description="Deterministic verification of physics / math formulas.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp_):
        sp_.add_argument("--units", action="append", metavar="NAME=UNIT",
                         help="declare a unit, repeatable (e.g. --units m=kg)")
        sp_.add_argument("--infer", action="store_true",
                         help=("guess units for undeclared symbols from a physics "
                               "naming table (off by default: a wrong guess "
                               "produces a false dimensional error)"))
        sp_.add_argument("--symbols", metavar="A,B", default="",
                         help=("force these names to parse as plain symbols; needed for I if you mean current rather than the imaginary unit"))
        sp_.add_argument("--positive", metavar="A,B",
                         help="symbols to sample as strictly positive")
        sp_.add_argument("--samples", type=int, default=10000)
        sp_.add_argument("--tol", type=float, default=1e-9)
        sp_.add_argument("--seed", type=int, default=0)
        sp_.add_argument("--critical", action="append", metavar="VAR=VALUE",
                         help="extra limit point to test, e.g. --critical x=1")
        sp_.add_argument("--report", metavar="PATH",
                         help="where to write the Markdown report ('-' to skip)")
        sp_.add_argument("--stdout-report", action="store_true",
                         help="print the Markdown report instead of JSON")
        sp_.add_argument("--json-pretty", action="store_true",
                         help="print the JSON summary with indentation (easier to read "
                              "in a terminal; default is one compact line)")

    v = sub.add_parser("validate", help="verify an equation lhs = rhs")
    v.add_argument("--expr", required=True)
    v.add_argument("--no-symbolic", action="store_true",
                   help="skip the symbolic identity prover")
    v.add_argument("--max-ops", type=int, default=800)
    common(v)
    v.set_defaults(func=cmd_validate)

    c = sub.add_parser("check", help="inspect a single expression")
    c.add_argument("--expr", required=True)
    c.add_argument("--expect-zero", "--as-residual", action="store_true",
                   dest="expect_zero",
                   help="assert the expression is an identity equal to zero; "
                        "runs the symbolic zero test (e.g. check --expr "
                        "\"sin(x)**2+cos(x)**2-1\" --expect-zero)")
    common(c)
    c.set_defaults(func=cmd_check)

    d = sub.add_parser("derive", help="verify a chain of steps and localise the break")
    d.add_argument("--steps-file", help="file with one step per line")
    d.add_argument("--steps", action="append", default=[],
                   help="a derivation step, repeatable")
    common(d)
    d.set_defaults(func=cmd_derive)

    m = sub.add_parser("matrix", help="check matrix properties (Hermitian, unitary, ...)")
    m.add_argument("--matrix", help="Matrix([[...]]) or [[...]]")
    m.add_argument("--matrix-file", help="read the matrix from a file")
    m.add_argument("--props", default="hermitian,unitary",
                   help="comma-separated: " + ", ".join(PROPERTIES))
    m.add_argument("--max-ops", type=int, default=400)
    m.add_argument("--report", metavar="PATH")
    m.add_argument("--stdout-report", action="store_true")
    m.add_argument("--json-pretty", action="store_true",
                   help="print the JSON summary with indentation (easier to read "
                        "in a terminal; default is one compact line)")
    m.set_defaults(func=cmd_matrix)

    return p


def main(argv: list[str] | None = None) -> int:
    _fix_console()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        return _emit({"verdict": "error", "message": "interrupted"}, 4)
    except Exception as exc:  # never dump a traceback into the agent's context
        return _emit({"verdict": "error", "message": f"{type(exc).__name__}: {exc}",
                      "traceback": traceback.format_exc(limit=3).splitlines()[-3:]}, 4)


if __name__ == "__main__":
    sys.exit(main())
