"""Shared utilities for task-organizer.



Design notes

------------

This module is the only place where cross-cutting helpers live:



- path / file / directory primitives that tolerate Windows + POSIX;

- an append-only Markdown log writer that lives under process/;

- AI summary integration (optional, gracefully degrades to filename+200-char

  placeholder when no API key is configured);

- three-tier structure constants and builder;

- "new-file allowance" used by verify.py to whitelist index/log files.



All functions have type hints and docstrings, and never raise for

expected I/O errors -- they log and degrade gracefully, so the top-level

organize flow never crashes mid-run.

"""

from __future__ import annotations



import hashlib

import json

import os

import re

from dataclasses import dataclass, field

from datetime import datetime

from pathlib import Path

from typing import Iterable, List, Optional, Sequence, Set, Tuple



# ---------------------------------------------------------------------------

# Three-tier structure constants

# ---------------------------------------------------------------------------



#: organize tier: raw source material and downloaded reference material.

TIER_ORGANIZE = "material"

#: process tier: drafts, intermediate files, plus snapshots/logs/indexes.

TIER_PROCESS = "process"

#: results tier: final deliverables.

TIER_RESULT = "results"



#: organize sub-dirs.

SUB_INIT = "initial"

SUB_DOWNLOAD = "downloaded"

SUB_ORGANIZE = "material" # alias to keep material/Index.* unambiguous



#: Files that always live at organize/.

INDEX_MD_NAME = "Index.md"

INDEX_XLSX_NAME = "Index.xlsx"



#: Files that always live at process/.

SNAPSHOT_BEFORE_PREFIX = "before"

SNAPSHOT_AFTER_PREFIX = "after"

LOG_PREFIX = "OrganizeLog"

VERIFY_REPORT_NAME = "verification_report.md"



#: The broadcast center (context-compression index) folder. Tool-owned:

#: ``init`` / ``organize`` never relocate it (see organize._OWNED_PREFIXES).

BROADCAST_DIRNAME = "_broadcast"


#: Files that may legitimately sit at the task root (tool-owned config
#: template, not user material). ``verify._run_c8`` uses this to exclude
#: them when counting "loose files at the root" as a missed-init signal.
ROOT_OWNED_FILES: Set[str] = {".task-organizer.yml"}



#: Allowed new files in after-snapshot (whitelist used by verify.py).

ALLOWED_NEW_FILE_NAMES: Set[str] = {

    INDEX_MD_NAME,

    INDEX_XLSX_NAME,

    VERIFY_REPORT_NAME,

}





# ---------------------------------------------------------------------------

# Dataclasses

# ---------------------------------------------------------------------------





@dataclass

class MoveRecord:

    """A single recorded move operation.



    Attributes

    ----------

    source: original absolute path of the moved file.

    target: final absolute path after the move.

    reason: placement rule applied (one of initial/downloaded/process/results/

            unclassified).

    status: "moved" | "skipped" (skipped when source was readonly or locked).

    timestamp: ISO-8601 local time string.

    """



    source: str

    target: str

    reason: str

    status: str

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())



    def to_dict(self) -> dict:

        return {

            "source": self.source,

            "target": self.target,

            "reason": self.reason,

            "status": self.status,

            "timestamp": self.timestamp,

        }





@dataclass

class OrganizeSession:

    """Accumulated state for one organize run.



    Used by organize/verify/rollback to share state without a class hierarchy.

    """



    root: Path

    new_directories: List[str] = field(default_factory=list)

    move_records: List[MoveRecord] = field(default_factory=list)

    skipped_files: List[str] = field(default_factory=list)

    empty_folders_skipped: List[str] = field(default_factory=list)

    log_path: Optional[Path] = None



    def add_move(

        self,

        source: Path,

        target: Path,

        reason: str,

        status: str = "moved",

    ) -> MoveRecord:

        rec = MoveRecord(

            source=str(source),

            target=str(target),

            reason=reason,

            status=status,

        )

        self.move_records.append(rec)

        return rec



    def add_skipped(self, path: Path, reason: str) -> None:

        self.skipped_files.append(f"{path} ({reason})")





# ---------------------------------------------------------------------------

# Path / file primitives

# ---------------------------------------------------------------------------





def now_stamp() -> str:

    """Return ``YYYYMMDD_HHMMSS`` local-time stamp."""

    return datetime.now().strftime("%Y%m%d_%H%M%S")





def sha256_file(path: Path) -> str:

    """Compute SHA-256 of a file in streaming mode.



    Returns 64-char hex digest. Raises ``OSError`` if the file is unreadable.

    """

    digest = hashlib.sha256()

    with open(path, "rb") as fh:

        for chunk in iter(lambda: fh.read(1 << 20), b""):

            digest.update(chunk)

    return digest.hexdigest()





def is_hidden(p: Path) -> bool:

    """Return True if any path component starts with ``.``.



    Covers ``.hidden``, ``a/.hidden/b``, ``a/.b`` -- used to filter dot-files

    during scanning.

    """

    parts = p.parts

    for part in parts[1:]:

        if part.startswith(".") and part not in (".", ".."):

            return True

    return False





def is_readonly(p: Path) -> bool:

    """Return True if the file exists and is read-only.



    On POSIX we check ``stat``; on Windows we also check the ACL.

    Used by organize.py to skip readonly files.

    """

    if not p.exists():

        return False

    try:

        import stat as _stat



        return not (p.stat().st_mode & _stat.S_IWRITE)

    except OSError:

        return False





def ensure_parent(p: Path) -> None:

    """Ensure the parent directory of ``p`` exists (mkdir -p semantics)."""

    p.parent.mkdir(parents=True, exist_ok=True)





def unique_target_dir(target_dir: Path, name: str) -> Path:

    """Return an unused target path, auto-appending ``_1``/``_2`` suffix.



    Rule:

    - If ``target_dir/name`` does not exist -> return as-is.

    - Otherwise try ``name_1.ext``, ``name_2.ext``,... until free.

    - For names without an extension, suffix before the whole name.

    """

    if not (target_dir / name).exists():

        return target_dir / name

    stem = Path(name)

    base, suffix = stem.stem, stem.suffix

    for i in range(1, 10_000):

        candidate = target_dir / f"{base}_{i}{suffix}"

        if not candidate.exists():

            return candidate

    raise OSError(f"could not find a unique name under {target_dir} for {name}")





# ---------------------------------------------------------------------------

# Log / report file naming helpers

# ---------------------------------------------------------------------------





def snapshot_filename(prefix: str, timestamp: Optional[str] = None) -> str:

    """Return a snapshot file name: ``YYYYMMDD_HHMMSS_<prefix>.json``."""

    ts = timestamp or now_stamp()

    return f"{ts}_{prefix}.json"





def log_filename(timestamp: Optional[str] = None) -> str:

    """Return the organize log name: ``YYYYMMDD_HHMMSS_OrganizeLog.md``."""

    ts = timestamp or now_stamp()

    return f"{ts}_{LOG_PREFIX}.md"





#: Extra auto-generated artifacts introduced.

HISTORY_PREFIX = "history"

DUPLICATE_REPORT_NAME = "duplicate_report.md"

LOG_DIRNAME = "logs"



#: Provenance manifest introduced (see :mod:`scripts.sources`).

MANIFEST_NAME = "sources.json"





def is_allowed_new_file(name: str) -> bool:

    """True if *name* is an expected auto-generated file (index/log/snapshot).



    Matches the fixed-name artifacts (index, verification report, duplicate

    report) plus any timestamped pipeline file:

    ``YYYYMMDD_HHMMSS_<before|after>.json``,

    ``YYYYMMDD_HHMMSS_<OrganizeLog|Cancelled>.md``,

    ``YYYYMMDD_HHMMSS_history.json`` (operation history), and the per-day log

    ``YYYYMMDD.log`` under ``process/logs/``. Using a timestamp regex (rather

    than string-prefixing on LOG_PREFIX) keeps this robust to the folder

    naming scheme.



    The provenance manifest is whitelisted by **exact path**

    (``process/sources.json``) -- deliberately *not* by bare name, so a

    user file that merely happens to be called ``sources.json`` still gets

    hashed and verified.

    """

    norm = name.replace("\\", "/")

    base = norm.rsplit("/", 1)[-1]

    if base in ALLOWED_NEW_FILE_NAMES:

        return True

    low = base.lower()

    if low.endswith(VERIFY_REPORT_NAME):

        return True

    if low == DUPLICATE_REPORT_NAME:

        return True

    # Path-based: anything the tool writes under process/history or

    # process/logs is an audit artifact, never user content.

    if "/process/history/" in norm or f"/process/{LOG_DIRNAME}/" in norm:

        return True

    # Provenance manifest: exact path only (see docstring).

    if norm == f"{TIER_PROCESS}/{MANIFEST_NAME}":

        return True

    # Timestamped pipeline files: 8 digits + '_' + 6 digits + '_' + label.

    if re.match(r"^\d{8}_\d{6}_(before|after|organizelog|cancelled|history)\.", low):

        return True

    # Per-day log files: YYYYMMDD.log or YYYYMMDD_HHMMSS.log.

    if re.match(r"^\d{8}(_\d{6})?\.(log)$", low):

        return True

    return False





def iter_new_files_under(p: Path) -> Iterable[Path]:

    """Yield files under *p* that are considered 'new' by verify.py."""

    for f in p.rglob("*"):

        if f.is_file():

            if is_allowed_new_file(str(f)):

                yield f





# ---------------------------------------------------------------------------

# Three-tier structure

# ---------------------------------------------------------------------------





def build_structure(root: Path, session: OrganizeSession) -> List[Path]:

    """Create the standard three-tier structure under *root*.



    Layout::



        root/

            _broadcast/     # read-only context-compression index (INDEX.md +

                            # index.json, written by scripts.broadcast)

            organize/

                initial/

                downloaded/

                Index.md (placeholder, filled by index_md)

                Index.xlsx (placeholder, filled by index_xlsx)

            process/

            results/



    ``_broadcast/`` is created here so the folder is complete from the first

    minute of a task: the user's requirement is that every task start builds

    all folder types (materials / process / results / broadcast) before any

    content is written. The directory itself stays empty until ``broadcast``

    fills it - an empty ``_broadcast/`` is never mistaken for content by

    ``organize`` (it is a tool-owned prefix) or by ``broadcast`` (idempotent).



    Returns the list of directories created (for logging & rollback).

    Never raises; missing dirs are created, existing dirs are preserved.

    """

    created: List[Path] = []



    dirs_to_make = [

        root / TIER_ORGANIZE / SUB_INIT,

        root / TIER_ORGANIZE / SUB_DOWNLOAD,

        root / TIER_PROCESS,

        root / TIER_RESULT,

        root / BROADCAST_DIRNAME,

    ]



    for d in dirs_to_make:

        if not d.exists():

            try:

                d.mkdir(parents=True, exist_ok=True)

                created.append(d)

            except OSError as exc: # pragma: no cover - rare

                session.skipped_files.append(f"{d} (mkdir failed: {exc})")

        else:

            # Record for log even if already present.

            pass



    # Also record any created parents (e.g. root itself when it was missing).

    if not root.exists():

        try:

            root.mkdir(parents=True, exist_ok=True)

        except OSError:

            pass



    # Dedup and stable order (deepest first is irrelevant, use insertion).

    seen: Set[Path] = set()

    for d in created:

        if d not in seen:

            session.new_directories.append(str(d))

            seen.add(d)



    return created





def structure_complete(root: Path) -> bool:

    """Return True if the three-tier structure is fully present under *root*."""

    required = [

        root / TIER_ORGANIZE / SUB_INIT,

        root / TIER_ORGANIZE / SUB_DOWNLOAD,

        root / TIER_PROCESS,

        root / TIER_RESULT,

    ]

    return all(d.is_dir() for d in required)





def list_empty_dirs(root: Path) -> List[Path]:

    """List empty directories under *root* (used for "skip empty folder").



    Tool-owned directories (``organize``, ``process``, ``results``,

    ``_broadcast``) are never reported: ``_broadcast/`` in particular is

    created empty by ``init`` on purpose and only ``broadcast`` fills it.

    """

    from scripts.organize import owned_prefixes  # local import: avoid a cycle



    owned = owned_prefixes()

    empties: List[Path] = []

    for p in sorted(root.rglob("*")):

        if not p.is_dir() or list(p.iterdir()):

            continue

        rel = p.relative_to(root)

        if rel.parts and rel.parts[0] in owned:

            continue

        empties.append(p)

    return empties





# ---------------------------------------------------------------------------

# Markdown log / report writing

# ---------------------------------------------------------------------------





def append_log(

    session: OrganizeSession,

    title: str,

    body_lines: Sequence[str],

) -> Path:

    """Append a timestamped Markdown section to ``session.log_path``.



    If the log file does not exist yet, it is created with a header.

    Returns the log path (absolute) so callers can store it.

    """

    if session.log_path is None:

        ts = now_stamp()

        log_file = Path(session.root / TIER_PROCESS / log_filename(ts))

        log_file.parent.mkdir(parents=True, exist_ok=True)

        log_file.write_text(

            f"# OrganizeLog({datetime.now().isoformat()})\n\n",

            encoding="utf-8",

        )

        session.log_path = log_file



    with open(session.log_path, "a", encoding="utf-8") as fh:

        fh.write(f"\n## {title}\n\n")

        for line in body_lines:

            fh.write(line + "\n")

    return session.log_path





def write_json(path: Path, data: object) -> None:

    """Write *data* as UTF-8 JSON, creating parents if needed."""

    ensure_parent(path)

    path.write_text(

        json.dumps(data, ensure_ascii=False, indent=2),

        encoding="utf-8",

    )





def read_json(path: Path) -> object:

    """Read JSON from *path* and return the parsed object."""

    return json.loads(path.read_text(encoding="utf-8"))





# ---------------------------------------------------------------------------

# AI summary integration (optional)

# ---------------------------------------------------------------------------



#: Environment variable names checked in order. The first non-empty value wins.

_AI_API_KEY_ENV = [

    "TASK_ORG_AI_API_KEY",

    "OPENAI_API_KEY",

    "DASHSCOPE_API_KEY",

    "ANTHROPIC_API_KEY",

]



_AI_MODEL_ENV = "TASK_ORG_AI_MODEL"



#: Master switch for *any* outbound AI call. Summaries are local-only unless

#: this is explicitly enabled -- many users already have ``OPENAI_API_KEY``

#: exported for unrelated tooling, and silently spending tokens on every

#: index rebuild is exactly the kind of hidden cost this project avoids.

AI_ENABLE_ENV = "TASK_ORG_AI"





def ai_enabled() -> bool:

    """True only when AI summaries were explicitly opted into.



    Requires ``TASK_ORG_AI`` to be set to a truthy value (``1`` / ``true`` /

    ``yes`` / ``on``) **and** an API key to be present. Default: disabled, so

    the index is always generated with the deterministic local placeholder.

    """

    flag = os.environ.get(AI_ENABLE_ENV, "").strip().lower()

    if flag not in ("1", "true", "yes", "on"):

        return False

    return _configured_ai_key() is not None





def ai_available() -> bool:

    """True when an API key is configured - capability, not opt-in.



    Callers that received an explicit ``--ai`` flag combine this with their

    own policy instead of relying on the environment opt-in alone.

    """

    return _configured_ai_key() is not None





def _configured_ai_key() -> Optional[str]:

    """Return the first configured AI API key, or None if none set."""

    for env in _AI_API_KEY_ENV:

        val = os.environ.get(env, "").strip()

        if val:

            return val

    return None





def _read_text_sample(path: Path, max_chars: int = 200) -> str:

    """Read up to *max_chars* of a text file; return empty string on failure.



    Binary files fall back to their filename (no content sampling).

    """

    try:

        text = path.read_text(encoding="utf-8")

    except (UnicodeDecodeError, OSError):

        return ""

    text = re.sub(r"\s+", " ", text).strip()

    return text[:max_chars]





def generate_summary(path: Path, hint: str = "") -> str:

    """Generate a one-line summary for a file.



    Strategy:

    - **Local placeholder by default** (``filename + first-200-characters``).

      This is deterministic, offline and costs nothing.

    - Only when AI summaries are explicitly enabled (:func:`ai_enabled`,

      i.e. ``TASK_ORG_AI=1`` *and* a key) is an API call attempted; any

      failure falls through to the placeholder, so the index pipeline always

      completes even without network.



    The placeholder never fails, so indexing is safe by construction.

    """

    key = _configured_ai_key()

    name = Path(path).name

    sample = _read_text_sample(path, 200)



    if key and ai_enabled():

        try:

            summary = _ai_summarize(name, sample, hint, key)

            if summary:

                return summary

        except Exception: # pragma: no cover - optional feature

            # AI failure is non-fatal; fall through to placeholder.

            pass



    if sample:

        return f"{name}: {sample[:200]}"

    return f"{name} (placeholder summary: not generated)"





def ai_summarize_file(name: str, sample: str, hint: str = "") -> str:

    """Public wrapper: one-sentence AI summary, or ``""`` when unavailable.



    Requires the same opt-in as :func:`ai_enabled`. Any failure returns

    ``""`` so callers can fall back to the local placeholder.

    """

    key = _configured_ai_key()

    if not (key and ai_enabled()):

        return ""

    try:

        return _ai_summarize(name, sample, hint, key)

    except Exception:  # noqa: BLE001 - AI is strictly optional

        return ""





def ai_keywords(name: str, sample: str, k: int = 5) -> List[str]:

    """Ask the model for up to *k* keywords for a file.



    Returns ``[]`` when AI is disabled or the call fails, so the caller can

    fall back to the local statistical keywords.

    """

    key = _configured_ai_key()

    if not (key and ai_enabled()):

        return []

    try:

        text = _ai_chat(

            system=(

                "You extract keywords from a file's content. "

                "Reply with a comma-separated list only, no prose."

            ),

            user=(

                f"filename: {name}\n"

                f"Content excerpt: {sample}\n"

                f"List up to {k} keywords (single words or short phrases), "

                "comma-separated."

            ),

            max_tokens=80,

            api_key=key,

        )

    except Exception:  # noqa: BLE001 - AI is strictly optional

        return []

    return _parse_keywords(text, k)





def ai_digest_file(

    name: str, sample: str, k: int = 5, force: bool = False

) -> Tuple[str, List[str]]:

    """Public wrapper: one AI call returning ``(summary, keywords)``.



    Asking for both in a single round trip halves the latency and the

    tokens spent per file. Any failure returns ``("", [])`` so callers can

    fall back to the local summary and statistical keywords.



    *force* lets a caller that received an explicit ``--ai`` flag use AI

    even when ``TASK_ORG_AI`` is unset; a configured key is still required.

    """

    key = _configured_ai_key()

    if not key or not (ai_enabled() or force):

        return "", []

    try:

        text = _ai_chat(

            system=(

                "You digest a file for a searchable index. "

                "Reply with exactly two lines and nothing else: "

                "line 1 is a one-sentence summary (at most 40 words); "

                "line 2 is a comma-separated list of keywords."

            ),

            user=(

                f"filename: {name}\n"

                f"Content excerpt: {sample}\n"

                "Line 1: one-sentence summary. "

                f"Line 2: up to {k} keywords, comma-separated."

            ),

            max_tokens=140,

            api_key=key,

        )

    except Exception:  # noqa: BLE001 - AI is strictly optional

        return "", []

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]

    if not lines:

        return "", []

    summary = re.sub(r"\s+", " ", lines[0]).strip("-*# !?").strip()[:300]

    return summary, _parse_keywords("\n".join(lines[1:]), k)





def _parse_keywords(text: str, k: int) -> List[str]:

    """Split a comma/、/;-separated keyword reply into a clean list."""

    parts = re.split(r"[,，、;；\n]", text or "")

    out: List[str] = []

    for p in parts:

        kw = p.strip().strip("-*").strip()

        if kw and kw.lower() not in {x.lower() for x in out}:

            out.append(kw[:40])

        if len(out) >= k:

            break

    return out





def _ai_summarize(

    name: str,

    sample: str,

    hint: str,

    api_key: str,

) -> str:

    """Call a generic OpenAI-compatible chat-completions endpoint.



    Only used when an API key is configured. Returns "" on any failure.

    Intended to keep the public surface small while remaining useful.

    """

    try:

        text = _ai_chat(

            system="You summarize a file's content in one English sentence.",

            user=(

                f"filename: {name}\n"

                f"Category hint: {hint or 'unspecified'}\n"

                f"Content excerpt: {sample}\n"

                "Summarize this file's content in one sentence "

                "(no more than 40 words)."

            ),

            max_tokens=60,

            api_key=api_key,

        )

        return text[:40]

    except Exception:

        return ""





def _ai_chat(system: str, user: str, max_tokens: int, api_key: str) -> str:

    """One OpenAI-compatible chat-completions round trip. Returns "" on failure."""

    try:

        import urllib.parse

        import urllib.request



        base_url = os.environ.get(

            "TASK_ORG_AI_BASE_URL",

            "https://api.openai.com/v1",

        ).rstrip("/")

        model = os.environ.get(_AI_MODEL_ENV, "gpt-4o-mini")



        payload = {

            "model": model,

            "messages": [

                {"role": "system", "content": system},

                {"role": "user", "content": user},

            ],

            "max_tokens": max_tokens,

            "temperature": 0,

        }



        req = urllib.request.Request(

            f"{base_url}/chat/completions",

            data=json.dumps(payload).encode("utf-8"),

            headers={

                "Content-Type": "application/json",

                "Authorization": f"Bearer {api_key}",

            },

            method="POST",

        )

        with urllib.request.urlopen(req, timeout=30) as resp:

            data = json.loads(resp.read().decode("utf-8"))

        return data["choices"][0]["message"]["content"].strip()

    except Exception:

        return ""





def format_bytes(n: int) -> str:

    """Return a human-readable size: B / KB / MB / GB."""

    units = ["B", "KB", "MB", "GB", "TB"]

    i = 0

    v = float(n)

    while v >= 1024 and i < len(units) - 1:

        v /= 1024

        i += 1

    if i == 0:

        return f"{int(v)} {units[i]}"

    return f"{v:.1f} {units[i]}"

