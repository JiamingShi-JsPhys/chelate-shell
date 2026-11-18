# deck-exporter

Turn the Markdown reports in `process/` into one self-contained HTML deck —
images inlined, CSS inline, no network references, and no absolute paths.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

Nothing. Standard library only.

## Usage

```bash
python run.py --root <workspace> --action build --name deck
```

## Input

Every `*.md` in `process/`, in filename order:

- the first `# ` heading becomes the title slide;
- each `## ` heading starts a slide;
- `![](figures/plot.png)` is inlined as a `data:` URI when the file is under
  2 MiB, and replaced by its alt text otherwise (and in the report).

## What is refused

A deck that would contain a Windows drive, a UNC path, `file://`, `/home/…`
or `/Users/…` is not written at all. The alternative — writing it and
sanitising the obvious ones — leaves the job half done on a file that has
already been sent to someone.

## Outputs

| Path | Content |
|------|---------|
| `process/gates/deck-exporter_<ts>.json` | gate result (PASS / FAIL / UNVERIFIED) |
| `process/deck/<name>.html` | the deck: sections, inline CSS, `data:` images |
| `process/deck/<name>.json` | sources, slide count, images inlined and skipped |
