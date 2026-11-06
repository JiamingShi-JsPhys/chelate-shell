# latex-exporter

LaTeX export processor — **no heavy dependency, no pandoc**. Reads the Markdown
reports generated under `process/` and the graphics under `process/figures/`,
then merges them into a single compilable `.tex` file under `process/latex/`.
Part of **chelate-shell v1.2.0** (MIT).

## Usage

```bash
python scripts/run.py --root <WS> --action process
python scripts/run.py --root <WS> --action process --name manuscript.tex
```

The verdict is written to `<WS>/process/gates/latex-exporter_<ts>.json` and the
`.tex` to `<WS>/process/latex/<name>.tex`; both paths are reported on stdout.

## Inputs it discovers
- Markdown: every `*.md` under `<WS>/process/` (recursively), sorted.
- Graphics: every `.pdf/.png/.jpg/.jpeg/.eps` under `<WS>/process/figures/`.

## Markdown subset
ATX headings, fenced code blocks (`verbatim`), pipe tables (`tabular`), bullet
/ numbered lists, block quotes, horizontal rules, and inline **bold** /
*italic* / `code` / `[links](url)` / `![images](src)` / `$...$` math. LaTeX
special characters are escaped; math and code are protected from escaping.
`ctex` is auto-added when CJK text is detected (compile with XeLaTeX/LuaLaTeX).

## Output
A complete `article` — preamble + `\maketitle` + one section structure per
report (separated by `\clearpage`) + a `Figures` section with one `figure`
float per graphic (caption from the filename).

## Clean-room
The converter is a self-contained standard-library renderer; no third-party
conversion source is copied.
