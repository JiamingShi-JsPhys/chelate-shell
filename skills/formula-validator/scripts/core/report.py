"""Render a verification result as a Markdown report with the errors up front.

The report is written to disk as UTF-8 and is meant for a human. The agent
normally reads only the compact JSON summary; the full report is opened when
the summary says something failed. That split is what keeps the verification
out of the context window.
"""

from __future__ import annotations

from datetime import datetime

__all__ = ["render"]

_BADGE = {
    "pass": "PASS",
    "fail": "FAIL",
    "conflict": "CONFLICT",
    "unknown": "UNKNOWN",
}
# Every status a stage can report must have an entry here. The fallback in the
# callers is the raw status word, which renders "skipped skipped" in the table.
_MARK = {"pass": "[ok]", "fail": "[XX]", "conflict": "[!!]", "unknown": "[??]",
         "warning": "[! ]", "inconclusive": "[??]", "inconsistent": "[XX]",
         "skipped": "[--]", "proven": "[ok]", "disproven": "[XX]",
         "unresolved": "[??]", "consistent": "[ok]"}
_CHECK_LABEL = {
    "parse": "D1 Parse",
    "dimension": "D2 Dimension",
    "limit": "D3 Limit",
    "numeric": "D4 Numeric",
    "symbolic": "D5 Symbolic",
}


def _fmt_point(point) -> str:
    if not point:
        return "-"
    return ", ".join(f"`{k}` = {v}" for k, v in point.items())


def _header(result: dict) -> list[str]:
    verdict = result.get("verdict", "unknown")
    lines = [
        "# Formula verification report",
        "",
        f"**Verdict: {_BADGE.get(verdict, verdict.upper())}**",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Mode: `{result.get('mode')}`",
    ]
    inp = result.get("input", {})
    if inp.get("text"):
        lines.append(f"- Input: `{inp['text']}`")
    if inp.get("declared_units"):
        units = ", ".join(f"`{k}`: {v}" for k, v in inp["declared_units"].items())
        lines.append(f"- Declared units: {units}")
    lines.append("")
    return lines


def _check_table(result: dict) -> list[str]:
    checks = result.get("checks", {})
    lines = ["## Checks", "", "| Check | Status | Note |", "|---|---|---|"]
    for key in ("parse", "dimension", "limit", "numeric", "symbolic"):
        if key not in checks:
            continue
        c = checks[key]
        status = c.get("status", "unknown")
        note = ""
        if key == "parse":
            note = f"strategy `{c.get('strategy')}`"
        elif key == "dimension":
            note = f"lhs `{c.get('lhs_text')}` / rhs `{c.get('rhs_text')}`"
        elif key == "limit":
            note = f"{c.get('n_checks', 0)} cases, {c.get('n_errors', 0)} errors"
        elif key == "numeric":
            note = (f"{c.get('n_compared', 0)} of {c.get('n_samples', 0)} samples, "
                    f"max rel err {c.get('max_rel_error')}")
        elif key == "symbolic":
            note = (c.get("tactic") or c.get("note") or "")
        lines.append(f"| {_CHECK_LABEL[key]} | {_MARK.get(status, status)} "
                     f"{status} | {note} |")
    lines.append("")
    return lines


def _errors(result: dict) -> list[str]:
    errs = result.get("errors", [])
    if not errs:
        return ["## Highlighted problems", "",
                "None. Every check that ran agreed.", ""]
    lines = ["## Highlighted problems", ""]
    for i, e in enumerate(errs, 1):
        lines.append(f"### {i}. {_CHECK_LABEL.get(e['check'], e['check'])} — "
                     f"{e.get('message', '')}")
        lines.append("")
        ev = e.get("evidence") or {}
        if e["check"] == "dimension":
            if ev.get("expression"):
                lines.append(f"- Offending sub-expression: `{ev['expression']}`")
            if ev.get("term_dimensions"):
                terms = "`, `".join(str(t) for t in ev["term_dimensions"])
                lines.append(f"- Dimensions involved: `{terms}`")
        elif e["check"] == "numeric":
            lines.append(f"- Worst point: {_fmt_point(ev.get('worst_point'))}")
            lines.append(f"- lhs value: `{ev.get('lhs_value')}`")
            lines.append(f"- rhs value: `{ev.get('rhs_value')}`")
            ratio = ev.get("ratio") or {}
            if ratio.get("looks_like_constant_factor"):
                lines.append(f"- **Diagnosis:** the ratio between the two sides "
                             f"is nearly constant at about `{ratio.get('mean')}` "
                             f"across every sample — this looks like a missing "
                             f"constant factor, not a wrong functional form.")
            elif ratio.get("spread") is not None:
                lines.append(f"- Ratio spread `{ratio.get('spread')}`: the "
                             f"mismatch varies with the parameters, so the "
                             f"functional form differs.")
        elif e["check"] == "limit":
            lines.append(f"- Variable `{ev.get('symbol')}` at "
                         f"`{ev.get('point')}`")
        elif e["check"] == "symbolic":
            if ev.get("difference"):
                lines.append(f"- lhs - rhs simplifies to: `{ev['difference']}`")
        lines.append("")
    return lines


def _limit_section(result: dict) -> list[str]:
    lim = result.get("checks", {}).get("limit")
    if not lim or not lim.get("checks"):
        return []
    rows = [c for c in lim["checks"] if c.get("severity") != "info"]
    if not rows:
        return ["## Limit cases", "",
                f"All {lim.get('n_checks', 0)} enumerated limit cases behaved "
                "consistently on both sides.", ""]
    lines = ["## Limit cases", "",
             "| Variable | Point | lhs | rhs | Verdict |", "|---|---|---|---|---|"]
    for c in rows:
        ll = c.get("lhs_limit") or {}
        lr = c.get("rhs_limit") or {}
        lines.append(
            f"| `{c.get('symbol')}` | `{c.get('point')}` | "
            f"{ll.get('kind')} | {lr.get('kind')} | "
            f"{_MARK.get(c.get('verdict'), '')} {c.get('verdict')} |")
        if c.get("message"):
            lines.append(f"| | | | | {c['message']} |")
    lines.append("")
    return lines


def _caveats(result: dict) -> list[str]:
    cvs = result.get("caveats", [])
    if not cvs:
        return []
    lines = ["## Caveats", ""]
    lines += [f"- {c}" for c in cvs]
    lines.append("")
    return lines


def _breakpoint(result: dict) -> list[str]:
    bp = result.get("breakpoint")
    if not bp:
        return []
    lines = ["## Derivation chain", "",
             f"- Steps: {bp.get('n_steps')}",
             f"- Chain verified up to step index: {bp.get('verified_up_to')}",
             f"- Breaking steps: {bp.get('n_breaks')}", ""]
    lines.append("| Step | Status | Max rel err | Dimension |", "|---|---|---|---|")
    for s in bp.get("steps", []):
        lines.append(f"| {s['step']} ({s['from_index']}→{s['to_index']}) | "
                     f"{_MARK.get(s['status'], s['status'])} {s['status']} | "
                     f"{s.get('max_rel_error')} | `{s.get('dimension')}` |")
    lines.append("")
    fb = bp.get("first_break")
    if fb:
        d = fb.get("diagnosis") or {}
        lines += ["### First break", "",
                  f"- **Step {fb['step']}** (index {fb['from_index']} → "
                  f"{fb['to_index']})",
                  f"- Diagnosis: `{d.get('diagnosis')}`",
                  f"- {d.get('summary')}",
                  f"- Fix hint: {d.get('fix_hint')}",
                  f"- Worst point: {_fmt_point(fb.get('worst_point'))}",
                  f"- lhs = `{fb.get('lhs_at_worst')}`, "
                  f"rhs = `{fb.get('rhs_at_worst')}`"]
        if fb.get("difference"):
            lines.append(f"- Difference introduced: `{fb['difference']}`")
        lines.append("")
    gc = bp.get("global_check") or {}
    if gc:
        lines += [f"Global check (step 0 vs last): {_MARK.get(gc.get('status'), '')} "
                  f"{gc.get('status')}, max rel err {gc.get('max_rel_error')}", ""]
    return lines


def _matrix(result: dict) -> list[str]:
    m = result.get("matrix")
    if not m:
        return []
    lines = ["## Matrix properties", "",
             f"- Shape: {m.get('shape')}", "",
             "| Property | Symbolic | Numeric | Residual |", "|---|---|---|---|"]
    for name, r in (m.get("properties") or {}).items():
        lines.append(f"| {name} | {_MARK.get(r['status'], r['status'])} "
                     f"{r['status']} | {r.get('numeric')} | "
                     f"`{(r.get('residual') or '')[:80]}` |")
    lines.append("")
    return lines


def _timing(result: dict) -> list[str]:
    t = result.get("timing_ms")
    if not t:
        return []
    total = t.get("total") or sum(v for k, v in t.items() if k != "total")
    lines = ["## Timing", "",
             "| Stage | ms |", "|---|---|"]
    for k, v in t.items():
        if k != "total":
            lines.append(f"| {_CHECK_LABEL.get(k, k)} | {v} |")
    lines += [f"| **total** | **{round(total, 2)}** |", ""]
    return lines


def render(result: dict) -> str:
    parts: list[str] = [_header(result)[0]]
    parts += _header(result)[1:]
    parts += _errors(result)
    parts += _check_table(result)
    parts += _breakpoint(result)
    parts += _matrix(result)
    parts += _limit_section(result)
    parts += _caveats(result)
    parts += _timing(result)
    parts += ["---", "",
              "_Every numeric result above comes from SymPy/NumPy. The language "
              "model extracts the formula and reads this report; it does not "
              "perform any of the algebra._", ""]
    return "\n".join(parts)
