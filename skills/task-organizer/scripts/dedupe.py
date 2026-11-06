"""dedupe.py -- exact + similarity duplicate detection.

Two complementary detectors:

1. **Exact duplicates** -- files whose content is byte-for-byte identical.
   Detected by SHA-256 over the full content (after a cheap pre-filter on
   ``(size, first-1KB-hash)`` so we only hash the candidates that could
   possibly match).

2. **Similar duplicates** -- files that are *not* exact but highly alike
   (e.g. slightly edited drafts, re-downloaded near-copies). Detected by a
   coarse pre-filter (same size, same first 1 KB) followed by a
   ``difflib.SequenceMatcher`` ratio on up to ``MAX_SIM_BYTES`` of content.

Outputs
-------
- A human-readable ``process/duplicate_report.md`` (always written) listing
  every exact group and every similar pair, with sizes and similarity ratios.
- When ``action == "move"`` the *exact* duplicates are moved (never deleted)
  into ``material/duplicates/`` using the same ``organize._move_file`` path
  that the main pipeline uses, so the moves are recorded into the
  :class:`OrganizeSession`, captured by the after-snapshot, and enforced by
  the forced 8-check verification (and rolled back automatically on
  failure). Similar files are **reported only** -- auto-moving near-copies is
  too risky, so the user decides.

Design constraints
------------------
- Standard library only.
- Default mode is ``report``: fully non-destructive.
- Never raises for expected I/O errors; every failure is logged and skipped.
- The tool's own auto-generated artifacts (snapshots, logs, indexes,
  history, the report itself) are excluded from the candidate set.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts import organize, snapshot, utils
from scripts.utils import logger

#: Similarity ratio at or above which two files are reported as "similar".
SIMILAR_THRESHOLD = 0.85

#: Cap on the number of bytes fed to SequenceMatcher (keeps similarity cheap
#: even on multi-MB near-copies; the first-N-KB already matched by size+prefix).
MAX_SIM_BYTES = 64 * 1024

#: Sub-directory (under material/) where exact duplicates are quarantined in
#: ``move`` mode. Originals are never deleted.
DUPLICATES_DIRNAME = "duplicates"


@dataclass
class DuplicateReport:
    """The result of a duplicate scan."""

    exact_groups: List[List[str]] = field(default_factory=list)
    similar_pairs: List[Tuple[str, str, float]] = field(default_factory=list)

    @property
    def exact_count(self) -> int:
        """Total number of files participating in an exact-duplicate group."""
        return sum(len(g) for g in self.exact_groups)

    @property
    def similar_count(self) -> int:
        return len(self.similar_pairs)


@dataclass
class DedupeResult:
    """Outcome of a :func:`run_dedupe` invocation."""

    action: str = "report"
    exact_groups: int = 0
    similar_pairs: int = 0
    moved_count: int = 0
    moved: List[str] = field(default_factory=list)
    report_path: Optional[Path] = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.report_path is not None


# ---------------------------------------------------------------------------
# Candidate gathering
# ---------------------------------------------------------------------------


def _candidate_files(root: Path) -> List[Path]:
    """List regular, non-hidden, non-generated files eligible for comparison.

    Excludes the tool's own artifacts (snapshots / logs / indexes / history /
    the report) and the quarantine folder ``material/duplicates/`` itself so
    that a second run does not re-move already-quarantined copies.
    """
    out: List[Path] = []
    for p in sorted(root.rglob("*")):
        if p.is_dir() or p.is_symlink():
            continue
        if utils.is_hidden(p):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if utils.is_allowed_new_file(rel):
            continue
        # Do not re-scan the quarantine directory.
        if "/material/duplicates/" in rel:
            continue
        out.append(p)
    return out


def _first_1kb_hash(path: Path) -> str:
    """SHA-256 of the first 1 KB (or the whole file if smaller)."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            digest.update(fh.read(1024))
    except OSError:
        return ""
    return digest.hexdigest()


def _similarity(a: Path, b: Path) -> float:
    """Return a difflib similarity ratio in ``[0, 1]`` for two files.

    Compares at most ``MAX_SIM_BYTES`` of each file. Text files are compared
    line-by-line (which yields much better ratios on near-copies than raw
    byte matching); binary files fall back to whole-buffer comparison.
    Returns 0.0 on any read failure so a broken file is never reported as
    similar.
    """
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            ca = fa.read(MAX_SIM_BYTES)
            cb = fb.read(MAX_SIM_BYTES)
    except OSError:
        return 0.0

    # Text-aware comparison. Line-based matching is great for multi-line text
    # near-copies, but degenerates to 0.0 when both files are a single long
    # line (the two "lines" are not identical, so SequenceMatcher sees two
    # different list elements and reports no match). In that case fall back to
    # char-level comparison, which captures the overlap correctly.
    try:
        ta = ca.decode("utf-8")
        tb = cb.decode("utf-8")
        la = ta.splitlines()
        lb = tb.splitlines()
        if len(la) > 1 or len(lb) > 1:
            # Multi-line: compare line-by-line.
            return SequenceMatcher(None, la, lb).ratio()
        # Both are single-line (or empty): compare at the character level.
        return SequenceMatcher(None, ta, tb).ratio()
    except UnicodeDecodeError:
        pass
    return SequenceMatcher(None, ca, cb).ratio()


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------


def find_duplicates(root: Path) -> DuplicateReport:
    """Scan *root* for exact and similar duplicate files.

    The algorithm:
    1. Gather candidates and compute ``(size, first-1KB-hash)`` for each.
    2. Group by that pre-filter key -- only groups with >= 2 entries can
       possibly contain duplicates, so we hash the *full* content only for
       those (a major speed-up on large folders).
    3. Within a group, files sharing the full SHA-256 are an *exact* group.
    4. Within a group, pairs sharing size + first 1 KB but *not* the full hash
       are compared with SequenceMatcher; high-ratio pairs are *similar*.

    Never raises: bad files are skipped and logged.
    """
    root = Path(root).resolve()
    files = _candidate_files(root)

    entries: List[Dict] = []
    for p in files:
        try:
            st = p.stat()
        except OSError:
            logger.warning(f"dedupe: cannot stat {p}; skipped")
            continue
        entries.append(
            {
                "path": p,
                "size": st.st_size,
                "prefix": _first_1kb_hash(p),
                "sha": None,  # filled lazily for candidate groups
            }
        )

    # Pre-filter by the first 1 KB content hash. We deliberately do NOT bucket
    # on exact size: two near-copies of a text file commonly differ by a few
    # bytes, so a strict size-equality bucket would silently drop them. The
    # first-1-KB hash already provides a strong coarse pre-filter, and any
    # size mismatch is harmless -- the full SHA-256 / SequenceMatcher stages
    # below decide the truth.
    preflight: Dict[str, List[Dict]] = defaultdict(list)
    for e in entries:
        preflight[e["prefix"]].append(e)

    report = DuplicateReport()

    for key, grp in preflight.items():
        if len(grp) < 2:
            continue
        # Compute full SHA only for candidate groups.
        for e in grp:
            if e["sha"] is None:
                try:
                    e["sha"] = utils.sha256_file(e["path"])
                except OSError:
                    e["sha"] = ""

        # Exact groups (same full SHA-256).
        by_sha: Dict[str, List[Dict]] = defaultdict(list)
        for e in grp:
            if e["sha"]:
                by_sha[e["sha"]].append(e)
        for sha, bucket in by_sha.items():
            if len(bucket) >= 2:
                paths = sorted(str(e["path"]) for e in bucket)
                report.exact_groups.append(paths)

        # Similar pairs (same pre-filter, different full hash).
        for i in range(len(grp)):
            for j in range(i + 1, len(grp)):
                ea, eb = grp[i], grp[j]
                if not ea["sha"] or not eb["sha"]:
                    continue
                if ea["sha"] == eb["sha"]:
                    continue  # already counted as exact
                ratio = _similarity(ea["path"], eb["path"])
                if ratio >= SIMILAR_THRESHOLD:
                    report.similar_pairs.append(
                        (str(ea["path"]), str(eb["path"]), round(ratio, 3))
                    )

    logger.info(
        f"dedupe: found {len(report.exact_groups)} exact group(s), "
        f"{len(report.similar_pairs)} similar pair(s)"
    )
    return report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def write_report(root: Path, report: DuplicateReport) -> Path:
    """Render ``process/duplicate_report.md`` and return its path."""
    root = Path(root).resolve()
    proc = root / utils.TIER_PROCESS
    proc.mkdir(parents=True, exist_ok=True)
    path = proc / utils.DUPLICATE_REPORT_NAME

    lines: List[str] = []
    lines.append("# Duplicate Report")
    lines.append("")
    lines.append(
        f"- Exact duplicate groups: **{len(report.exact_groups)}** "
        f"({report.exact_count} files)"
    )
    lines.append(f"- Similar pairs: **{len(report.similar_pairs)}**")
    lines.append("")

    if report.exact_groups:
        lines.append("## Exact duplicates (identical content)")
        lines.append("")
        lines.append(
            "Each group lists files with byte-for-byte identical content. "
            "In `move` mode every copy except the first (alphabetical) is "
            "relocated to `material/duplicates/`; originals are never deleted."
        )
        lines.append("")
        for idx, grp in enumerate(report.exact_groups, 1):
            lines.append(f"### Group {idx}")
            for p in grp:
                lines.append(f"- `{_rel(root, p)}`")
            lines.append("")
    else:
        lines.append("## Exact duplicates")
        lines.append("")
        lines.append("None found.")
        lines.append("")

    if report.similar_pairs:
        lines.append("## Similar pairs (near-duplicates, review manually)")
        lines.append("")
        lines.append(
            "These are *not* identical but share size + first 1 KB and a "
            f"similarity ratio >= {SIMILAR_THRESHOLD}. They are reported only "
            "and never moved automatically."
        )
        lines.append("")
        for a, b, ratio in report.similar_pairs:
            lines.append(
                f"- `{_rel(root, a)}` ~ `{_rel(root, b)}` "
                f"(similarity {ratio:.2f})"
            )
        lines.append("")
    else:
        lines.append("## Similar pairs")
        lines.append("")
        lines.append("None found.")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"dedupe: wrote report {path.name}")
    return path


def _rel(root: Path, p: str) -> str:
    try:
        return str(Path(p).relative_to(root))
    except ValueError:
        return p


# ---------------------------------------------------------------------------
# Action driver
# ---------------------------------------------------------------------------


def _quarantine_move(
    src: Path, target: Path, session: utils.OrganizeSession
) -> Tuple[bool, str]:
    """Move a duplicate to its quarantine target using an *exact* path.

    Unlike :func:`organize._move_file` (which auto-suffixes on collision,
    producing a target that C3 traceability cannot anticipate), this helper
    moves to the exact ``target`` requested and raises a conflict if the name
    is already taken. The deterministic path keeps the move consistent with
    the forced verification.
    """
    import shutil

    if not src.exists():
        return False, "source no longer exists"
    if utils.is_readonly(src):
        return False, "readonly file, not moved"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return False, "target already exists, not overwriting"
    try:
        shutil.move(str(src), str(target))
    except OSError as exc:
        return False, f"move failed: {exc}"
    session.add_move(src, target, reason=DUPLICATES_DIRNAME, status="moved")
    return True, str(target)


def run_dedupe(
    root: Path,
    action: str = "report",
    session: Optional[utils.OrganizeSession] = None,
) -> DedupeResult:
    """Scan for duplicates, write the report, and optionally quarantine them.

    Parameters
    ----------
    root:
        Task root.
    action:
        ``"report"`` (default, non-destructive) or ``"move"`` (relocate exact
        duplicates to ``material/duplicates/``).
    session:
        An optional live :class:`OrganizeSession`. When provided (e.g. the
        main pipeline run), the quarantine moves are recorded into it so they
        are covered by the forced verification. When ``None``, a fresh session
        is created (used by the standalone ``dedupe`` command, which performs
        its own snapshot/verify/rollback).

    Returns
    -------
    DedupeResult:
        Summary of what was found and, for ``move`` mode, what was relocated.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"dedupe target is not a directory: {root}")

    if session is None:
        session = utils.OrganizeSession(root=root)

    report = find_duplicates(root)
    # Write the report against the pre-move state so it lists the originals.
    report_path = write_report(root, report)

    result = DedupeResult(
        action=action,
        exact_groups=len(report.exact_groups),
        similar_pairs=len(report.similar_pairs),
        report_path=report_path,
    )

    if action != "move":
        result.message = (
            "report-only; no files were moved. "
            "Use --action move to quarantine exact duplicates."
        )
        return result

    # move mode: quarantine exact duplicates (never the similar pairs).
    # Ensure the three-tier structure exists first (C7 requires it) and the
    # quarantine dir is created so verification can pass.
    try:
        utils.build_structure(root, session)
    except Exception:  # pragma: no cover - defensive
        pass
    dup_dir = root / utils.TIER_ORGANIZE / DUPLICATES_DIRNAME
    dup_dir.mkdir(parents=True, exist_ok=True)
    if str(dup_dir) not in session.new_directories:
        session.new_directories.append(str(dup_dir))

    moved: List[str] = []
    for grp in report.exact_groups:
        # Keep the alphabetically-first copy in place; move the rest.
        keep = sorted(grp)[0]
        for src_str in sorted(grp)[1:]:
            src = Path(src_str)
            target = dup_dir / src.name
            ok, msg = _quarantine_move(src, target, session)
            if ok:
                moved.append(str(target))
                logger.info(f"dedupe: moved duplicate {src.name} -> {target}")
            else:
                logger.warning(
                    f"dedupe: could not move {src} ({msg}); left in place"
                )

    result.moved_count = len(moved)
    result.moved = moved
    result.message = (
        f"moved {len(moved)} exact duplicate file(s) to "
        f"{_rel(root, str(dup_dir))}/; originals preserved."
        if moved
        else "no exact duplicates to move."
    )
    return result


def run_dedupe_verified(root: Path, action: str = "report") -> DedupeResult:
    """Standalone dedup: snapshot -> dedupe -> verify -> (rollback on fail).

    Used by the ``dedupe`` CLI sub-command. It mirrors the forced-verification
    protocol of the main pipeline so a standalone ``move`` never leaves the
    folder half-quarantined. Report-mode is non-destructive and skips verify.
    """
    root = Path(root).resolve()
    session = utils.OrganizeSession(root=root)

    if action != "move":
        # Non-destructive: no snapshot/verify needed.
        return run_dedupe(root, action=action, session=session)

    before = snapshot.make_snapshot(root, phase="before")
    res = run_dedupe(root, action="move", session=session)
    after = snapshot.make_snapshot(root, phase="after")

    from scripts import rollback, verify

    vres = verify.verify(
        root, session=session, before=before, after=after, write_report=False
    )
    if vres.passed:
        res.message = (res.message or "") + " (verified)"
        return res

    rb = rollback.rollback(root, session=session)
    res.moved_count = 0
    res.moved = []
    res.message = (
        "dedupe move failed verification and was rolled back "
        f"({rb.restored_count} files restored)"
    )
    return res
