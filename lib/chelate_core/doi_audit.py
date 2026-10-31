"""DOI extraction and Crossref verification core.

DOI syntax (Crossref): 10.NNNN/suffix, captured with a conservative regex
that stops at whitespace and closing delimiters. Verification is a plain
GET against the Crossref REST API with a politeness mailto parameter:
  HTTP 200 -> valid, HTTP 404 -> invalid (fabricated reference),
  anything else (or a transport error) -> indeterminate.

The caller decides the gate: any invalid DOI is a FAIL; indeterminate
without a single valid DOI is UNVERIFIED.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

CROSSREF_ENDPOINT = "https://api.crossref.org/works/"
CONTACT_MAILTO = "chelate-shell@example.invalid"  # Crossref politeness param
USER_AGENT = "chelate-shell/1.2.0"

# 10.NNNN/suffix — NNNN is 4-9 digits; suffix runs until whitespace or a
# closing delimiter commonly following a DOI in prose/bib entries.
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'\]\)\},;]+")


def extract_dois(text: str) -> List[str]:
    """Return DOIs in first-seen order, stripped of trailing punctuation."""
    seen, out = set(), []
    for raw in _DOI_RE.findall(text or ""):
        doi = raw.rstrip(".,;:")
        if doi and doi not in seen:
            seen.add(doi)
            out.append(doi)
    return out


def verify_doi(doi: str, timeout: int = 20) -> Dict:
    """Query Crossref for one DOI; return a per-DOI verdict dict."""
    import requests

    record = {"doi": doi, "status": "unknown", "title": None,
              "container": None, "year": None, "http_status": None}
    try:
        resp = requests.get(CROSSREF_ENDPOINT + requests.utils.quote(doi),
                            params={"mailto": CONTACT_MAILTO},
                            timeout=timeout,
                            headers={"User-Agent":
                                     f"{USER_AGENT} (mailto:{CONTACT_MAILTO})"})
    except Exception as exc:
        record["status"] = "indeterminate"
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record
    record["http_status"] = resp.status_code
    if resp.status_code == 200:
        try:
            msg = resp.json().get("message", {})
            record["status"] = "valid"
            record["title"] = (msg.get("title") or [None])[0]
            record["container"] = (msg.get("container-title") or [None])[0]
            issued = (msg.get("issued", {}).get("date-parts") or [[None]])[0]
            record["year"] = issued[0] if issued else None
        except Exception:
            record["status"] = "indeterminate"
            record["error"] = "malformed Crossref payload"
    elif resp.status_code == 404:
        record["status"] = "invalid"
    else:
        record["status"] = "indeterminate"
        record["error"] = f"HTTP {resp.status_code}"
    return record


def read_draft(input_path: Optional[str], text: Optional[str]):
    """Resolve draft text from --input or --text; raise ValueError on misuse."""
    from pathlib import Path
    if input_path:
        src = Path(input_path)
        if not src.is_file():
            raise FileNotFoundError(f"draft not found: {src}")
        return src.read_text(encoding="utf-8", errors="replace"), str(src)
    if text:
        return text, "<inline>"
    raise ValueError("nothing to audit: pass --input or --text")


def audit(text: str, source: str, timeout: int = 20,
          details_dir: Optional[str] = None) -> Dict:
    """Run the full audit of `text` and return the gate verdict payload.

    Returns {status, evidence_level, reason, records, details_path} where
    status is PASS / FAIL / UNVERIFIED per the gate contract:
      FAIL        at least one DOI returned HTTP 404 (names the offenders)
      UNVERIFIED network failure for every DOI (or nothing valid at all)
      PASS        every DOI resolves (indeterminate ones are reported, not
                  counted as failures)
    When `details_dir` is given, the per-DOI records are written there as
    reference_audit_<stamp>.json and its path is returned as details_path.
    """
    dois = extract_dois(text)
    records = [verify_doi(d, timeout=timeout) for d in dois]
    invalid = [r for r in records if r["status"] == "invalid"]
    indeterminate = [r for r in records if r["status"] == "indeterminate"]
    valid = [r for r in records if r["status"] == "valid"]

    details_path = None
    if details_dir:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        os.makedirs(details_dir, exist_ok=True)
        details_path = os.path.join(details_dir,
                                    f"reference_audit_{stamp}.json")
        with open(details_path, "w", encoding="utf-8") as f:
            json.dump({"source": source, "checked_at": stamp,
                       "total": len(records), "valid": len(valid),
                       "invalid": len(invalid),
                       "indeterminate": len(indeterminate),
                       "records": records}, f, ensure_ascii=False, indent=2)

    if invalid:
        names = ", ".join(r["doi"] for r in invalid[:5])
        return {"status": "FAIL", "evidence_level": "EXACT",
                "reason": (f"{len(invalid)} of {len(records)} DOIs do not "
                           f"exist in Crossref: {names}"),
                "records": records, "details_path": details_path}
    if indeterminate and not valid:
        first = indeterminate[0]
        return {"status": "UNVERIFIED", "evidence_level": "UNVERIFIED",
                "reason": (f"Crossref unreachable for all {len(records)} "
                           f"DOIs (e.g. {first.get('error', 'unknown')}); "
                           f"verification inconclusive"),
                "records": records, "details_path": details_path}
    reason = f"all {len(valid)} DOIs resolve in Crossref"
    if indeterminate:
        reason += (f"; {len(indeterminate)} indeterminate "
                   f"(network errors, not counted as failures)")
    return {"status": "PASS", "evidence_level": "EXACT", "reason": reason,
            "records": records, "details_path": details_path}
