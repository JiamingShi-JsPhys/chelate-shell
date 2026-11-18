"""Crossref / PubMed / DOI records for the literature-retriever skill.

Caller: skills/literature-retriever/run.py (`--source crossref|pubmed|doi`).
Data schemas:
    Reads:  Crossref works + DOI endpoints, NCBI eutils.
    Writes: nothing; returns records in the same shape arXiv produces:
            {title, summary, authors, published, updated, entry_id, pdf_url,
             categories, doi, journal_ref, source}
Design: pure standard library (urllib + ElementTree + json), so a machine
        without the `arxiv` SDK can still search the two most useful
        bibliographic databases.

Three details are deliberate, because the naive version of each is wrong in
a way that only shows up in the data:

* **Dates are normalised to one format.** Crossref says ``2025``, PubMed says
  ``2024 Jan``, Crossref sometimes says ``[[null]]``. All three become
  ``YYYY[-MM[-DD]]`` or ``""`` — never the string ``"None"``, which is what a
  straight ``str(part)`` produces and what then travels into a bibliography.
* **Crossref's non-literature record types are dropped.** A query otherwise
  returns a figure caption (``component``), a supplementary .docx, or a
  subject-heading entry (``dataset``) among its first hits; none of them is a
  paper, and the first of them can fill an entire ``limit``-sized request.
* **A DOI that is not registered is not a network failure.** Crossref answers
  404 for an unknown DOI, and that is reported as "not found", not as
  "check your connection".
"""
from __future__ import annotations

import html as html_lib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

DEFAULT_TIMEOUT = 20.0
# PubMed's efetch is the one XML endpoint here. ElementTree does not resolve
# external entities, but it will happily expand internal ones (billion
# laughs), so a document carrying a DTD is refused outright and the body is
# capped before it reaches the parser. NCBI never sends either.
_MAX_XML_BYTES = 8 * 1024 * 1024
USER_AGENT = ("ChelateShell literature-retriever "
              "(+https://github.com/JiamingShi-JsPhys/chelate-shell)")

_CROSSREF_SEARCH = (
    "https://api.crossref.org/works?query.bibliographic={query}&rows={limit}"
    # Ask for literature only. Without this, a phrase like "twisted bilayer
    # graphene" comes back 18/20 as `component` records that merely repeat
    # article titles; the client-side filter below is the second line.
    "&filter=type:journal-article,type:book-chapter,type:proceedings-article,"
    "type:posted-content,type:dissertation,type:report"
    "&select=DOI,title,author,container-title,issued,published-print,"
    "published-online,abstract,URL,type,subject,volume,issue,page"
)
_CROSSREF_DOI = "https://api.crossref.org/works/{doi}"
# A DOI goes into a URL *path*, and `quote(..., safe="/")` deliberately
# leaves "." and "/" alone — so `../../x` would be quoted into a path that
# walks out of /works/. The shape check is the defence: every DOI begins
# "10." and then the registrant's four-to-nine digits, a slash, and a suffix
# with no whitespace. Anything else is not a DOI and is refused before a
# request is built.
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_PUBMED_SEARCH = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    "?db=pubmed&term={query}&retmode=json&retmax={limit}&sort=relevance"
)
_PUBMED_SUMMARY = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    "?db=pubmed&id={ids}&retmode=json"
)
_PUBMED_FETCH = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    "?db=pubmed&id={ids}&retmode=xml"
)

_MONTHS = {name: index for index, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}


class ScholarError(RuntimeError):
    """The query could not be made or its answer could not be understood."""


class NotFound(ScholarError):
    """The DOI is not registered — a 404, not a network problem."""


# -- transport -----------------------------------------------------------

# Every URL this module builds is a format string over one of these two
# hosts. The check below is what makes that true at the point a socket is
# opened rather than only in the five places the strings are written: a
# caller that later hands `_get` a URL assembled somewhere else is refused
# instead of fetched.
_SOURCE_HOSTS = frozenset({"api.crossref.org", "eutils.ncbi.nlm.nih.gov"})


def _get(url: str, opener=None, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in _SOURCE_HOSTS:
        raise ScholarError(
            f"refusing to fetch {parts.netloc or url!r}: not a literature "
            f"source host")
    try:
        if opener is not None:
            return opener(url)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound(f"not registered: {url}") from exc
        raise ScholarError(f"HTTP {exc.code} for {url}") from exc
    except ScholarError:
        raise
    except Exception as exc:  # URLError, timeout, TLS
        raise ScholarError(f"{exc.__class__.__name__}: {exc}") from exc


def _json(url: str, opener=None) -> Any:
    raw = _get(url, opener)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ScholarError(f"invalid JSON from {url}: {exc}") from exc


# -- normalisation -------------------------------------------------------

def normalise_date(value: Any) -> str:
    """One date format for every source: ``YYYY[-MM[-DD]]`` or ``""``."""
    if value is None:
        return ""
    if isinstance(value, dict):  # Crossref {"date-parts": [[2025, 3, 14]]}
        parts = (value.get("date-parts") or [[]])[0] or []
        numbers = [int(part) for part in parts[:3]
                   if isinstance(part, int) or str(part).isdigit()]
        if not numbers:
            return ""
        year = numbers[0]
        month = f"-{numbers[1]:02d}" if len(numbers) > 1 and 1 <= numbers[1] <= 12 else ""
        day = f"-{numbers[2]:02d}" if len(numbers) > 2 and month and 1 <= numbers[2] <= 31 else ""
        return f"{year}{month}{day}"

    text = str(value).strip()
    match = re.match(
        r"^(\d{4})(?:[-/.\s]+(\d{1,2}|[A-Za-z]{3,}))?(?:[-/.\s]+(\d{1,2}))?",
        text)
    if not match:
        return ""
    year, month_token, day_token = match.group(1), match.group(2), match.group(3)
    if not month_token:
        return year
    month = (int(month_token) if month_token.isdigit()
             else _MONTHS.get(month_token[:3].lower(), 0))
    if not 1 <= month <= 12:
        return year
    if day_token and 1 <= int(day_token) <= 31:
        return f"{year}-{month:02d}-{int(day_token):02d}"
    return f"{year}-{month:02d}"


def _clean(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _first(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return "" if value is None else str(value)


def crossref_record(item: Dict[str, Any], source: str = "crossref") -> Dict[str, Any]:
    authors: List[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = author.get("name") or " ".join(
            part for part in (author.get("given"), author.get("family")) if part)
        if name:
            authors.append(name)
    published = (normalise_date(item.get("published-print"))
                 or normalise_date(item.get("published-online"))
                 or normalise_date(item.get("issued")))
    doi = str(item.get("DOI") or "")
    return {
        "title": _clean(_first(item.get("title"))),
        "summary": _clean(item.get("abstract")),
        "authors": authors,
        "published": published,
        "updated": "",
        "entry_id": str(item.get("URL") or (f"https://doi.org/{doi}" if doi else "")),
        "pdf_url": "",
        "categories": [str(topic) for topic in item.get("subject") or []],
        "doi": doi,
        "journal_ref": _clean(_first(item.get("container-title"))),
        "volume": str(item.get("volume") or ""),
        "issue": str(item.get("issue") or ""),
        "pages": str(item.get("page") or ""),
        "type": str(item.get("type") or ""),
        "source": source,
    }


def _pubmed_abstracts(xml_bytes: bytes) -> Dict[str, str]:
    if len(xml_bytes) > _MAX_XML_BYTES:
        raise ScholarError(f"efetch response too large ({len(xml_bytes)} bytes)")
    head = xml_bytes[:4096].lstrip()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ScholarError("refusing an XML document that declares entities")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    abstracts: Dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""
        chunks = [_clean(node.text)
                  for node in article.findall(".//Abstract/AbstractText")
                  if node.text]
        if pmid and chunks:
            abstracts[pmid] = " ".join(chunk for chunk in chunks if chunk)
    return abstracts


def pubmed_record(item: Dict[str, Any], uid: str,
                  abstracts: Dict[str, str]) -> Dict[str, Any]:
    doi = ""
    for article_id in item.get("articleids") or []:
        if article_id.get("idtype") == "doi":
            doi = str(article_id.get("value") or "")
            break
    return {
        "title": _clean(item.get("title")),
        "summary": abstracts.get(uid, ""),
        "authors": [str(author.get("name"))
                    for author in item.get("authors") or []
                    if author.get("name")],
        "published": normalise_date(item.get("pubdate")),
        "updated": "",
        "entry_id": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
        "pdf_url": "",
        "categories": [],
        "doi": doi,
        "journal_ref": str(item.get("fulljournalname")
                           or item.get("source") or ""),
        "volume": str(item.get("volume") or ""),
        "issue": str(item.get("issue") or ""),
        "pages": str(item.get("pages") or ""),
        "type": "journal-article",
        "source": "pubmed",
    }


# -- queries -------------------------------------------------------------

_CROSSREF_NOISE = {
    "component", "dataset", "standard", "reference-entry", "peer-review",
    "grant", "database-placeholder",
}


def search_crossref(query: str, limit: int = 10,
                    opener=None) -> List[Dict[str, Any]]:
    limit = max(1, min(limit, 50))
    # Ask for more than asked: Crossref mixes non-literature record types
    # (figure captions, subject headings) into ordinary result sets, and
    # filtering after a request sized to `limit` leaves fewer rows than the
    # caller asked for — sometimes none at all, which reads as "no literature".
    rows = min(max(limit * 4, 20), 100)
    url = _CROSSREF_SEARCH.format(query=urllib.parse.quote_plus(query),
                                  limit=rows)
    payload = _json(url, opener)
    items = ((payload or {}).get("message") or {}).get("items") or []
    records = [crossref_record(item) for item in items
               if str(item.get("type") or "").lower() not in _CROSSREF_NOISE]
    return records[:limit]


def resolve_doi(doi: str, opener=None) -> List[Dict[str, Any]]:
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi.strip(),
                 flags=re.IGNORECASE)
    if not _DOI.match(doi) or ".." in doi:
        raise NotFound(f"not a DOI: {doi!r}")
    url = _CROSSREF_DOI.format(doi=urllib.parse.quote(doi, safe="/"))
    payload = _json(url, opener)
    message = (payload or {}).get("message") or {}
    if not message.get("DOI"):
        raise NotFound(f"not registered: {doi}")
    return [crossref_record(message, source="doi")]


def search_pubmed(query: str, limit: int = 10,
                  opener=None) -> List[Dict[str, Any]]:
    limit = max(1, min(limit, 50))
    found = _json(_PUBMED_SEARCH.format(
        query=urllib.parse.quote_plus(query), limit=limit), opener)
    ids = (((found or {}).get("esearchresult") or {}).get("idlist") or [])[:limit]
    if not ids:
        return []
    joined = ",".join(ids)
    summary = _json(_PUBMED_SUMMARY.format(ids=joined), opener)
    result = (summary or {}).get("result") or {}
    try:
        abstracts = _pubmed_abstracts(_get(_PUBMED_FETCH.format(ids=joined),
                                           opener))
    except ScholarError:
        abstracts = {}
    return [pubmed_record(result.get(uid) or {}, uid, abstracts)
            for uid in ids]


def search(source: str, query: str, limit: int = 10, opener=None):
    """Dispatch by source; returns records in the arXiv shape."""
    source = (source or "crossref").lower()
    if source == "crossref":
        return search_crossref(query, limit, opener)
    if source == "doi":
        return resolve_doi(query, opener)
    if source == "pubmed":
        return search_pubmed(query, limit, opener)
    raise ScholarError(f"unsupported source {source!r}")


# -- merging and citation ------------------------------------------------

def _key(record: Dict[str, Any]) -> str:
    doi = str(record.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    title = re.sub(r"[^a-z0-9]+", " ", str(record.get("title") or "").lower())
    return f"title:{title.strip()}"


def dedupe(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the first record per DOI, else per normalised title.

    First wins because the caller decides the source order; merging fields
    from a second record is how a wrong abstract ends up attached to a
    right DOI.
    """
    seen: set = set()
    kept: List[Dict[str, Any]] = []
    for record in records:
        key = _key(record)
        if key in seen:
            continue
        seen.add(key)
        kept.append(record)
    return kept


def _tex(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.replace("{", "").replace("}", "").replace("\\", "")


def bibtex_key(record: Dict[str, Any], used: Optional[set] = None) -> str:
    authors = record.get("authors") or []
    words = str(authors[0] if authors else "").split()
    surname = re.sub(r"[^A-Za-z]", "", words[-1]) if words else ""
    surname = surname or "anon"
    year = str(record.get("published") or "")[:4] or "nd"
    title_words = str(record.get("title") or "untitled").split() or ["untitled"]
    word = re.sub(r"[^A-Za-z]", "", title_words[0]) or "untitled"
    base = f"{surname.lower()}{year}{word.lower()}"
    key, suffix = base, 0
    while used is not None and key in used:
        suffix += 1
        key = f"{base}{chr(ord('a') + suffix - 1)}"
    if used is not None:
        used.add(key)
    return key


def to_bibtex(records: List[Dict[str, Any]]) -> str:
    """A .bib body; one entry per record, fields only when they exist."""
    used: set = set()
    entries: List[str] = []
    for record in records:
        fields = [("title", record.get("title")),
                  ("author", " and ".join(record.get("authors") or [])),
                  ("journal", record.get("journal_ref")),
                  ("year", str(record.get("published") or "")[:4]),
                  ("volume", record.get("volume")),
                  ("number", record.get("issue")),
                  ("pages", record.get("pages")),
                  ("doi", record.get("doi")),
                  ("url", record.get("entry_id"))]
        body = ",\n".join(f"  {name} = {{{_tex(value)}}}"
                          for name, value in fields if _tex(value))
        entries.append(f"@article{{{bibtex_key(record, used)},\n{body}\n}}")
    return "\n\n".join(entries) + ("\n" if entries else "")
