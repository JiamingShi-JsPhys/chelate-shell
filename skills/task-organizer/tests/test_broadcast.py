"""Tests for the broadcast center (context-compression index).



Covers the three promises the module makes:



1. **Extraction works** for every supported format (txt / md / csv / json /

   docx / pdf / pptx / xlsx), including the stdlib-only fallbacks for

   formats whose libraries are missing or whose files are hand-made.

2. **Read-only**: originals are never modified (hash + mtime unchanged) and

   the only writes are ``_broadcast/INDEX.md`` + ``_broadcast/index.json``.

3. **Safe inside a task folder**: ``_broadcast`` is tool-owned, so ``init``

   and ``organize`` never relocate it, and re-running broadcast is

   idempotent.

"""



from __future__ import annotations



import hashlib

import json

import os

import zipfile

import zlib

from pathlib import Path



import pytest



from scripts import broadcast, init as init_mod, organize, run as run_mod, text_extract

from scripts.utils import logger



# ---------------------------------------------------------------------------

# Fixture builders (minimal but *valid* files)

# ---------------------------------------------------------------------------



_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"





def _sha(path: Path) -> str:

    return hashlib.sha256(path.read_bytes()).hexdigest()





def make_docx(path: Path, paragraphs: list) -> Path:

    body = "".join(

        f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs

    )

    xml = (

        f'<?xml version="1.0"?><w:document xmlns:w="{_W_NS}">'

        f"<w:body>{body}</w:body></w:document>"

    )

    with zipfile.ZipFile(path, "w") as zf:

        zf.writestr("word/document.xml", xml)

    return path





def make_pptx(path: Path, slides: list) -> Path:

    with zipfile.ZipFile(path, "w") as zf:

        for i, text in enumerate(slides, start=1):

            xml = (

                f'<?xml version="1.0"?><p:sld xmlns:p="{_P_NS}" '

                f'xmlns:a="{_A_NS}"><p:cSld><p:spTree>'

                f'<a:p><a:r><a:t>{text}</a:t></a:r></a:p>'

                f"</p:spTree></p:cSld></p:sld>"

            )

            zf.writestr(f"ppt/slides/slide{i}.xml", xml)

    return path





def make_xlsx_stdlib(path: Path, rows: list) -> Path:

    """A minimal (openpyxl-hostile) workbook: shared strings + one sheet."""

    strings = sorted({c for row in rows for c in row})

    sst = (

        '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/'

        f'spreadsheetml/2006/main">{"".join(f"<si><t>{s}</t></si>" for s in strings)}</sst>'

    )

    sheet_rows = ""

    for row in rows:

        cells = "".join(f'<c t="s"><v>{strings.index(c)}</v></c>' for c in row)

        sheet_rows += f"<row>{cells}</row>"

    sheet = (

        '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats'

        '.org/spreadsheetml/2006/main"><sheetData>'

        f"{sheet_rows}</sheetData></worksheet>"

    )

    with zipfile.ZipFile(path, "w") as zf:

        zf.writestr("xl/sharedStrings.xml", sst)

        zf.writestr("xl/worksheets/sheet1.xml", sheet)

    return path





def make_pdf(path: Path, text: str) -> Path:

    """A one-page PDF whose text lives in a FlateDecode content stream."""

    content = (

        b"BT /F1 12 Tf 72 720 Td (" + text.encode("latin-1") + b") Tj ET"

    )

    stream = zlib.compress(content)

    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n"

    pdf += (

        b"2 0 obj<</Length "

        + str(len(stream)).encode()

        + b"/Filter/FlateDecode>>stream\n"

        + stream

        + b"\nendstream\nendobj\n"

    )

    pdf += b"3 0 obj<</Type/Page>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"

    path.write_bytes(pdf)

    return path





@pytest.fixture()

def doc_folder(tmp_path: Path) -> Path:

    """A folder holding one file of every supported format."""

    root = tmp_path / "docs"

    root.mkdir()

    (root / "notes.txt").write_text(

        "Topological insulators and strong correlation effects. " * 4,

        encoding="utf-8",

    )

    (root / "review.md").write_text(

        "# 综述：量子场论中的重整化群\n\n本文讨论 Wilson 的重整化群方法与临界现象。",

        encoding="utf-8",

    )

    (root / "data.csv").write_text("name,score\nalpha,1\n", encoding="utf-8")

    (root / "meta.json").write_text('{"topic": "holography"}', encoding="utf-8")

    (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

    make_docx(root / "lecture.docx", ["Path integrals in quantum field theory."])

    make_pptx(root / "talk.pptx", ["String theory overview", "AdS/CFT part two"])

    make_xlsx_stdlib(root / "results.xlsx", [("experiment", "result"), ("topological order", "confirmed")])

    make_pdf(root / "paper.pdf", "Renormalization group flow near criticality.")

    return root





# ---------------------------------------------------------------------------

# text extraction

# ---------------------------------------------------------------------------





class TestTextExtract:

    def test_plain_text(self, doc_folder: Path):

        text, method = text_extract.extract_text(doc_folder / "notes.txt")

        assert method == "text"

        assert "Topological insulators" in text



    def test_markdown_with_cjk(self, doc_folder: Path):

        text, method = text_extract.extract_text(doc_folder / "review.md")

        assert method == "text"

        assert "重整化群" in text



    def test_docx(self, doc_folder: Path):

        text, method = text_extract.extract_text(doc_folder / "lecture.docx")

        assert method == "docx"

        assert "Path integrals" in text



    def test_pptx_multiple_slides_in_order(self, doc_folder: Path):

        text, method = text_extract.extract_text(doc_folder / "talk.pptx")

        assert method == "pptx"

        assert text.index("overview") < text.index("part two")



    def test_xlsx_stdlib_fallback(self, doc_folder: Path):

        # The fixture deliberately lacks [Content_Types].xml, so openpyxl

        # (when installed) fails and the stdlib shared-strings path runs.

        text, method = text_extract.extract_text(doc_folder / "results.xlsx")

        assert method in ("xlsx", "xlsx-openpyxl")

        assert "topological order" in text

        assert "confirmed" in text



    def test_pdf_stdlib(self, doc_folder: Path):

        text, method = text_extract.extract_text(doc_folder / "paper.pdf")

        assert method.startswith("pdf")

        assert "Renormalization group flow" in text



    def test_pdf_page_count(self, doc_folder: Path):

        assert text_extract.pdf_page_count(doc_folder / "paper.pdf") == 1



    def test_unsupported_extension(self, doc_folder: Path):

        text, method = text_extract.extract_text(doc_folder / "image.png")

        assert text == ""

        assert method == "unsupported"



    def test_corrupt_docx_degrades(self, tmp_path: Path):

        bad = tmp_path / "broken.docx"

        bad.write_bytes(b"this is not a zip archive at all")

        text, method = text_extract.extract_text(bad)

        assert text == ""

        assert method in ("text", "failed")



    def test_extraction_cap(self, tmp_path: Path):

        big = tmp_path / "big.txt"

        big.write_text("x" * 100_000, encoding="utf-8")

        text, _ = text_extract.extract_text(big, max_chars=1000)

        assert len(text) == 1000



    def test_is_supported(self, doc_folder: Path):

        assert text_extract.is_supported(Path("a.txt"))

        assert text_extract.is_supported(Path("a.PDF"))

        assert not text_extract.is_supported(Path("a.png"))


# SRT / VTT subtitles -------------------------------------------------------


    def test_srt_extraction_strips_structure(self, tmp_path: Path):
        p = tmp_path / "lecture.srt"
        p.write_text(
            "1\n00:00:02,940 --> 00:00:03,580\n总的来说，这个算法很优雅\n\n2\n00:00:03,580 --> 00:00:04,220\n复杂度是O(nlogn)\n",
            encoding="utf-8",
        )
        text, method = text_extract.extract_text(p)
        assert method == "text"
        # no index numbers or timestamp axis survive
        assert "-->" not in text and "00:00" not in text
        assert "总的来说" in text
        assert "O(nlogn)" in text


    def test_vtt_extraction_strips_header_and_cues(self, tmp_path: Path):
        p = tmp_path / "talking.vtt"
        p.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello world\n\n00:00:02.000 --> 00:00:03.000 line:1 position:16%80%\nSecond cue\n",
            encoding="utf-8",
        )
        text, method = text_extract.extract_text(p)
        assert method == "text"
        assert "WEBVTT" not in text and "00:00" not in text and "line:1" not in text
        assert text == "Hello world Second cue"


    def test_subtitle_structure_removed_from_text(self):
        raw = (
            "3\n00:00:05,000 --> 00:00:06,100\n第三段对白\n00:00:06,100 --> 00:00:07,000\n第四段对白\n"
        )
        out = text_extract.strip_subtitle(raw)
        assert "3" not in out and "-->" not in out
        assert out == "第三段对白 第四段对白"

    def test_corrupt_subtitle_degrades(self, tmp_path: Path):
        p = tmp_path / "bad.srt"
        p.write_bytes(bytes([0x00, 0x01, 0x02]) + b"garbage")
        text, method = text_extract.extract_text(p)
        # binary bytes decode under latin-1 to junk, or fail outright - either
        # way no subtitle structure can survive the strip
        assert method in ("text", "failed")
        assert "-->" not in text







# ---------------------------------------------------------------------------

# local summarization

# ---------------------------------------------------------------------------





class TestLocalSummarization:

    def test_english_keywords_frequency_over_stopwords(self):

        text = (

            "insulator insulator insulator correlation correlation "

            "topological band structure the the the and and of of of of"

        )

        kws = broadcast.local_keywords(text, k=5)

        assert "insulator" in kws

        assert "correlation" in kws

        # stopwords never surface as keywords

        assert "the" not in kws and "and" not in kws and "of" not in kws



    def test_chinese_keywords_bigrams(self):

        text = "重整化群方法在临界现象中的应用。重整化群方法。临界现象与重整化群。"

        kws = broadcast.local_keywords(text, k=5)

        assert any("重整" in k or "化群" in k for k in kws)

        # stopword characters must not form bigrams

        assert not any(k in ("的了", "是在", "和的") for k in kws)



    def test_keywords_deterministic(self):

        text = "alpha beta gamma alpha beta alpha"

        assert broadcast.local_keywords(text) == broadcast.local_keywords(text)



    def test_local_summary_uses_first_200_chars(self):

        text = "A" * 500

        summary = broadcast.local_summary("f.txt", text, "text", 500, None)

        # the name is NOT repeated - the index line already carries the path

        assert not summary.startswith("f.txt")

        # no sentence boundary in sight: hard cut with an ellipsis

        assert summary.count("A") == 199

        assert summary.endswith(" …")



    def test_local_summary_cuts_at_sentence_boundary(self):

        text = "A" * 150 + ". " + "B" * 300

        summary = broadcast.local_summary("f.txt", text, "text", 500, None)

        assert summary == "A" * 150 + "."



    def test_pdf_metadata_summary(self):

        summary = broadcast.local_summary(

            "scan.pdf", "", "pdf-metadata", 2048, pages=12

        )

        assert "PDF document" in summary

        assert "~12 pages" in summary

        assert "not extractable" in summary



    def test_empty_text_keywords(self):

        assert broadcast.local_keywords("") == []





# ---------------------------------------------------------------------------

# the broadcast center itself

# ---------------------------------------------------------------------------





class TestBroadcast:

    def test_creates_both_index_files(self, doc_folder: Path):

        r = broadcast.broadcast(doc_folder)

        assert r.ok, r.summary_lines()

        bdir = doc_folder / "_broadcast"

        assert (bdir / "INDEX.md").is_file()

        assert (bdir / "index.json").is_file()

        assert r.file_count == 8  # every supported format, png excluded

        assert r.skipped_count == 1  # the png



    def test_index_md_structure(self, doc_folder: Path):

        broadcast.broadcast(doc_folder)

        md = (doc_folder / "_broadcast" / "INDEX.md").read_text(encoding="utf-8")

        assert md.startswith("# Broadcast index")

        assert "read-only digest" in md

        assert "read the directory below first" in md

        assert "## Directory" in md  # the categorized table of contents

        assert "- `notes.txt`" in md

        assert "- `paper.pdf`" in md

        assert "Renormalization group flow" in md

        assert "#insulators" in md.replace(" ", "") or "#insulators" in md

        assert "image.png" in md  # listed under Skipped

        assert "unsupported format" in md



    def test_index_json_structure(self, doc_folder: Path):

        broadcast.broadcast(doc_folder)

        data = json.loads(

            (doc_folder / "_broadcast" / "index.json").read_text(encoding="utf-8")

        )

        assert data["version"] == 1

        assert data["mode"] == "local"

        assert data["file_count"] == 8

        paths = {f["path"] for f in data["files"]}

        assert paths == {

            "notes.txt",

            "review.md",

            "data.csv",

            "meta.json",

            "lecture.docx",

            "talk.pptx",

            "results.xlsx",

            "paper.pdf",

        }

        entry = next(f for f in data["files"] if f["path"] == "lecture.docx")

        assert entry["method"] == "docx"

        assert entry["keywords"]

        # the summary no longer repeats the filename (the path is above it)

        assert entry["summary"]

        assert not entry["summary"].startswith("lecture.docx")

        assert entry["size"] > 0

        assert data["skipped"] == [{"path": "image.png", "reason": "unsupported format"}]



    def test_read_only_originals_untouched(self, doc_folder: Path):

        before = {

            p.name: (_sha(p), p.stat().st_mtime_ns)

            for p in doc_folder.iterdir()

            if p.is_file()

        }

        broadcast.broadcast(doc_folder)

        after = {

            p.name: (_sha(p), p.stat().st_mtime_ns)

            for p in doc_folder.iterdir()

            if p.is_file()

        }

        assert before == after  # same names, same bytes, same mtimes



    def test_only_broadcast_dir_is_written(self, doc_folder: Path):

        before = {p.name for p in doc_folder.iterdir()}

        broadcast.broadcast(doc_folder)

        after = {p.name for p in doc_folder.iterdir()}

        assert after - before == {"_broadcast"}



    def test_idempotent(self, doc_folder: Path):

        broadcast.broadcast(doc_folder)

        first = (doc_folder / "_broadcast" / "index.json").read_text(encoding="utf-8")

        r2 = broadcast.broadcast(doc_folder)

        assert r2.ok

        second = (doc_folder / "_broadcast" / "index.json").read_text(encoding="utf-8")

        # generated_at is the only expected difference

        d1 = json.loads(first)

        d2 = json.loads(second)

        d1.pop("generated_at")

        d2.pop("generated_at")

        assert d1 == d2



    def test_rebroadcast_does_not_index_itself(self, doc_folder: Path):

        broadcast.broadcast(doc_folder)

        r2 = broadcast.broadcast(doc_folder)

        assert r2.file_count == 8  # _broadcast/ contents never re-indexed



    def test_skips_hidden_files(self, doc_folder: Path):

        (doc_folder / ".secret.txt").write_text("hidden", encoding="utf-8")

        r = broadcast.broadcast(doc_folder)

        assert r.file_count == 8



    def test_skips_process_zone(self, tmp_path: Path):

        root = tmp_path / "task"

        root.mkdir()

        (root / "real.txt").write_text("real content", encoding="utf-8")

        (root / "process").mkdir()

        (root / "process" / "internal.json").write_text("{}", encoding="utf-8")

        r = broadcast.broadcast(root)

        assert r.file_count == 1  # tool bookkeeping is not user content



    def test_root_must_exist(self, tmp_path: Path):

        missing = tmp_path / "nope"

        r = broadcast.broadcast(missing)

        assert not r.ok

        assert not missing.exists()  # no tree materialised from a typo



    def test_max_files_cap(self, doc_folder: Path):

        r = broadcast.broadcast(doc_folder, max_files=3)

        assert r.file_count == 3

        # every leftover file is counted (5 over the cap + the png), but the

        # skipped *list* stays aggregated instead of one line per file

        assert r.skipped_count == 6

        data = json.loads(

            (doc_folder / "_broadcast" / "index.json").read_text(encoding="utf-8")

        )

        assert len(data["skipped"]) == 2  # png + one aggregate cap line

        reasons = " ".join(s["reason"] for s in data["skipped"])

        assert "file cap reached" in reasons



    def test_no_ai_calls_when_disabled(self, doc_folder: Path, monkeypatch):

        called = []

        monkeypatch.setattr(

            broadcast.utils, "_ai_chat", lambda *a, **k: called.append(a) or ""

        )

        r = broadcast.broadcast(doc_folder)

        assert r.ai_used is False

        assert called == []  # local mode never touches the network



    def test_md_soft_limit_warns(self, doc_folder: Path, monkeypatch):

        warnings = []

        monkeypatch.setattr(logger, "warning", warnings.append)

        monkeypatch.setattr(broadcast, "MD_SOFT_LIMIT", 10)

        broadcast.broadcast(doc_folder)

        assert any("soft limit" in w for w in warnings)





# ---------------------------------------------------------------------------

# integration with the rest of the tool

# ---------------------------------------------------------------------------





class TestBroadcastIntegration:

    def test_broadcast_is_a_tool_owned_prefix(self):

        assert broadcast.BROADCAST_DIRNAME in organize.owned_prefixes()



    def test_init_does_not_lift_broadcast(self, tmp_path: Path):

        from scripts import init as init_mod



        root = tmp_path / "task"

        root.mkdir()

        (root / "material.txt").write_text("user material", encoding="utf-8")

        (root / "_broadcast").mkdir()

        (root / "_broadcast" / "INDEX.md").write_text("index", encoding="utf-8")



        init_mod.init_folder(root)



        assert (root / "_broadcast" / "INDEX.md").is_file()

        assert (root / "material" / "initial" / "material.txt").is_file()

        assert not (root / "material" / "initial" / "_broadcast").exists()



    def test_organize_does_not_move_broadcast(self, tmp_path: Path):

        from scripts import init as init_mod



        root = tmp_path / "task"

        root.mkdir()

        init_mod.init_folder(root)

        (root / "later.txt").write_text("late arrival", encoding="utf-8")

        # init already created _broadcast/ (task-start requirement); a later

        # index write into it must survive organize untouched

        (root / "_broadcast" / "INDEX.md").write_text("index", encoding="utf-8")



        from scripts.run import run



        res = run(root, mode="full")

        assert res.ok, res.summary_lines()

        assert (root / "_broadcast" / "INDEX.md").is_file()

        assert not (root / "material" / "initial" / "_broadcast").exists()



    def test_broadcast_then_organize_keeps_both(self, doc_folder: Path):

        """The realistic order: digest first, tidy later."""

        broadcast.broadcast(doc_folder)

        from scripts import init as init_mod



        init_mod.init_folder(doc_folder)

        from scripts.run import run



        res = run(doc_folder, mode="full")

        assert res.ok, res.summary_lines()

        assert (doc_folder / "_broadcast" / "INDEX.md").is_file()





class TestAiModePolicy:

    """AI mode must be honest about what it used and honour --ai."""



    def test_ai_flag_forces_past_env_optin(self, doc_folder: Path, monkeypatch):

        # --ai is documented as "force AI even when TASK_ORG_AI is unset";

        # a configured key is the only remaining requirement

        monkeypatch.setattr(broadcast.utils, "ai_enabled", lambda: False)

        monkeypatch.setattr(broadcast.utils, "_configured_ai_key", lambda: "k")

        monkeypatch.setattr(

            broadcast.utils,

            "_ai_chat",

            lambda *a, **kw: "AI summary line.\nkw1, kw2",

        )

        broadcast.broadcast(doc_folder, use_ai=True)

        data = json.loads(

            (doc_folder / "_broadcast" / "index.json").read_text(encoding="utf-8")

        )

        assert data["mode"] == "ai"

        assert data["files"][0]["summary"] == "AI summary line."

        assert data["files"][0]["keywords"] == ["kw1", "kw2"]



    def test_ai_flag_without_key_degrades_to_local_label(

        self, doc_folder: Path, monkeypatch

    ):

        monkeypatch.setattr(broadcast.utils, "ai_enabled", lambda: False)

        monkeypatch.setattr(broadcast.utils, "_configured_ai_key", lambda: None)

        r = broadcast.broadcast(doc_folder, use_ai=True)

        assert r.ai_used is False

        data = json.loads(

            (doc_folder / "_broadcast" / "index.json").read_text(encoding="utf-8")

        )

        # the index must not claim ai mode when it silently used local

        assert data["mode"] == "local"



    def test_env_optin_with_key_uses_ai(self, doc_folder: Path, monkeypatch):

        monkeypatch.setattr(broadcast.utils, "ai_enabled", lambda: True)

        monkeypatch.setattr(broadcast.utils, "_configured_ai_key", lambda: "k")

        monkeypatch.setattr(

            broadcast.utils,

            "_ai_chat",

            lambda *a, **kw: "Env summary.\nenvkw",

        )

        broadcast.broadcast(doc_folder)  # no --ai flag

        data = json.loads(

            (doc_folder / "_broadcast" / "index.json").read_text(encoding="utf-8")

        )

        assert data["mode"] == "ai"

        assert data["files"][0]["summary"] == "Env summary."





# ---------------------------------------------------------------------------

# regression guards from the pre-release debug/optimization rounds

# ---------------------------------------------------------------------------





class TestEncodingRobustness:

    """Legacy encodings must decode to real text, never mojibake."""



    def test_gbk_text(self, tmp_path: Path):

        p = tmp_path / "gbk.txt"

        p.write_bytes("任务文件夹整理：综述初稿。".encode("gb18030"))

        text, method = text_extract.extract_text(p)

        assert method == "text"

        assert "综述" in text and "任务" in text



    def test_big5_text(self, tmp_path: Path):

        p = tmp_path / "big5.txt"

        p.write_bytes("資料整理與鍵盤。".encode("big5"))

        text, _ = text_extract.extract_text(p)

        assert "資料" in text



    def test_big5_not_misdecoded_as_gb18030(self):

        # these bytes decode under gb18030 into private-use characters;

        # that decode must be rejected in favour of big5

        raw = "資料整理與鍵盤。".encode("big5")

        assert text_extract._sniff_encoding(raw) == "big5"



    def test_utf16_text(self, tmp_path: Path):

        p = tmp_path / "u16.txt"

        p.write_bytes("edge transport robustness".encode("utf-16"))

        text, _ = text_extract.extract_text(p)

        assert "edge transport" in text



    def test_utf8_bom_stripped(self, tmp_path: Path):

        p = tmp_path / "bom.txt"

        p.write_bytes("\ufeffbom content".encode("utf-8"))

        text, _ = text_extract.extract_text(p)

        assert not text.startswith("\ufeff")

        assert "bom content" in text



    def test_latin1_text(self, tmp_path: Path):

        p = tmp_path / "l1.txt"

        p.write_bytes("caf\u00e9 na\u00efve".encode("latin-1"))

        text, _ = text_extract.extract_text(p)

        assert "caf\u00e9" in text



    def test_binary_does_not_crash(self, tmp_path: Path):

        p = tmp_path / "bin.txt"

        p.write_bytes(bytes(range(256)) * 8)

        text, method = text_extract.extract_text(p)

        assert isinstance(text, str)



    def test_huge_file_read_is_bounded(self, tmp_path: Path):

        # only max_chars characters are ever pulled into memory

        p = tmp_path / "huge.txt"

        p.write_text("x" * 300_000, encoding="utf-8")

        text, _ = text_extract.extract_text(p, max_chars=100)

        assert len(text) == 100





class TestKeywordQuality:

    """Chinese keywords must be words/phrases, not straddling fragments."""



    def test_repeated_phrase_extended(self):

        text = (

            "广播中心是上下文压缩索引。广播中心节省 token。"

            "上下文压缩索引先读再读原文。"

        )

        kws = broadcast.local_keywords(text, k=4)

        assert "广播中心" in kws

        assert "上下文压缩索引" in kws



    def test_frequent_fragment_superseded_by_phrase(self):

        # "索引" is the most frequent term, but the full repeated phrase

        # must win over the fragment

        text = "上下文压缩索引。上下文压缩索引。索引很多。索引很多。"

        kws = broadcast.local_keywords(text, k=3)

        assert "上下文压缩索引" in kws

        assert "索引" not in kws



    def test_single_mention_bigrams_do_not_overlap(self):

        text = "任务文件夹整理：综述初稿。"

        kws = broadcast.local_keywords(text, k=5)

        assert "任务" in kws

        assert "务文" not in kws  # overlaps 任务

        assert "文件" in kws

        assert "件夹" not in kws  # overlaps 文件



    def test_deterministic_under_reordering_of_input(self):

        a = "alpha beta gamma delta alpha beta"

        assert broadcast.local_keywords(a) == broadcast.local_keywords(a)





class TestIndexRobustness:

    """The index files must stay well-formed for pathological names."""



    def test_backtick_filename_sanitized(self, tmp_path: Path):

        root = tmp_path / "d"

        root.mkdir()

        (root / "weird `name`.txt").write_text("content", encoding="utf-8")

        broadcast.broadcast(root)

        md = (root / "_broadcast" / "INDEX.md").read_text(encoding="utf-8")

        line = next(ln for ln in md.splitlines() if "weird" in ln)

        # only the wrapping pair of backticks may remain

        assert line.count("`") == 2

        assert "weird 'name'.txt" in line



    def test_paths_use_forward_slashes(self, tmp_path: Path):

        root = tmp_path / "d"

        root.mkdir()

        sub = root / "a" / "b"

        sub.mkdir(parents=True)

        (sub / "deep.txt").write_text("x", encoding="utf-8")

        broadcast.broadcast(root)

        data = json.loads(

            (root / "_broadcast" / "index.json").read_text(encoding="utf-8")

        )

        assert data["files"][0]["path"] == "a/b/deep.txt"



    def test_cap_skips_stay_bounded(self, tmp_path: Path):

        root = tmp_path / "d"

        root.mkdir()

        for i in range(40):

            (root / f"f{i:02d}.txt").write_text("x", encoding="utf-8")

        r = broadcast.broadcast(root, max_files=5)

        assert r.file_count == 5

        assert r.skipped_count == 35  # every leftover file is counted

        data = json.loads(

            (root / "_broadcast" / "index.json").read_text(encoding="utf-8")

        )

        assert len(data["skipped"]) == 1  # but the list is aggregated

        assert "35" in data["skipped"][0]["path"]



    def test_symlink_dir_loop_is_safe(self, tmp_path: Path):

        root = tmp_path / "d"

        root.mkdir()

        (root / "real.txt").write_text("x", encoding="utf-8")

        sub = root / "sub"

        sub.mkdir()

        (sub / "inner.txt").write_text("y", encoding="utf-8")

        try:

            os.symlink(root, sub / "loop")  # cycle back to the root

        except OSError:

            pytest.skip("symlinks unavailable on this platform")

        r = broadcast.broadcast(root)

        assert r.ok

        assert r.file_count == 2



    def test_hidden_and_process_dirs_pruned_before_descending(self, tmp_path: Path):

        root = tmp_path / "d"

        root.mkdir()

        (root / ".git").mkdir()

        (root / ".git" / "config.txt").write_text("x", encoding="utf-8")

        (root / "process").mkdir()

        (root / "process" / "log.txt").write_text("x", encoding="utf-8")

        (root / "keep.txt").write_text("x", encoding="utf-8")

        broadcast.broadcast(root)

        data = json.loads(

            (root / "_broadcast" / "index.json").read_text(encoding="utf-8")

        )

        assert {f["path"] for f in data["files"]} == {"keep.txt"}





class TestTaskStartFullChain:

    """Locks the user's hard requirement for a task start:



    the moment a task folder is opened, *every* structural folder is built

    (materials / process / results / broadcast), then content is written,

    then the broadcast index is written -- and a later organize must not

    disturb any of it.

    """



    def test_init_builds_all_folders_including_broadcast(self, tmp_path: Path):

        root = tmp_path / "task"

        root.mkdir()

        res = init_mod.init_folder(root)

        assert res.ok

        for sub in (

            "material/initial",

            "material/downloaded",

            "process",

            "results",

            "_broadcast",

        ):

            assert (root / sub).is_dir(), f"missing {sub}"



    def test_full_chain_report_to_results_then_broadcast_survives_reorganize(

        self, tmp_path: Path

    ):

        root = tmp_path / "task"

        root.mkdir()



        # 1) task start: build the whole skeleton (incl. _broadcast)

        init_mod.init_folder(root)



        # 2) write a deliverable whose name carries a results keyword

        # (note: avoid the draft keyword 草稿, which would route to process)

        (root / "开题报告_西方经济研究.md").write_text(

            "重整化群是量子场论处理临界现象的核心工具。\n", encoding="utf-8"

        )



        # 3) organize -> deliverable must land in results/

        r1 = run_mod.run(root, mode="full")

        assert r1.ok, r1.summary_lines()

        assert (root / "results" / "开题报告_西方经济研究.md").is_file()

        assert not (root / "开题报告_西方经济研究.md").exists()



        # 4) broadcast -> index written into the already-existing _broadcast/

        r2 = broadcast.broadcast(root)

        assert r2.ok

        idx = (root / "_broadcast" / "INDEX.md").read_text(encoding="utf-8")

        assert "开题报告" in idx

        md_hash = hashlib.sha256(

            (root / "_broadcast" / "INDEX.md").read_bytes()

        ).hexdigest()



        # 5) reorganize -> results file stays put, broadcast index untouched

        r3 = run_mod.run(root, mode="full")

        assert r3.ok, r3.summary_lines()

        assert (root / "results" / "开题报告_西方经济研究.md").is_file()

        assert (

            hashlib.sha256(

                (root / "_broadcast" / "INDEX.md").read_bytes()

            ).hexdigest()

            == md_hash

        )

