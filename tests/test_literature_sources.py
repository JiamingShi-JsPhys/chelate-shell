"""Crossref/PubMed/DOI retrieval: dates, components, dedupe and BibTeX.

No test here touches the network. Each query takes an `opener` callable so
the fixtures below stand in for the API, which keeps the parsing rules — the
part that was wrong in the version this replaces — under test on any machine.
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from lib.chelate_core import scholar_search as scholar


def _json_opener(payload):
    return lambda url: json.dumps(payload).encode("utf-8")


def _router_opener(table):
    """Serve a canned body per URL substring."""
    def opener(url):
        for needle, body in table.items():
            if needle in url:
                return body if isinstance(body, bytes) else json.dumps(body).encode()
        raise AssertionError(f"unexpected URL {url}")
    return opener


# -- dates ----------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ({"date-parts": [[2025, 3, 14]]}, "2025-03-14"),
    ({"date-parts": [[2025, 3]]}, "2025-03"),
    ({"date-parts": [[2025]]}, "2025"),
    ({"date-parts": [[None]]}, ""),
    ({"date-parts": [[]]}, ""),
    ("2024 Jan", "2024-01"),
    ("2024 Jan 5", "2024-01-05"),
    ("2024/01/01 00:00", "2024-01-01"),
    ("2025", "2025"),
    ("", ""),
    (None, ""),
    ("not a date", ""),
])
def test_dates_have_one_format_and_never_say_none(value, expected):
    assert scholar.normalise_date(value) == expected


# -- Crossref -------------------------------------------------------------

def test_crossref_record_reads_names_and_falls_back_on_the_title():
    record = scholar.crossref_record({
        "DOI": "10.1/x",
        "title": ["A <i>title</i>"],
        "author": [{"given": "Ada", "family": "Lovelace"},
                   {"name": "A Consortium"}],
        "container-title": ["Journal of Tests"],
        "issued": {"date-parts": [[2020, 2, 3]]},
        "subject": ["physics"],
        "type": "journal-article",
    })
    assert record["title"] == "A title"
    assert record["authors"] == ["Ada Lovelace", "A Consortium"]
    assert record["published"] == "2020-02-03"
    assert record["journal_ref"] == "Journal of Tests"
    assert record["doi"] == "10.1/x"
    assert record["source"] == "crossref"


def test_component_records_are_dropped():
    payload = {"message": {"items": [
        {"DOI": "10.1/fig", "type": "component", "title": ["Figure 1"]},
        {"DOI": "10.1/paper", "type": "journal-article", "title": ["Paper"]},
    ]}}
    records = scholar.search_crossref("q", 10, opener=_json_opener(payload))
    assert [record["doi"] for record in records] == ["10.1/paper"]


def test_doi_resolution_accepts_the_usual_prefixes():
    payload = {"message": {"DOI": "10.1038/nature14539", "title": ["Deep learning"]}}
    seen = []

    def opener(url):
        seen.append(url)
        return json.dumps(payload).encode()

    for query in ("10.1038/nature14539", "doi:10.1038/nature14539",
                  "https://doi.org/10.1038/nature14539"):
        records = scholar.resolve_doi(query, opener=opener)
        assert records[0]["doi"] == "10.1038/nature14539"
    assert all("10.1038/nature14539" in url for url in seen)


def test_a_value_that_is_not_a_doi_never_reaches_the_url():
    """`quote(..., safe="/")` leaves ".." alone, so the shape is the check."""
    seen = []

    def opener(url):
        seen.append(url)
        raise AssertionError(f"no request should be made: {url}")

    for bad in ("../../works", "10.1/x", "http://evil.example/x",
                "10.1038/../x", "10.1038/a b"):
        with pytest.raises(scholar.NotFound):
            scholar.resolve_doi(bad, opener=opener)
    assert not seen


def test_a_url_outside_the_source_hosts_is_never_fetched():
    """The five URL templates are the only sources; `_get` enforces it."""
    for url in ("http://127.0.0.1:8080/works", "https://evil.example/x",
                "http://api.crossref.org/works/10.1038/x"):
        with pytest.raises(scholar.ScholarError):
            scholar._get(url)


def test_an_unregistered_doi_is_not_found_not_a_network_error():
    def opener(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    with pytest.raises(scholar.NotFound):
        scholar.resolve_doi("10.9999/nope", opener=opener)


# -- PubMed ---------------------------------------------------------------

def test_pubmed_merges_summary_and_abstract():
    table = {
        "esearch": {"esearchresult": {"idlist": ["42"]}},
        "esummary": {"result": {"42": {
            "title": "A paper.",
            "authors": [{"name": "Fu Z"}],
            "pubdate": "2024 Jan 5",
            "fulljournalname": "Small methods",
            "articleids": [{"idtype": "doi", "value": "10.2/pm"}],
        }}},
        "efetch": (b"<PubmedArticleSet><PubmedArticle><MedlineCitation>"
                   b"<PMID>42</PMID><Article><Abstract>"
                   b"<AbstractText>First half.</AbstractText>"
                   b"<AbstractText>Second half.</AbstractText>"
                   b"</Abstract></Article></MedlineCitation></PubmedArticle>"
                   b"</PubmedArticleSet>"),
    }
    records = scholar.search_pubmed("q", 5, opener=_router_opener(table))
    assert records[0]["published"] == "2024-01-05"
    assert records[0]["summary"] == "First half. Second half."
    assert records[0]["journal_ref"] == "Small methods"
    assert records[0]["doi"] == "10.2/pm"


def test_xml_with_an_entity_declaration_is_refused():
    bomb = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]>'
            b"<PubmedArticleSet/>")
    with pytest.raises(scholar.ScholarError, match="entit"):
        scholar._pubmed_abstracts(bomb)


# -- merging --------------------------------------------------------------

def test_dedupe_keeps_the_first_record_per_doi_then_per_title():
    records = [
        {"doi": "10.1/a", "title": "First"},
        {"doi": "10.1/A", "title": "Duplicate DOI"},
        {"doi": "", "title": "Same  Title"},
        {"doi": "", "title": "same title"},
    ]
    assert [record["title"] for record in scholar.dedupe(records)] == [
        "First", "Same  Title"]


# -- BibTeX ---------------------------------------------------------------

def test_bibtex_carries_the_fields_that_exist_and_unique_keys():
    records = [
        {"title": "One", "authors": ["Ada Lovelace", "Alan Turing"],
         "published": "2020-02-03", "journal_ref": "J. Tests",
         "doi": "10.1/one", "entry_id": "https://doi.org/10.1/one"},
        {"title": "One", "authors": ["Ada Lovelace"],
         "published": "2020", "journal_ref": "", "doi": "", "entry_id": ""},
    ]
    body = scholar.to_bibtex(records)
    assert body.count("@article{") == 2
    assert "author = {Ada Lovelace and Alan Turing}" in body
    assert "year = {2020}" in body
    assert "journal = {J. Tests}" in body
    keys = [line.rstrip(",") for line in body.splitlines()
            if line.startswith("@article{")]
    assert len(set(keys)) == 2


def test_bibtex_escapes_braces_out_of_a_title():
    body = scholar.to_bibtex([{"title": "A {weird} title", "authors": ["X Y"]}])
    assert "{weird}" not in body.replace("title = {A weird title}", "")
    assert "title = {A weird title}" in body


def test_crossref_asks_for_more_rows_than_it_returns():
    """Components are filtered after the request, so the request must be wider."""
    seen = []

    def opener(url):
        seen.append(url)
        return json.dumps({"message": {"items": [
            {"DOI": "10.1/fig", "type": "component"}]}}).encode()

    assert scholar.search_crossref("q", 2, opener=opener) == []
    assert "rows=20" in seen[0]


def test_bibtex_key_survives_a_record_without_authors():
    body = scholar.to_bibtex([{"title": "", "authors": [],
                               "published": "", "doi": ""}])
    assert "@article{anon" in body


def test_subject_heading_datasets_are_dropped_too():
    payload = {"message": {"items": [
        {"DOI": "10.1/ph", "type": "dataset", "title": ["Twisted bilayer graphene"]},
        {"DOI": "10.1/p", "type": "journal-article", "title": ["Paper"]},
    ]}}
    records = scholar.search_crossref("q", 5, opener=_json_opener(payload))
    assert [record["doi"] for record in records] == ["10.1/p"]
