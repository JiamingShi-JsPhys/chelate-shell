"""deck-exporter: one file that travels without the workspace in it."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from conftest import REPO_ROOT, run_path_of
from lib.chelate_core import deck


def _report(tmp_path, name, text):
    path = tmp_path / "process" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_slides_are_the_title_plus_every_second_level_heading(tmp_path):
    _report(tmp_path, "01_report.md",
            "# Results\n\nintro\n\n## Method\n\nwe measured\n\n"
            "## Findings\n\n- one\n- two\n")
    report = deck.build(str(tmp_path), "deck")
    assert report["slides"] == 3
    html = open(report["path"], encoding="utf-8").read()
    assert "<h2>Results</h2>" in html
    assert "<h2>Findings</h2>" in html
    assert "<li>one</li>" in html


def test_an_image_is_inlined_as_a_data_uri(tmp_path):
    _report(tmp_path, "01_report.md", "# T\n\n## Fig\n\n![](figures/p.png)\n")
    image = tmp_path / "process" / "figures" / "p.png"  # relative to the .md
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    report = deck.build(str(tmp_path), "deck")
    html = open(report["path"], encoding="utf-8").read()
    assert "data:image/png;base64," in html
    assert report["images_inlined"][0]["image"].endswith("p.png")


def test_a_missing_image_degrades_the_slide_not_the_run(tmp_path):
    _report(tmp_path, "01_report.md", "# T\n\n## Fig\n\n![plot](figures/no.png)\n")
    report = deck.build(str(tmp_path), "deck")
    html = open(report["path"], encoding="utf-8").read()
    assert "<em>plot</em>" in html
    assert report["images_skipped"][0]["reason"] == "missing"


def test_a_remote_image_is_never_referenced(tmp_path):
    _report(tmp_path, "01_report.md",
            "# T\n\n## Fig\n\n![x](https://example.com/a.png)\n")
    report = deck.build(str(tmp_path), "deck")
    html = open(report["path"], encoding="utf-8").read()
    assert "example.com" not in html
    assert report["images_skipped"][0]["reason"] == "remote URL"


def test_an_absolute_path_refuses_the_export(tmp_path):
    """The one rule worth refusing over: the file has been mailed already."""
    _report(tmp_path, "01_report.md",
            "# T\n\n## Data\n\nsee C:\\Users\\someone\\data.csv\n")
    with pytest.raises(deck.DeckLeak) as exc:
        deck.build(str(tmp_path), "deck")
    assert "windows absolute path" in str(exc.value)
    assert not (tmp_path / "process" / "deck" / "deck.html").exists()


def test_a_posix_home_path_is_caught_too(tmp_path):
    _report(tmp_path, "01_report.md", "# T\n\n## Data\n\n/home/me/x.csv\n")
    with pytest.raises(deck.DeckLeak):
        deck.build(str(tmp_path), "deck")


def test_a_drive_relative_deck_name_is_refused(tmp_path):
    """`--name C:deck` made join() drop process/deck on Windows."""
    _report(tmp_path, "01_report.md", "# T\n\n## S\n\nplain text\n")
    for name in ("C:deck", "../deck", "a/b", ".."):
        with pytest.raises(deck.DeckError):
            deck.build(str(tmp_path), name)
    assert not (tmp_path / "process" / "deck").exists()


def test_the_deck_has_no_script_and_no_http(tmp_path):
    _report(tmp_path, "01_report.md", "# T\n\n## S\n\nplain text\n")
    report = deck.build(str(tmp_path), "deck")
    html = open(report["path"], encoding="utf-8").read()
    assert "<script" not in html
    assert "http://" not in html and "https://" not in html


def test_no_markdown_is_a_refusal_to_export(tmp_path):
    (tmp_path / "process").mkdir()
    with pytest.raises(deck.DeckError) as exc:
        deck.build(str(tmp_path), "deck")
    assert "no Markdown" in str(exc.value)


def test_the_report_beside_the_deck_names_what_was_left_out(tmp_path):
    _report(tmp_path, "01_report.md", "# T\n\n## F\n\n![a](nope.png)\n")
    report = deck.build(str(tmp_path), "deck")
    saved = json.load(open(report["path"].replace(".html", ".json"),
                           encoding="utf-8"))
    assert saved["images_skipped"][0]["image"] == "nope.png"


# --------------------------------------------------------------------------
# the adapter
# --------------------------------------------------------------------------

def _run_adapter(workspace, *extra):
    proc = subprocess.run(
        [sys.executable, str(run_path_of("deck-exporter")),
         "--root", str(workspace), *extra],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120)
    lines = [line for line in proc.stdout.strip().splitlines() if line.strip()]
    assert lines, proc.stdout + proc.stderr
    return json.loads(lines[-1])


def test_the_adapter_passes_and_writes_the_deck(workspace):
    _report(workspace, "01_report.md", "# T\n\n## S\n\ntext\n")
    payload = _run_adapter(workspace, "--name", "talk")
    assert payload["status"] == "PASS"
    assert (workspace / "process" / "deck" / "talk.html").is_file()
    # The stdout contract carries gate/status/reason only; the counts live in
    # the report written beside the deck.
    saved = json.loads((workspace / "process" / "deck" / "talk.json")
                       .read_text(encoding="utf-8"))
    assert saved["slides"] == 2


def test_the_adapter_fails_on_a_leak(workspace):
    _report(workspace, "01_report.md", "# T\n\nD:\\data\\x.csv\n")
    payload = _run_adapter(workspace)
    assert payload["status"] == "FAIL"
    assert "absolute path" in payload["reason"]


def test_the_adapter_degrades_without_reports(workspace):
    payload = _run_adapter(workspace)
    assert payload["status"] == "UNVERIFIED"
    assert "nothing to export" in payload["reason"]
