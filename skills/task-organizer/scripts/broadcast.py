"""broadcast.py -- the context-compression index ("broadcast center").



Design notes

------------

A task folder can hold hundreds of documents. Feeding them all into an AI

session burns tokens and degrades recall (context rot); reading none of

them means working blind. The broadcast center is the middle path, and it

mirrors what context-engineering practice calls *just-in-time retrieval*:

a small, always-fresh digest that says **what is here**, so a later session

can read the index first and open only the original files it actually

needs.



What it does

------------

1. Walks the target folder (skipping hidden files, symlinks, the tool's own

   ``process/`` bookkeeping zone and any previous ``_broadcast/``).

2. Extracts text from every supported format

   (:mod:`scripts.text_extract`: txt / md / csv / json / docx / pdf / pptx /

   xlsx).

3. Produces, per file, a **one-sentence summary** and a few **keywords**:

   - AI mode (``TASK_ORG_AI=1`` + a key, or ``--ai``): one model call

     returns both;

   - local mode (default): first 200 characters + statistical keywords

     (English word frequency, Chinese 2-4 character n-grams with

     fragment filtering).

4. Writes exactly two lightweight files into ``<root>/_broadcast/``:



   ``INDEX.md``

       The human/AI-facing digest -- one line per file, with size, date,

       summary and keywords, plus a "how to use" header.

   ``index.json``

       The machine-facing twin (compact JSON) for programmatic consumers.



Guarantees

----------

- **Read-only**: original files are opened for reading only. The only

  writes in the whole module are the two files inside ``_broadcast/``.

- **Idempotent**: re-running regenerates both index files in place.

- **Bounded**: per-file extraction is capped (see

  :data:`scripts.text_extract.MAX_EXTRACT_CHARS`), the number of indexed

  files is capped (:data:`DEFAULT_MAX_FILES`), and a soft size warning is

  logged when ``INDEX.md`` grows past :data:`MD_SOFT_LIMIT`.

- **Protected**: ``_broadcast`` is a tool-owned prefix, so ``init`` /

  ``organize`` never relocate it (see :mod:`scripts.organize`).

"""

from __future__ import annotations



import json

import os

import re

from collections import Counter

from dataclasses import dataclass, field

from datetime import datetime

from pathlib import Path

from typing import Dict, List, Optional, Tuple



from scripts import text_extract, utils

from scripts.utils import logger



#: Name of the broadcast folder created inside the target root.

BROADCAST_DIRNAME = utils.BROADCAST_DIRNAME



#: The two index files (kept deliberately few -- the folder must stay light).

INDEX_MD_NAME = "INDEX.md"

INDEX_JSON_NAME = "index.json"



#: Default cap on the number of indexed files (keeps the index readable).

DEFAULT_MAX_FILES = 2000



#: Soft limit for INDEX.md size; exceeding it logs a warning (never fails).

MD_SOFT_LIMIT = 256 * 1024



#: Local-mode summary length (characters of the extracted text kept).

SUMMARY_CHARS = 200



#: Default keyword count per file.

DEFAULT_KEYWORDS = 5



#: Common English stopwords (small on purpose -- the index is a hint, not

#: an NLP product).

_STOP_EN = frozenset(

    """

    a an and are as at be been but by can could did do does for from had has

    have how i if in into is it its just me my no not of on or our out over

    so some such than that the their them then there these they this those

    through to too under up us was we were what when where which while who

    why will with would you your

    about after again all also any because before being below between both

    during each few further here his her him itself more most nor now once

    only other own same should still the their theirs them themselves very

    via was were what whatever whether whomever whose

    across among onto upon towards toward within without per etc using used

    against among via thus hence therefore however moreover furthermore

    """.split()

)



#: Characters that make a Chinese bigram useless as a keyword.

_STOP_ZH_CHARS = frozenset(

    "的了是在和与及对等为或者如果这那个我你他她它们以及不没很非常一个些可以不会要将把被让向从到"

    "与其之后之前时候现在知道怎么什么怎样为什么吧呢啊吗呀嗯哦于以其所则该都会这那那些各自"

)



_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")

_EN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")





# ---------------------------------------------------------------------------

# Result object

# ---------------------------------------------------------------------------





@dataclass

class BroadcastResult:

    """Outcome of one broadcast run."""



    root: str

    broadcast_dir: str = ""

    index_md: str = ""

    index_json: str = ""

    file_count: int = 0

    skipped_count: int = 0

    indexed_bytes: int = 0

    index_bytes: int = 0

    ai_used: bool = False

    errors: List[str] = field(default_factory=list)



    @property

    def ok(self) -> bool:

        return bool(self.index_md) and not self.errors



    def summary_lines(self) -> List[str]:

        lines = [f"Root: {self.root}"]

        lines.append(f"broadcast: {self.broadcast_dir or 'not written'}")

        lines.append(

            f"files: {self.file_count} indexed, {self.skipped_count} skipped "

            f"({utils.format_bytes(self.indexed_bytes)} of originals)"

        )

        lines.append(f"index size: {utils.format_bytes(self.index_bytes)}")

        lines.append(f"summary mode: {'ai' if self.ai_used else 'local'}")

        lines.append(f"INDEX.md: {self.index_md or 'not written'}")

        lines.append(f"index.json: {self.index_json or 'not written'}")

        if self.errors:

            lines.append("errors:")

            lines.extend(f"  - {e}" for e in self.errors)

        return lines





# ---------------------------------------------------------------------------

# Local summarization

# ---------------------------------------------------------------------------





#: Sentence-ending punctuation, used to cut summaries at a clean boundary.

_SENTENCE_END = re.compile(r"[。！？!?.;；]")





def local_summary(name: str, text: str, method: str, size: int, pages: Optional[int]) -> str:

    """Deterministic, offline one-line summary (the default mode).



    The file's name is *not* repeated - the index line already carries the

    path. A long snippet is cut at the last sentence boundary inside the

    second half of the window, or hard-cut with an ellipsis.

    """

    if method == "pdf-metadata":

        page_note = f"~{pages} pages, " if pages else ""

        return (

            f"PDF document ({page_note}{utils.format_bytes(size)}); "

            "text not extractable locally"

        )

    if method == "failed":

        return "(summary unavailable - text extraction failed)"

    snippet = re.sub(r"\s+", " ", text).strip()

    if not snippet:

        return "(no extractable text)"

    if len(snippet) <= SUMMARY_CHARS:

        return snippet

    head = snippet[:SUMMARY_CHARS]

    cut = -1

    for m in _SENTENCE_END.finditer(head):

        cut = m.end()

    if cut >= SUMMARY_CHARS // 2:

        return head[:cut]

    return head.rstrip()[:-1] + " …"





def _zh_ngrams(text: str) -> Tuple[Counter, Dict[str, int]]:

    """Count CJK n-grams (n = 2..4) and remember each one's first position.



    Longer n-grams let a repeated term surface as one word ("broadcast

    center"-style phrases) instead of straddling bigrams; first position

    gives single-mention terms a sensible topical ranking (Chinese writing

    tends to put the topic first).

    """

    counts: Counter = Counter()

    first: Dict[str, int] = {}

    pos = 0

    for run in _CJK_RUN.findall(text):

        for n in (2, 3, 4):

            if len(run) < n:

                break

            for i in range(len(run) - n + 1):

                g = run[i : i + n]

                if any(ch in _STOP_ZH_CHARS for ch in g):

                    continue

                counts[g] += 1

                first.setdefault(g, pos + i)

        pos += len(run) + 1  # runs are separated by non-CJK text

    return counts, first





#: Maximum length of an extended Chinese keyword phrase.

_ZH_MAX_WORD = 12





def _extend_zh_word(text: str, g: str) -> str:

    """Greedily extend a repeated n-gram to the full repeated phrase.



    ``上下文压`` (mentioned twice) becomes ``上下文压缩索引`` when every

    occurrence continues with the same characters - a repeated *phrase* is

    a better keyword than any bounded-n cut of it. Extension stops at the

    first non-CJK or stop character, or when occurrences diverge.

    """

    while len(g) < _ZH_MAX_WORD:

        i = text.find(g)

        if i < 0:

            break

        nxt = None

        while i >= 0:

            j = i + len(g)

            if j >= len(text):

                nxt = None

                break

            ch = text[j]

            if not ("\u4e00" <= ch <= "\u9fff") or ch in _STOP_ZH_CHARS:

                nxt = None

                break

            if nxt is None:

                nxt = ch

            elif nxt != ch:

                nxt = None

                break

            i = text.find(g, i + 1)

        if nxt is None:

            break

        extended = g + nxt

        if text.count(extended) != text.count(g):

            break

        g = extended

    return g





def local_keywords(text: str, k: int = DEFAULT_KEYWORDS) -> List[str]:

    """Statistical keywords: English word frequency + Chinese n-grams.



    Deliberately simple and dependency-free. For English text this is

    ordinary term frequency over a small stopword list. Chinese has no

    whitespace to split on, so repeated 2-4 character n-grams stand in for

    words: each repeated n-gram is first extended to the full repeated

    phrase, then overlapping fragments are dropped, while terms mentioned

    once fall back to earliest-position bigrams. Both lists are ranked

    deterministically. AI mode exists for the cases this approximates.

    """

    if not text:

        return []

    lower = text.lower()

    en_counts: Counter = Counter(

        w for w in _EN_WORD.findall(lower) if w not in _STOP_EN

    )

    zh_counts, zh_first = _zh_ngrams(text)



    # Repeated terms first: extend each to its full phrase, then keep only

    # non-overlapping ones (a bigram inside a longer kept word is a

    # fragment of that word, not a word).

    strong = sorted(

        (g for g, c in zh_counts.items() if c >= 2),

        key=lambda g: (-zh_counts[g], zh_first[g], g),

    )

    zh_words: List[str] = []

    spans: List[Tuple[int, int]] = []



    def take(word: str, start: int) -> bool:

        """Keep *word* unless it overlaps an already-kept term's characters.



        A longer phrase supersedes the shorter words it contains, so a

        high-frequency fragment ("索引") taken early does not block the

        full repeated phrase ("上下文压缩索引") discovered later.

        """

        end = start + len(word)

        kept: List[Tuple[str, Tuple[int, int]]] = []

        for w, span in zip(zh_words, spans):

            if w in word:

                continue  # superseded by the longer phrase

            kept.append((w, span))

        for _, (s0, s1) in kept:

            if start < s1 and s0 < end:

                return False

        zh_words[:] = [w for w, _ in kept]

        spans[:] = [span for _, span in kept]

        spans.append((start, end))

        zh_words.append(word)

        return True



    for g in strong:

        if len(zh_words) >= k:

            break

        word = _extend_zh_word(text, g)

        take(word, zh_first[g])



    # Fill remaining slots with single-mention bigrams, earliest first.

    if len(zh_words) < k:

        singles = sorted(

            (g for g, c in zh_counts.items() if c == 1 and len(g) == 2),

            key=lambda g: (zh_first[g], g),

        )

        for g in singles:

            if len(zh_words) >= k:

                break

            if any(g in w or w in g for w in zh_words):

                continue

            take(g, zh_first[g])



    # When the document is Chinese-dominant, English tokens must repeat to

    # count (a stray "https" should not crowd out real keywords).

    en_min = 2 if zh_counts else 1

    en_top = [

        w for w, c in en_counts.most_common() if c >= en_min

    ]



    def rank(words: List[str], counts: Counter) -> List[str]:

        return sorted(words, key=lambda w: (-counts[w], w))



    out: List[str] = []

    en_ranked = rank(en_top, en_counts)[: k + 2]

    zh_ranked = zh_words[: k + 2]

    # Interleave so mixed-language documents get both sides represented.

    for i in range(max(len(en_ranked), len(zh_ranked))):

        if i < len(en_ranked):

            out.append(en_ranked[i])

        if i < len(zh_ranked):

            out.append(zh_ranked[i])

        if len(out) >= k:

            break

    return out[:k]





# ---------------------------------------------------------------------------

# Scanning

# ---------------------------------------------------------------------------





def _iter_indexable(root: Path) -> List[Tuple[Path, Path]]:

    """Collect files worth indexing, in deterministic (sorted) order.



    Walks with ``os.walk(followlinks=False)`` and prunes hidden directories,

    ``process/`` and ``_broadcast/`` *before* descending into them - so a

    symlink cycle or a ``.git`` tree can never blow up the scan (and the

    walk never wastes time inside them). Symlinked files are skipped like

    any other non-regular file. Paths in the result use forward slashes so

    the index is identical on every platform.

    """

    collected: List[Tuple[Path, Path]] = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):

        dirnames[:] = [

            n

            for n in dirnames

            if not n.startswith(".")

            and n not in (utils.TIER_PROCESS, BROADCAST_DIRNAME)

        ]

        base = Path(dirpath)

        for fn in filenames:

            if fn.startswith("."):

                continue

            p = base / fn

            try:

                if p.is_symlink() or not p.is_file():

                    continue

            except OSError:

                continue

            collected.append((p, p.relative_to(root)))

    collected.sort(key=lambda t: t[1].as_posix().lower())

    return collected





def _scan_entries(

    root: Path,

    use_ai: bool,

    max_files: int,

    keywords_per_file: int,

) -> Tuple[List[dict], List[dict], int]:

    """Build one index entry per supported file; collect skips separately.



    Returns ``(files, skipped, total_skipped)``. When the file cap bites,

    the skipped list stays bounded (one aggregate line) while the count

    still reports every file that was left out.

    """

    files: List[dict] = []

    skipped: List[dict] = []

    cap_skipped = 0

    for path, rel in _iter_indexable(root):

        rel_s = rel.as_posix()

        if len(files) >= max_files:

            cap_skipped += 1

            continue

        try:

            st = path.stat()

        except OSError as exc:

            skipped.append({"path": rel_s, "reason": f"stat failed: {exc}"})

            continue

        entry = {

            "path": rel_s,

            "name": path.name,

            "ext": path.suffix.lower(),

            "size": st.st_size,

            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),

        }

        if not text_extract.is_supported(path):

            skipped.append({"path": rel_s, "reason": "unsupported format"})

            continue

        text, method = text_extract.extract_text(path)

        entry["method"] = method

        entry["extracted_chars"] = len(text)



        summary = ""

        keywords: List[str] = []

        if use_ai and text:

            # one round trip yields both the summary and the keywords;

            # force=use_ai lets an explicit --ai bypass the env opt-in

            summary, keywords = utils.ai_digest_file(

                path.name, text[:SUMMARY_CHARS], k=keywords_per_file, force=use_ai

            )

        if not summary:

            # page counting re-reads the file; only the metadata fallback

            # actually needs it

            pages = (

                text_extract.pdf_page_count(path) if method == "pdf-metadata" else None

            )

            summary = local_summary(path.name, text, method, st.st_size, pages)

        if not keywords:

            keywords = local_keywords(text, k=keywords_per_file)

        entry["summary"] = summary

        entry["keywords"] = keywords

        files.append(entry)

    total_skipped = len(skipped) + cap_skipped

    if cap_skipped:

        skipped.append(

            {

                "path": f"({cap_skipped} more file(s))",

                "reason": f"file cap reached ({max_files}); "

                "raise --max-files to index them",

            }

        )

    return files, skipped, total_skipped





# ---------------------------------------------------------------------------

# Index writers

# ---------------------------------------------------------------------------





def _md_inline(text: str) -> str:

    """Make *text* safe inside a one-line markdown bullet.



    Backticks would close the inline-code span around the path, and any

    newline (possible in AI output) would break the one-line-per-file

    contract - both are folded to plain characters.

    """

    return re.sub(r"\s+", " ", text).replace("`", "'")





def _render_md(root: Path, files: List[dict], skipped: List[dict], ai_used: bool) -> str:

    """Render the human/AI-facing digest.



    The file opens with a **categorized directory**: every file is filed

    under its most salient keyword (the keyword that is most frequent across

    the corpus, so popular topics become navigable headings). A reader can

    scan the directory, pick a topic, and jump straight to that section --

    they never have to read every per-file line, which matters when a folder

    holds thousands of files.

    """

    total_bytes = sum(f["size"] for f in files)



    def _kw(k: str) -> str:

        return _md_inline(k).replace(" ", "_")



    # Global keyword frequency drives the category assignment: a file joins

    # the category (keyword) that is most prominent corpus-wide.

    kw_freq: Counter = Counter()

    for f in files:

        for k in f["keywords"]:

            if k:

                kw_freq[_kw(k)] += 1



    def _category(f: dict) -> str:

        best, best_c = "(uncategorized)", -1

        for k in f["keywords"]:

            if not k:

                continue

            c = kw_freq.get(_kw(k), 0)

            if c > best_c:

                best, best_c = _kw(k), c

        return best



    categories: Dict[str, List[dict]] = {}

    for f in files:

        categories.setdefault(_category(f), []).append(f)

    # Largest topics first; stable tie-break by name.

    cat_names = sorted(categories, key=lambda c: (-len(categories[c]), c))



    from scripts import __version__ as _VERSION

    lines: List[str] = []

    lines.append(f"# Broadcast index -- {root.name}")

    lines.append("")

    lines.append(f"> Js Task Organizer v{_VERSION}")

    lines.append("")

    lines.append(

        f"> {datetime.now().isoformat(timespec='seconds')} | "

        f"{len(files)} file(s), {utils.format_bytes(total_bytes)} | "

        f"summary mode: {'ai' if ai_used else 'local'}"

    )

    lines.append(">")

    lines.append(

        "> This is a **read-only digest**: every original file is untouched."

    )

    lines.append(

        "> How to use: read the directory below first, jump to a topic, and"

    )

    lines.append(

        "> open only the original files you actually need -- you never have"

    )

    lines.append("> to read every line in this file.")

    lines.append("")



    # ---- Categorized directory (the navigable table of contents). ----

    lines.append("## Directory")

    lines.append("")

    for c in cat_names:

        lines.append(f"- {c} -- {len(categories[c])} file(s)")

    lines.append("")



    # ---- Files grouped by category. ----

    lines.append("## Files by category")

    lines.append("")

    for c in cat_names:

        members = categories[c]

        lines.append(f"### {c} ({len(members)})")

        lines.append("")

        for f in members:

            kws = " ".join(f"#{_kw(k)}" for k in f["keywords"] if k)

            date = f["mtime"][:10]

            line = (

                f"- `{_md_inline(f['path'])}` "

                f"({f['ext'].lstrip('.') or 'file'}, "

                f"{utils.format_bytes(f['size'])}, {date}) -- "

                f"{_md_inline(f['summary'])}"

            )

            if kws:

                line += f"  {kws}"

            lines.append(line)

        lines.append("")



    if skipped:

        lines.append("## Skipped")

        lines.append("")

        for s in skipped:

            lines.append(f"- `{_md_inline(s['path'])}` -- {_md_inline(s['reason'])}")

        lines.append("")

    return "\n".join(lines)





def _render_json(

    root: Path,

    files: List[dict],

    skipped: List[dict],

    ai_used: bool,

    index_bytes: Dict[str, int],

) -> str:

    """Render the machine-facing twin (compact JSON)."""

    payload = {

        "version": 1,

        "root": str(root),

        "generated_at": datetime.now().isoformat(timespec="seconds"),

        "mode": "ai" if ai_used else "local",

        "file_count": len(files),

        "total_bytes": sum(f["size"] for f in files),

        "index_bytes": index_bytes,

        "files": files,

        "skipped": skipped,

    }

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))





# ---------------------------------------------------------------------------

# Entry point

# ---------------------------------------------------------------------------





def broadcast(

    root: Path,

    use_ai: bool = False,

    max_files: int = DEFAULT_MAX_FILES,

    keywords_per_file: int = DEFAULT_KEYWORDS,

    verbose: bool = False,

    quiet: bool = False,

) -> BroadcastResult:

    """Build (or rebuild) the broadcast center under *root*.



    Parameters

    ----------

    root:

        Folder to digest. Must already exist -- a typo must fail loudly

        rather than materialise a new tree (same rule as ``snapshot``).

    use_ai:

        Force AI summaries even when ``TASK_ORG_AI`` is unset. When the

        variable *is* set, AI mode is used either way.

    max_files:

        Safety cap on indexed files.

    keywords_per_file:

        Keywords kept per file in the index.

    """

    root = Path(root).resolve()

    result = BroadcastResult(root=str(root))

    # Console-only logging: broadcast must not write anything besides the

    # two index files, and that includes a process/logs/ trail in a folder

    # that may not even be a task folder.

    logger.setup_logging(root, verbose=verbose, quiet=quiet, file_log=False)



    if not root.is_dir():

        logger.error(f"broadcast: root is not a directory: {root}")

        result.errors.append(f"root is not a directory: {root}")

        return result



    # ``--ai`` requests AI mode; the environment opt-in requests it too.

    # What the index may *claim* is the intersection with an actual key -

    # a request without a key degrades to local and must be labelled so.

    ai_requested = use_ai or utils.ai_enabled()

    ai_capable = bool(ai_requested and utils.ai_available())

    result.ai_used = ai_capable

    if ai_requested and not ai_capable:

        logger.warning(

            "broadcast: AI summaries requested but no API key/TASK_ORG_AI "

            "configured; falling back to local summaries"

        )



    try:

        files, skipped, total_skipped = _scan_entries(

            root, ai_requested, max_files, keywords_per_file

        )

    except Exception as exc:  # noqa: BLE001 - never crash the caller

        logger.error(f"broadcast: scan failed: {exc}")

        result.errors.append(f"scan failed: {exc}")

        return result



    result.file_count = len(files)

    result.skipped_count = total_skipped

    result.indexed_bytes = sum(f["size"] for f in files)



    bdir = root / BROADCAST_DIRNAME

    try:

        bdir.mkdir(exist_ok=True)

        md_text = _render_md(root, files, skipped, result.ai_used)

        md_path = bdir / INDEX_MD_NAME

        # newline="\n": the index must be byte-identical on every platform

        md_path.write_text(md_text, encoding="utf-8", newline="\n")

        # ``index.json`` records only INDEX.md's size -- a file cannot

        # truthfully contain its own final size, and the stat-based total

        # is reported separately in the result summary.

        json_text = _render_json(

            root,

            files,

            skipped,

            result.ai_used,

            {"md": len(md_text.encode("utf-8"))},

        )

        json_path = bdir / INDEX_JSON_NAME

        json_path.write_text(json_text, encoding="utf-8", newline="\n")

    except OSError as exc:

        logger.error(f"broadcast: write failed: {exc}")

        result.errors.append(f"write failed: {exc}")

        return result



    result.broadcast_dir = str(bdir)

    result.index_md = str(md_path)

    result.index_json = str(json_path)

    result.index_bytes = md_path.stat().st_size + json_path.stat().st_size



    md_bytes = len(md_text.encode("utf-8"))

    if md_bytes > MD_SOFT_LIMIT:

        logger.warning(

            f"broadcast: INDEX.md is {utils.format_bytes(md_bytes)} "

            f"(soft limit {utils.format_bytes(MD_SOFT_LIMIT)}); consider "

            "broadcasting sub-folders separately or raising --max-files discipline"

        )

    logger.info(

        f"broadcast: indexed {result.file_count} file(s), skipped "

        f"{result.skipped_count}; wrote {INDEX_MD_NAME} + {INDEX_JSON_NAME} "

        f"({utils.format_bytes(result.index_bytes)})"

    )

    return result

