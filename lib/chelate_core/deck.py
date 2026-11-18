"""deck-exporter's engine — Markdown reports into one self-contained HTML deck.

Caller: skills/deck-exporter/run.py.

Data schemas:
    Reads:  <workspace>/process/*.md (slides split on `## `), and the images
            they reference under process/.
    Writes: <workspace>/process/deck/<name>.html (+ a JSON report beside it).

Design — the export rule that matters is what does **not** end up inside:

    **No absolute paths.** A deck is the file people mail to a co-author, and
    an absolute path in it leaks the author's directory layout — in this
    project it can also name the workspace root, which is the one thing every
    other layer spends its time keeping out of a deliverable. The renderer
    never writes one, and `leaks()` re-reads the produced HTML looking for the
    shapes anyway (a Windows drive, a UNC prefix, file://, /home/ or /Users/).
    A deck that contains one is refused, not sanitised: a sanitiser that
    half-works is worse than a refusal, because the file has been mailed by
    the time anyone notices.

    **No network references.** Images are base64 data URIs, CSS is inline,
    there is no <script>. A deck that needs a CDN renders wrong on a plane and
    leaks a request when it does not.

    **A missing image degrades the slide, not the run.** An image that is
    absent, remote or too large becomes its alt text and is counted in the
    report, so the deck still opens and the report still says what was left
    out.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
from typing import Any, Dict, List

DECK_DIR = os.path.join("process", "deck")
MAX_IMAGE = 2 * 1024 * 1024
_SLIDE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# `--name` is caller-controlled and ends up in two file names. A check for
# "/" and "\\" alone is not enough on Windows: join() hands back
# "C:deck.html" unchanged (a drive-relative path), so the file lands beside
# whatever directory that drive is currently on. Accept plain characters
# only, then assert the resolved path still sits under the deck directory.
_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_LEAKS = (
    (re.compile(r"\b[A-Za-z]:[\\/][^\s\"'<>]*"), "windows absolute path"),
    (re.compile(r"\\\\[A-Za-z0-9_.$-]+[\\/][^\s\"'<>]*"), "UNC path"),
    (re.compile(r"file://[^\s\"'<>]*"), "file:// URL"),
    (re.compile(r"(?<![\w.-])/(?:Users|home)/[^\s\"'<>]+"), "posix home path"),
)
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}

_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ margin: 0; font: 20px/1.5 system-ui, sans-serif; background: #111; }}
  section {{ box-sizing: border-box; width: 100%; min-height: 100vh;
             padding: 6vh 8vw; background: #fff; page-break-after: always; }}
  section.title {{ display: flex; flex-direction: column;
                   justify-content: center; background: #0b1a2b; color: #fff; }}
  h2 {{ font-size: 2.2em; margin: 0 0 .6em; }}
  img {{ max-width: 100%; max-height: 60vh; display: block; margin: 1em 0; }}
  ul {{ padding-left: 1.2em; }}
</style>
</head>
<body>
{slides}
</body>
</html>
"""


class DeckError(ValueError):
    """The deck cannot be built from what is in process/."""


class DeckLeak(DeckError):
    """The deck would embed an absolute path, so it is not exportable."""


def sources(root: str) -> List[str]:
    """The Markdown reports, in a stable order (they are numbered by habit)."""
    folder = os.path.join(root, "process")
    if not os.path.isdir(folder):
        raise DeckError(f"no process/ directory under {os.path.basename(root)}")
    found = sorted(name for name in os.listdir(folder)
                   if name.lower().endswith(".md")
                   and os.path.isfile(os.path.join(folder, name)))
    if not found:
        raise DeckError("no Markdown reports in process/ to export")
    return [os.path.join(folder, name) for name in found]


def split(markdown_text: str, title: str) -> List[Dict[str, Any]]:
    """The first `# ` heading is the title slide; every `## ` starts a slide."""
    text = markdown_text.replace("\r\n", "\n")
    first = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    heading = first.group(1).strip() if first else title
    parts = _SLIDE.split(text)  # [preamble, h1, body1, h2, body2, ...]
    intro = parts[0] if parts else ""
    if first:
        # Everything between the title and the first `## ` belongs to the
        # title slide. Dropping it would silently lose the abstract — and,
        # worse, any absolute path that lived there would escape `leaks()`.
        intro = intro[first.end():].lstrip("\n")
    slides = [{"title": heading, "body": intro, "kind": "title"}]
    for index in range(1, len(parts), 2):
        slides.append({"title": parts[index].strip(),
                       "body": parts[index + 1] if index + 1 < len(parts) else "",
                       "kind": "slide"})
    return slides


def _image_tag(match, base: str, inlined: List[Dict[str, Any]],
               skipped: List[Dict[str, str]]) -> str:
    """An image becomes a data URI, or its alt text and a reported reason."""
    alt, target = match.group(1), match.group(2).strip()
    fallback = f"<em>{html.escape(alt or 'image')}</em>"
    if target.startswith(("http://", "https://")):
        skipped.append({"image": target, "reason": "remote URL"})
        return fallback
    path = target if os.path.isabs(target) else \
        os.path.join(base, *target.split("/"))
    ext = os.path.splitext(path)[1].lower()
    if not os.path.isfile(path):
        skipped.append({"image": target, "reason": "missing"})
        return fallback
    size = os.path.getsize(path)
    if size > MAX_IMAGE:
        skipped.append({"image": target, "reason": f"{size} bytes > limit"})
        return fallback
    if ext not in _MIME:
        skipped.append({"image": target, "reason": f"unsupported {ext}"})
        return fallback
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode("ascii")
    inlined.append({"image": target, "bytes": size})
    return f'<img alt="{html.escape(alt)}" src="data:{_MIME[ext]};base64,{data}">'


def _body_html(source: str, base: str, inlined: List[Dict[str, Any]],
               skipped: List[Dict[str, str]]) -> str:
    """Images are stashed first: html.escape would turn our tag into text."""
    placeholders: List[str] = []

    def stash(match):
        placeholders.append(_image_tag(match, base, inlined, skipped))
        return f"\x01{len(placeholders) - 1}\x01"

    text = html.escape(_IMAGE.sub(stash, source), quote=False)
    for index, tag in enumerate(placeholders):
        text = text.replace(f"\x01{index}\x01", tag)

    rendered = []
    for chunk in re.split(r"\n\s*\n", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = [line for line in chunk.splitlines() if line.strip()]
        if all(line.lstrip().startswith(("- ", "* ")) for line in lines):
            rendered.append("<ul>" + "".join(
                f"<li>{line.lstrip()[2:]}</li>" for line in lines) + "</ul>")
        elif chunk.startswith("<img "):
            rendered.append(chunk)
        else:
            rendered.append(f"<p>{' '.join(lines)}</p>")
    return "".join(rendered)


def render(markdown_text: str, title: str, base: str,
           inlined: List[Dict[str, Any]],
           skipped: List[Dict[str, str]]) -> str:
    """One report as a deck: every slide a section, nothing else."""
    slides = split(markdown_text, title)
    sections = [
        f'<section class="{slide["kind"]}">'
        f"<h2>{html.escape(slide['title'])}</h2>"
        + _body_html(slide["body"], base, inlined, skipped) + "</section>"
        for slide in slides]
    return _SHELL.format(title=html.escape(slides[0]["title"]),
                         slides="\n".join(sections))


def leaks(text: str) -> List[Dict[str, str]]:
    """Absolute-path shapes in a rendered deck. Empty means exportable."""
    found = []
    for pattern, label in _LEAKS:
        for match in pattern.findall(text):
            found.append({"kind": label, "text": str(match)[:120]})
    return found


def _inside(base: str, target: str) -> bool:
    """True when `target` resolves to a file under `base`."""
    root = os.path.realpath(base)
    try:
        return os.path.commonpath([root, os.path.realpath(target)]) == root
    except ValueError:      # different drives on Windows
        return False


def build(root: str, name: str = "deck") -> Dict[str, Any]:
    """Render every report into one deck and refuse an absolute-path leak."""
    name = str(name or "deck")
    if not _NAME.match(name) or name in {".", ".."}:
        raise DeckError(f"{name!r} is not a plain deck name (letters, digits, "
                        f"dot, dash and underscore, at most 64)")
    files = sources(root)
    inlined: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    pages = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            document = render(fh.read(), os.path.basename(path),
                              os.path.dirname(path), inlined, skipped)
        pages.append(document.split("<body>", 1)[1].rsplit("</body>", 1)[0])
    deck = _SHELL.format(title=html.escape(os.path.basename(files[0])),
                         slides="\n".join(pages))

    found = leaks(deck)
    if found:
        raise DeckLeak(
            f"the deck would embed {found[0]['kind']} ({found[0]['text']}); "
            f"rewrite that line as a relative path before exporting")

    out_dir = os.path.join(root, DECK_DIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{name}.html")
    if not _inside(out_dir, out_path):
        raise DeckError(f"{name!r} resolves outside {DECK_DIR}")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(deck)
    report = {"path": out_path,
              "sources": [os.path.basename(path) for path in files],
              "bytes": os.path.getsize(out_path),
              "slides": deck.count("<section"),
              "images_inlined": inlined, "images_skipped": skipped}
    report_path = os.path.join(out_dir, f"{name}.json")
    if not _inside(out_dir, report_path):
        raise DeckError(f"{name!r} resolves outside {DECK_DIR}")
    with open(report_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, indent=2))
    return report
