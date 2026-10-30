"""text_extract.py -- pull plain text out of the document formats a task
folder actually contains.

Design notes
------------
The broadcast center (:mod:`scripts.broadcast`) needs *some* text from every
file to summarize it. This module is that extraction layer, and it follows
the project's dependency policy: **the standard library does the work,
third-party libraries only make it better**.

Per format:

===========  ============================================================
Extension    Strategy
===========  ============================================================
``.txt``     direct read (utf-8 with replacement, never raises)
``.md``       direct read
``.csv``      direct read (rows are joined; cell text is the signal)
``.json``     direct read
``.docx``     ``zipfile`` + ``xml.etree`` -- ``word/document.xml``, ``w:t``
``.pptx``     ``zipfile`` + ``xml.etree`` -- ``ppt/slides/slideN.xml``, ``a:t``
``.xlsx``     ``openpyxl`` when installed, else ``zipfile`` + ``sharedStrings``
``.pdf``      ``pdfminer``/``PyPDF2`` when installed, else a stdlib
              ``zlib`` + text-operator scan, else metadata-only
===========  ============================================================

Every extractor returns ``(text, method)`` and never raises: a corrupt or
unreadable file degrades to ``("", "failed")`` so the caller can still index
the file's metadata. Extraction is capped at :data:`MAX_EXTRACT_CHARS`
characters per file, which bounds both memory and the time spent on a
pathologically large document.

The stdlib PDF path is deliberately *best effort*: it decompresses Flate
streams and collects the strings shown by ``Tj`` / ``TJ`` operators. Text
that is subset-encoded, drawn as curves, or split into positioned
fragments may come out garbled -- that is why library extractors are tried
first and why the caller always records the *method* used.
"""
from __future__ import annotations

import codecs
import json
import re
import zipfile
import zlib
from pathlib import Path
from typing import List, Optional, Tuple

#: Hard cap on characters extracted from a single file. Keeps a 500 MB CSV
#: or a 1000-slide deck from being pulled into memory in full.
MAX_EXTRACT_CHARS = 20_000

#: Bytes read from the head of a plain-text file to sniff its encoding.
_ENCODING_SAMPLE_BYTES = 65_536

#: Cap on bytes read from a PDF on the stdlib path (metadata fallback keeps
#: working on bigger files; text extraction is best effort anyway).
_PDF_STDLIB_MAX_BYTES = 64 * 1024 * 1024

#: Byte-order marks worth honouring before guessing.
_BOM_TABLE = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

#: Strict-decode candidates, in order. ``gb18030`` is a GBK superset and
#: ``big5`` covers traditional-Chinese notes; both still show up in real
#: task folders. ``latin-1`` never fails, so it is only the last resort.
_TEXT_ENCODINGS = ("utf-8", "gb18030", "big5")

#: Private-use characters: a GBK/Big5 byte sequence decoded under the wrong
#: legacy codec lands here, so any decode that yields them is rejected.
_PRIVATE_USE = re.compile("[\ue000-\uf8ff]")

#: Extensions read directly as text.
TEXT_EXTS = frozenset({".txt", ".md", ".csv", ".json", ".log", ".markdown"})

#: Extensions handled through the ZIP+XML path (OOXML family).
OOXML_EXTS = frozenset({".docx", ".pptx", ".xlsx"})

#: PDF extension (handled by the tiered PDF path).
PDF_EXTS = frozenset({".pdf"})

#: Subtitle extensions. Read as text, but their index numbers and timestamp
#: lines carry no summary signal - those are stripped first.
SUBTITLE_EXTS = frozenset({".srt", ".vtt"})

#: Every extension the broadcast center knows how to open.
SUPPORTED_EXTS = TEXT_EXTS | OOXML_EXTS | PDF_EXTS | SUBTITLE_EXTS

# OOXML namespaces.
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def is_supported(path: Path) -> bool:
    """True when *path* has an extension this module can open."""
    return Path(path).suffix.lower() in SUPPORTED_EXTS


def extract_text(path: Path, max_chars: int = MAX_EXTRACT_CHARS) -> Tuple[str, str]:
    """Extract text from *path*.

    Returns ``(text, method)`` where *method* is a short tag recording how
    the text was obtained (``text``, ``docx``, ``pptx``, ``xlsx``,
    ``xlsx-openpyxl``, ``pdf-pdfminer``, ``pdf-pypdf2``, ``pdf-stdlib``,
    ``pdf-metadata`` or ``failed``). The text is truncated to *max_chars*.

    Never raises.
    """
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext in TEXT_EXTS:
            return _extract_plain(p, max_chars)
        if ext == ".docx":
            return _extract_docx(p, max_chars)
        if ext == ".pptx":
            return _extract_pptx(p, max_chars)
        if ext == ".xlsx":
            return _extract_xlsx(p, max_chars)
        if ext == ".pdf":
            return _extract_pdf(p, max_chars)
        if ext in SUBTITLE_EXTS:
            return _extract_subtitle(p, max_chars)
    except Exception:  # noqa: BLE001 - extraction must never crash the caller
        return "", "failed"
    return "", "unsupported"


# ---------------------------------------------------------------------------
# plain text
# ---------------------------------------------------------------------------


def _sniff_encoding(sample: bytes) -> str:
    """Guess a text encoding from the first bytes of a file.

    BOM first, then strict utf-8, then the legacy Chinese encodings, then
    a NUL-density probe for BOM-less UTF-16, and finally latin-1 (which
    decodes any byte sequence, so it always terminates the search). Any
    decode that yields private-use characters is rejected: GBK/Big5 bytes
    under the wrong codec land exactly there (and real text almost never
    does).
    """
    for bom, enc in _BOM_TABLE:
        if sample.startswith(bom):
            return enc
    for enc in _TEXT_ENCODINGS:
        # drop up to 3 tail bytes: a multi-byte character may straddle the
        # sample boundary and must not fail the whole probe
        for candidate in (sample, sample[:-3]):
            try:
                text = candidate.decode(enc)
            except UnicodeDecodeError:
                continue
            if _PRIVATE_USE.search(text):
                continue
            return enc
    if sample.count(b"\x00") > len(sample) // 8:
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                sample.decode(enc)
                return enc
            except UnicodeDecodeError:
                continue
    return "latin-1"


def _extract_plain(path: Path, max_chars: int) -> Tuple[str, str]:
    """Read a text file, tolerating any encoding problem.

    The encoding is sniffed from a bounded head sample, then only
    *max_chars* characters are read - a 500 MB log cannot blow up the
    process. Undecodable bytes degrade to U+FFFD, never an exception.
    """
    try:
        with path.open("rb") as f:
            sample = f.read(_ENCODING_SAMPLE_BYTES)
        enc = _sniff_encoding(sample)
        with path.open("r", encoding=enc, errors="replace", newline="") as f:
            text = f.read(max_chars)
    except OSError:
        return "", "failed"
    return text, "text"


# ---------------------------------------------------------------------------
# subtitles (SRT / VTT): strip index + timestamp lines, keep the dialogue
# ---------------------------------------------------------------------------

#: SRT timestamp axis: a cue time-range such as
#: ``00:00:02,940 --> 00:00:03,580`` (with an optional index number and
#: optional aligned-text / position settings after it). The match is anchored
#: on the ``-->`` so ordinary dialogue lines that happen to contain numbers
#: or colons are never dropped.
_SRT_TIMELINE = re.compile(
    r"(?:\d+\s+)?"
    r"\d{1,2}:\d{2}(?::\d{2})?[.,]?\d*\s*-->\s*"
    r"\d{1,2}:\d{2}(?::\d{2})?[.,]?\d*"
)


def is_srt(path: Path) -> bool:
    """True when *path* is a SubRip subtitle file."""
    return Path(path).suffix.lower() == ".srt"


def is_vtt(path: Path) -> bool:
    """True when *path* is a WebVTT subtitle file."""
    return Path(path).suffix.lower() == ".vtt"


def strip_subtitle(text: str) -> str:
    """Remove SRT/VTT structure so only the spoken dialogue remains.

    Drops the ``WEBVTT`` / ``WEBVTT ...`` header, standalone index numbers,
    and the ``HH:MM:SS[,ms] --> HH:MM:SS[,ms]`` timestamp axis; joins the
    surviving lines on single spaces and trims the result. The text the
    caller passes in is already bounded to *max_chars* characters.
    """
    out: List[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("WEBVTT"):
            continue
        # SRT index numbers: 1, 2, 3, ...
        if re.fullmatch(r"\d{1,4}", line):
            continue
        # SRT timestamp axis: 00:00:02,940 --> 00:00:03,580  (plus optional
        # aligned-text / position settings appended on the same line).
        if _SRT_TIMELINE.search(line):
            continue
        out.append(line)
    return " ".join(out).strip()


def _extract_subtitle(path: Path, max_chars: int) -> Tuple[str, str]:
    """Read an SRT/VTT file and return only its dialogue text.

    The header, index numbers and timestamp lines are stripped before the
    result is returned, so the broadcast center summarizes *what the video
    says* instead of a wall of ``-->`` metadata. Encoding is sniffed the
    same way plain text is, and only *max_chars* characters are read.
    """
    try:
        with path.open("rb") as f:
            sample = f.read(_ENCODING_SAMPLE_BYTES)
        enc = _sniff_encoding(sample)
        with path.open("r", encoding=enc, errors="replace", newline="") as f:
            text = f.read(max_chars)
    except OSError:
        return "", "failed"
    return strip_subtitle(text), "text"


# ---------------------------------------------------------------------------
# docx / pptx / xlsx (OOXML family: ZIP + XML)
# ---------------------------------------------------------------------------


def _zip_xml(zf: zipfile.ZipFile, name: str) -> Optional[bytes]:
    """Read a member from *zf*; return None when absent or unreadable."""
    try:
        return zf.read(name)
    except (KeyError, zipfile.BadZipFile, OSError):
        return None


def _extract_docx(path: Path, max_chars: int) -> Tuple[str, str]:
    """Extract paragraph text from ``word/document.xml``."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as zf:
        xml = _zip_xml(zf, "word/document.xml")
    if xml is None:
        return "", "failed"
    root = ET.fromstring(xml)
    paras: List[str] = []
    total = 0
    for para in root.iter(f"{_W_NS}p"):
        buf = "".join(t.text or "" for t in para.iter(f"{_W_NS}t"))
        if buf:
            paras.append(buf)
            total += len(buf)
            if total >= max_chars:
                break
    return "\n".join(paras)[:max_chars], "docx"


def _extract_pptx(path: Path, max_chars: int) -> Tuple[str, str]:
    """Extract text from every slide, in slide-number order."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        names.sort(key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
        chunks: List[str] = []
        total = 0
        for name in names:
            xml = _zip_xml(zf, name)
            if xml is None:
                continue
            try:
                root = ET.fromstring(xml)
            except ET.ParseError:
                continue
            buf = " ".join(t.text or "" for t in root.iter(f"{_A_NS}t"))
            if buf:
                chunks.append(buf)
                total += len(buf)
                if total >= max_chars:
                    break
    if not chunks:
        return "", "failed"
    return "\n".join(chunks)[:max_chars], "pptx"


def _extract_xlsx(path: Path, max_chars: int) -> Tuple[str, str]:
    """Extract cell text from a workbook.

    ``openpyxl`` (already an optional dependency of this project) is used
    when available; on *any* failure (not installed, corrupt archive,
    minimal hand-made file) the shared-strings + sheet XML path runs on
    the standard library alone, so a broken workbook degrades instead of
    killing the whole index.
    """
    try:
        return _extract_xlsx_openpyxl(path, max_chars)
    except Exception:  # noqa: BLE001 - any openpyxl failure -> stdlib path
        return _extract_xlsx_stdlib(path, max_chars)


def _extract_xlsx_openpyxl(path: Path, max_chars: int) -> Tuple[str, str]:
    from openpyxl import load_workbook  # type: ignore

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        chunks: List[str] = []
        total = 0
        for ws in wb.worksheets:
            row_texts: List[str] = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None and str(c).strip()]
                if cells:
                    row_texts.append(" ".join(cells))
                    total += len(row_texts[-1])
                    if total >= max_chars:
                        break
            if row_texts:
                chunks.append(f"[{ws.title}] " + " | ".join(row_texts))
            if total >= max_chars:
                break
    finally:
        wb.close()
    if not chunks:
        return "", "failed"
    return "\n".join(chunks)[:max_chars], "xlsx-openpyxl"


def _extract_xlsx_stdlib(path: Path, max_chars: int) -> Tuple[str, str]:
    """Shared-strings based extraction (no third-party packages)."""
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as zf:
        shared: List[str] = []
        sst = _zip_xml(zf, "xl/sharedStrings.xml")
        if sst is not None:
            try:
                root = ET.fromstring(sst)
                for si in root:
                    shared.append("".join(t.text or "" for t in si.iter()))
            except ET.ParseError:
                shared = []
        sheets = sorted(
            n for n in zf.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)
        )
        chunks: List[str] = []
        total = 0
        for name in sheets:
            xml = _zip_xml(zf, name)
            if xml is None:
                continue
            try:
                root = ET.fromstring(xml)
            except ET.ParseError:
                continue
            row_texts: List[str] = []
            for row in root.iter():
                if not row.tag.endswith("}row"):
                    continue
                cells: List[str] = []
                for c in row:
                    if not c.tag.endswith("}c"):
                        continue
                    ctype = c.get("t")
                    v = next((x for x in c if x.tag.endswith("}v")), None)
                    if ctype == "s" and v is not None and v.text is not None:
                        try:
                            cells.append(shared[int(v.text)])
                        except (ValueError, IndexError):
                            pass
                    elif ctype == "inlineStr":
                        cells.append("".join(t.text or "" for t in c.iter()))
                    elif v is not None and v.text:
                        cells.append(v.text)
                line = " ".join(x for x in cells if x.strip())
                if line:
                    row_texts.append(line)
                    total += len(line)
                    if total >= max_chars:
                        break
            if row_texts:
                chunks.append(" | ".join(row_texts))
            if total >= max_chars:
                break
    if not chunks:
        return "", "failed"
    return "\n".join(chunks)[:max_chars], "xlsx"


# ---------------------------------------------------------------------------
# pdf
# ---------------------------------------------------------------------------


def _extract_pdf(path: Path, max_chars: int) -> Tuple[str, str]:
    """Tiered PDF extraction: library -> stdlib scan -> metadata only."""
    for method, fn in (
        ("pdf-pdfminer", _extract_pdf_pdfminer),
        ("pdf-pypdf2", _extract_pdf_pypdf2),
    ):
        try:
            text = fn(path, max_chars)
        except Exception:  # noqa: BLE001 - library missing or choked
            text = ""
        if text and text.strip():
            return text[:max_chars], method
    text = _extract_pdf_stdlib(path, max_chars)
    if text and text.strip():
        return text[:max_chars], "pdf-stdlib"
    return "", "pdf-metadata"


def _extract_pdf_pdfminer(path: Path, max_chars: int) -> str:
    from pdfminer.high_level import extract_text as pm_extract  # type: ignore

    return pm_extract(str(path), maxpages=50) or ""


def _extract_pdf_pypdf2(path: Path, max_chars: int) -> str:
    from PyPDF2 import PdfReader  # type: ignore

    reader = PdfReader(str(path))
    parts: List[str] = []
    for page in reader.pages[:50]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _extract_pdf_stdlib(path: Path, max_chars: int) -> str:
    """Best-effort stdlib PDF text extraction.

    Decompresses every Flate stream and collects the strings shown by text
    operators; uncompressed content streams are scanned as-is. Handles the
    common "text lives in a compressed content stream" case produced by
    Word/LaTeX/pandoc exporters; image-only or curve-drawn PDFs yield
    nothing (the caller then falls back to metadata-only). Only the first
    :data:`_PDF_STDLIB_MAX_BYTES` bytes are read, so a huge PDF cannot
    exhaust memory on this path.
    """
    try:
        with path.open("rb") as f:
            data = f.read(_PDF_STDLIB_MAX_BYTES)
    except OSError:
        return ""
    out: List[str] = []
    total = 0
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        raw = data[start:end]
        try:
            dec = zlib.decompress(raw)
        except zlib.error:
            dec = raw  # not Flate-compressed: scan the bytes as they are
        for sm in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj|\[[^\]]*\]\s*TJ", dec):
            chunk = _pdf_operator_strings(sm.group(0))
            if chunk:
                out.append(chunk)
                total += len(chunk)
                if total >= max_chars:
                    return " ".join(out)[:max_chars]
        if total >= max_chars:
            break
    return " ".join(out)[:max_chars]


def _pdf_operator_strings(operator_bytes: bytes) -> str:
    """Pull the literal strings out of a ``Tj`` / ``TJ`` operator."""
    parts: List[str] = []
    for sm in re.finditer(rb"\((?:\\.|[^\\()])*\)", operator_bytes):
        raw = sm.group(0)[1:-1]
        raw = re.sub(rb"\\([()\\])", rb"\1", raw)
        raw = raw.replace(rb"\n", b" ").replace(rb"\r", b" ").replace(rb"\t", b" ")
        try:
            parts.append(raw.decode("latin-1"))
        except Exception:  # noqa: BLE001 - undecodable byte, skip it
            continue
    return "".join(parts).strip()


def pdf_page_count(path: Path) -> Optional[int]:
    """Crude page count from the ``/Type /Page`` objects (no library).

    Reads at most :data:`_PDF_STDLIB_MAX_BYTES` bytes; a page tree beyond
    that is not worth the memory. Returns None when nothing is countable.
    """
    try:
        with path.open("rb") as f:
            data = f.read(_PDF_STDLIB_MAX_BYTES)
    except OSError:
        return None
    n = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))
    return n or None


def json_summary_of(path: Path, max_chars: int = MAX_EXTRACT_CHARS) -> Tuple[str, str]:
    """Flatten a JSON document into a single readable string.

    Kept public because it is also useful as a *hint* for summarization of
    any JSON-ish sidecar file.
    """
    text, _ = _extract_plain(path, max_chars)
    if not text:
        return "", "failed"
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text, "text"
    return json.dumps(obj, ensure_ascii=False)[:max_chars], "json"
