"""verify.py -- mandatory before/after verification.

This module is the gatekeeper of the *forced verification* protocol. After
``organize`` has moved files and ``snapshot`` has captured the after-state,
``verify`` diffs the two snapshots and enforces **eight** checks:

========================================================  ============
Check                                                     Severity
========================================================  ============
C1 File count conservation                                  error
C2 Content integrity (every unmoved file's SHA-256 stable) error
C3 Move traceability (every moved file has a log record)    error
C4 No unauthorized deletion (no before-file vanished)       error
C5 No unauthorized modification (no content was altered)    error
C6 No unauthorized addition (only index/log/snapshot)       warning
C7 Directory structure compliance (three-tier present)      error
C8 Self-check: deliverable stranded outside the structure   warning
========================================================  ============

Any *error*-severity failure -> ``VerifyResult.passed`` is ``False`` and the
pipeline MUST trigger ``rollback``.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from scripts import snapshot, utils

# Severity levels
ERROR = "error"
WARNING = "warning"
OK = "ok"


@dataclass
class Check:
    """One verification check result."""

    code: str # e.g. "C1"
    name: str # human-readable name
    severity: str # "error" | "warning"
    passed: bool
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "severity": self.severity,
            "passed": self.passed,
            "details": self.details,
        }


@dataclass
class VerifyResult:
    """Aggregated outcome of a verification run."""

    passed: bool
    checks: List[Check] = field(default_factory=list)
    report_path: Optional[Path] = None
    before: Optional[snapshot.Snapshot] = None
    after: Optional[snapshot.Snapshot] = None

    @property
    def error_count(self) -> int:
        return sum(
            1 for c in self.checks if not c.passed and c.severity == ERROR
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1 for c in self.checks if not c.passed and c.severity == WARNING
        )


def _snapshot_by_abs(snap: Optional[snapshot.Snapshot]) -> Dict[str, dict]:
    """Index a snapshot's files by absolute path for O(1) lookup."""
    out: Dict[str, dict] = {}
    if snap is None:
        return out
    for f in snap.files:
        out[f.abs_path] = f.to_dict()
    return out


def _moved_from_log(session: utils.OrganizeSession) -> Dict[str, str]:
    """Map source-abs -> target-abs for every 'moved' log record."""
    mapping: Dict[str, str] = {}
    for rec in session.move_records:
        if rec.status == "moved":
            mapping[rec.source] = rec.target
    return mapping


def _unmoved_files(
    before: Dict[str, dict],
    after: Dict[str, dict],
    moved_map: Dict[str, str],
) -> List[str]:
    """Return before-files whose abs path still exists in after unchanged."""
    unmoved: List[str] = []
    for abs_path, entry in before.items():
        if abs_path in moved_map:
            continue # this one moved; handled by C3
        if abs_path in after:
            unmoved.append(abs_path)
    return unmoved


def _run_c1(before: snapshot.Snapshot, after: snapshot.Snapshot) -> Check:
    """C1 file-count conservation (excluding auto-generated files)."""
    def _user_only(snap: snapshot.Snapshot) -> int:
        # Count only regular user files, not auto-generated index/log/snapshot.
        n = 0
        for f in snap.files:
            if utils.is_allowed_new_file(f.rel_path):
                continue
            n += 1
        return n

    b = _user_only(before)
    a = _user_only(after)
    passed = b == a
    details = [f"before user-files={b}, after user-files={a}"]
    if not passed:
        details.append(f"delta = {a - b} (should be 0)")
    return Check("C1", "File count conservation", ERROR, passed, details)


def _run_c2(
    before: Dict[str, dict],
    after: Dict[str, dict],
    unmoved: List[str],
) -> Check:
    """C2 content integrity of every unmoved file (SHA-256 stable)."""
    bad: List[str] = []
    for abs_path in unmoved:
        h_b = before.get(abs_path, {}).get("sha256", "")
        h_a = after.get(abs_path, {}).get("sha256", "")
        if h_b and h_a and h_b != h_a:
            bad.append(abs_path)
    passed = not bad
    details = [f"{len(unmoved)} unmoved files checked"]
    if bad:
        details.append(f"{len(bad)} files changed content:")
        details.extend(f" - {p}" for p in bad[:20])
    return Check("C2", "Content integrity (SHA-256 stable)", ERROR, passed, details)


def _run_c3(
    moved_map: Dict[str, str],
    session: utils.OrganizeSession,
) -> Check:
    """C3 move traceability: every moved file must have a log record.

    ``moved_map`` is *derived from the log itself*, so by construction every
    key has a record. The check instead validates the log's integrity: no
    'moved' record may point at a target that does not exist after the run.
    """
    missing: List[str] = []
    for src, tgt in moved_map.items():
        if not Path(tgt).exists():
            missing.append(f"{src} -> {tgt} (target missing)")
    passed = not missing
    details = [f"{len(moved_map)} move records traced"]
    details.extend(missing[:20])
    return Check("C3", "Move traceability", ERROR, passed, details)


def _run_c4(
    before: Dict[str, dict],
    after: Dict[str, dict],
    moved_map: Dict[str, str],
    session: utils.OrganizeSession,
) -> Check:
    """C4 no unauthorized deletion.

    A before-file is acceptable to disappear **only** if it was moved (has a
    log record) OR it is an auto-generated file we are allowed to drop during
    rollback. Any other disappearance is a fatal error.
    """
    vanished: List[str] = []
    for abs_path, entry in before.items():
        if abs_path in after:
            continue # still present
        if abs_path in moved_map:
            continue # legitimately moved
        # Auto-generated files that may legitimately be removed by rollback.
        if utils.is_allowed_new_file(entry.get("rel_path", abs_path)):
            continue
        vanished.append(abs_path)
    passed = not vanished
    details = [f"{len(vanished)} unexpected deletions"]
    details.extend(f" - {p}" for p in vanished[:20])
    return Check("C4", "No unauthorized deletion", ERROR, passed, details)


def _run_c5(
    before: Dict[str, dict],
    after: Dict[str, dict],
    unmoved: List[str],
) -> Check:
    """C5 no unauthorized modification (independent of C2 wording).

    C5 additionally checks *size* consistency for unmoved files so a
    same-hash-different-size anomaly (e.g. truncated re-write) is caught.
    """
    bad: List[str] = []
    for abs_path in unmoved:
        e_b = before.get(abs_path, {})
        e_a = after.get(abs_path, {})
        if e_b.get("size") != e_a.get("size"):
            bad.append(f"{abs_path} (size {e_b.get('size')} -> {e_a.get('size')})")
    passed = not bad
    details = [f"{len(unmoved)} unmoved files size-checked"]
    details.extend(bad[:20])
    return Check("C5", "No unauthorized modification (size stable)", ERROR, passed, details)


def _run_c6(
    after: snapshot.Snapshot,
    b_map: Dict[str, "snapshot.SnapshotFile"],
    moved_map: Dict[str, str],
) -> Check:
    """C6 no unauthorized additions.

    A file present in the after snapshot is acceptable if it is either:
    - in the auto-generated allow-list (index / log / snapshot / report), OR
    - an existing before file that was *moved* (now sits at a logged move
      target), OR
    - already present in the before snapshot at the same path.

    Anything else is a warning (not fatal).
    """
    before_abs = set(b_map.keys())
    moved_targets = set(moved_map.values())
    flagged: List[str] = []
    for f in after.files:
        if utils.is_allowed_new_file(f.rel_path):
            continue
        abs_path = str(f.abs_path)
        if abs_path in moved_targets or abs_path in before_abs:
            continue
        flagged.append(f.rel_path)
    passed = not flagged
    details = [f"{len(flagged)} non-whitelisted additions flagged"]
    details.extend(f" - {p}" for p in flagged[:20])
    return Check("C6", "No unauthorized addition (only index/log/snapshot)", WARNING, passed, details)


def _run_c7(root: Path, before: snapshot.Snapshot) -> Check:
    """C7 directory structure compliance (three-tier present)."""
    complete = utils.structure_complete(root)
    details = [
        f"material/initial: {_dir(root / utils.TIER_ORGANIZE / utils.SUB_INIT)}",
        f"material/downloaded: {_dir(root / utils.TIER_ORGANIZE / utils.SUB_DOWNLOAD)}",
        f"process: {_dir(root / utils.TIER_PROCESS)}",
        f"results: {_dir(root / utils.TIER_RESULT)}",
    ]
    return Check("C7", "Directory structure compliance", ERROR, complete, details)


def _dir(p: Path) -> str:
    return "present" if p.is_dir() else "MISSING"


def _run_c8(root: Path, before: snapshot.Snapshot) -> Check:
    """C8 self-check: deliverable stranded outside the structure.

    Catches the *missed-init* failure mode: the agent produced a
    deliverable (or loose material) but never ran ``init``, so the
    three-tier structure is missing and files sit at the folder root.
    This is a **warning, never an error** - it does not block the run or
    trigger rollback; it only reminds the agent to run ``init`` so the
    folder gets the standard layout.
    """
    complete = utils.structure_complete(root)
    if complete:
        return Check(
            "C8", "Self-check (structure vs. loose files)", WARNING, True, []
        )
    # Structure is incomplete - find how many deliverable/material files are
    # stranded at the root (not yet inside any tier).
    stranded: List[str] = []
    if root.is_dir():
        for p in sorted(root.iterdir()):
            if not p.is_file():
                continue
            # Skip tool-owned files that legitimately live at the root.
            if p.name.startswith(".") or p.name in utils.ROOT_OWNED_FILES:
                continue
            stranded.append(p.name)
    detail = (
        "standard structure incomplete - run `init` first "
        f"({len(stranded)} loose file(s) at root: {', '.join(stranded[:8])})"
        if stranded
        else "standard structure incomplete - run `init` to build it"
    )
    return Check(
        "C8",
        "Self-check (structure vs. loose files)",
        WARNING,
        False,
        [detail],
    )


def verify(
    root: Path,
    session: Optional[utils.OrganizeSession] = None,
    before: Optional[snapshot.Snapshot] = None,
    after: Optional[snapshot.Snapshot] = None,
    write_report: bool = True,
) -> VerifyResult:
    """Run all eight checks and produce a :class:`VerifyResult`.

    Parameters
    ----------
    root:
        Task root.
    session:
        The organize session (for move-log traceability). May be None if
        verifying an external/previous run.
    before / after:
        Explicit snapshots. When omitted, the latest snapshot of each phase
        is loaded from ``process/``.
    write_report:
        When True (default), write ``verification_report.md`` under
        ``process/``.

    Returns
    -------
    VerifyResult:
        ``passed`` is False if **any** error-severity check failed.
    """
    root = Path(root).resolve()
    session = session or utils.OrganizeSession(root=root)

    # Load snapshots (accept explicit, else find latest on disk).
    if before is None:
        before = snapshot.find_latest_snapshot(root, "before")
    if after is None:
        after = snapshot.find_latest_snapshot(root, "after")

    if before is None or after is None:
        result = VerifyResult(
            passed=False,
            checks=[
                Check(
                    "C0",
                    "snapshot missing",
                    ERROR,
                    False,
                    [
                        "before snapshot missing" if before is None else "",
                        "after snapshot missing" if after is None else "",
                    ],
                )
            ],
            before=before,
            after=after,
        )
        if write_report:
            _write_report(root, result)
        return result

    b_map = _snapshot_by_abs(before)
    a_map = _snapshot_by_abs(after)
    moved_map = _moved_from_log(session)
    unmoved = _unmoved_files(b_map, a_map, moved_map)

    checks: List[Check] = [
        _run_c1(before, after),
        _run_c2(b_map, a_map, unmoved),
        _run_c3(moved_map, session),
        _run_c4(b_map, a_map, moved_map, session),
        _run_c5(b_map, a_map, unmoved),
        _run_c6(after, b_map, moved_map),
        _run_c7(root, before),
        _run_c8(root, before),
    ]

    passed = all(c.passed or c.severity != ERROR for c in checks)
    result = VerifyResult(
        passed=passed,
        checks=checks,
        before=before,
        after=after,
    )
    if write_report:
        result.report_path = _write_report(root, result)
    return result


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _write_report(root: Path, result: VerifyResult) -> Path:
    """Render ``verification_report.md`` under process/ and return its path."""
    report = Path(root / utils.TIER_PROCESS / utils.VERIFY_REPORT_NAME)
    report.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now().isoformat()
    lines: List[str] = []
    lines.append("# Verification Report")
    lines.append("")
    lines.append(f"- Generated at: {ts}")
    lines.append(f"- Root: `{root}`")
    lines.append(
        f"- Verdict: **{'[PASS]' if result.passed else '[FAIL] (rollback needed)'}**"
    )
    lines.append("")
    lines.append("## checks")
    lines.append("")
    lines.append("| Code | checks | severity | result | detail |")
    lines.append("|------|--------|----------|------|----------|")
    for c in result.checks:
        mark = "[PASS]" if c.passed else "[FAIL]"
        detail = (c.details[0] if c.details else "").replace("|", "/")
        lines.append(
            f"| {c.code} | {c.name} | {c.severity} | {mark} | {detail} |"
        )
    lines.append("")
    lines.append("## Details")
    lines.append("")
    for c in result.checks:
        lines.append(f"### {c.code} {c.name} -- {'passed' if c.passed else 'failed'}")
        for d in c.details:
            lines.append(f"- {d}" if d else "- (none)")
        lines.append("")

    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def load_report(root: Path) -> Optional[str]:
    """Return the raw text of the latest report, or None if absent."""
    p = Path(root) / utils.TIER_PROCESS / utils.VERIFY_REPORT_NAME
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")
