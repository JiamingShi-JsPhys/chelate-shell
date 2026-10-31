---
name: figure-generator
description: Heavy figure-generation processor. Publishes statistical charts (matplotlib/seaborn) from structured data in an isolated sandbox.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.2.0
  entry_point: python scripts/run.py
  python_requires: '>=3.10'
version: 1.2.0
---

# figure-generator

## Quick Execution

**Do NOT read the source code. Run this exact command format directly:**

```bash
python scripts/run.py --root <WS> --action process --input <FILE>
```

- `--root <WS>` = the user's workspace (absolute path). All artifacts land in
  `<WS>/process/figures/` — never in the skill's install dir.
- Valid `--action`: process.
- `--input` is branched by file extension:
  - **`.json`** → parsed as a JSON object.  Two shapes are supported:
    - A **SEM path diagram** (rendered with `matplotlib.patches` +
      `pyplot.annotate`, not a table chart).  Set `"type": "sem_path"`:
      ```json
      {
        "type": "sem_path",
        "title": "Measurement + structural model",
        "latents": [
          {"name": "F1", "label": "F1",
           "indicators": ["Q1_1", "Q1_2", "Q1_3"],
           "loadings": [1.00, 0.85, 0.80]},
          {"name": "F2", "label": "F2",
           "indicators": ["Q2_1", "Q2_2"],
           "loadings": [1.00, 0.88]}
        ],
        "exogenous": [{"name": "X1", "label": "Control X1"}],
        "structural_paths": [
          {"from": "F1", "to": "F2", "estimate": 0.42, "se": 0.05, "p": 0.001}
        ],
        "fit_indices": {"CFI": 1.001, "TLI": 1.000, "RMSEA": 0.000}
      }
      ```
      Semantics of the SEM spec:
        - **Layered layout (rank-based, no crossing):** exogenous observed
          variables sit in the far-LEFT column, latent constructs are
          **ellipses** in the MIDDLE column, and each latent's observed
          indicators are **rectangles** in a RIGHT-side column stacked under
          their own latent.  This guarantees no edge crosses a node body.
        - **`latents`**: a latent → **ellipse** in the middle column; each
          `indicator` → a **rectangle** to its right, and a factor-loading
          arrow goes **directly** from the latent to the indicator's *left
          edge* (each loading arrow lives in the open gap west of the
          indicator column, so it never sweeps across a sibling box — no
          observed-to-observed causal chain, ever).  The first loading is the
          fixed marker = `1.00`.
        - **`exogenous`**: observed control variables → **rectangles** in the
          LEFT column (causes-on-the-left SEM convention).  IMPORTANT:
          exogenous observed nodes are drawn with **NO** measurement-error
          `e` circle (only endogenous indicators get one).
        - **`structural_paths`**: directed (`from` → `to`) causal arrows
          carrying the `estimate` (and `**` / `*` significance from `p`).
          Every edge is drawn with `FancyArrowPatch` and terminates strictly
          on a node's *border* (never centre-to-centre) so no line passes
          through a box.  Paths that span intermediate latents bow away from
          them.
        - **error / disturbance variance**: each latent gets a dashed
          double-headed **disturbance arc** hugging the top of its ellipse
          (clear of the loading/structural edges).  Every **endogenous**
          observed node gets a small **`e` circle** placed **beside** it
          (right side) with a dashed arrow pointing **into** the node (the
          `e → y` measurement-error convention) — exogenous nodes never get
          one.
        - **`standardized: true`** at the top level (or per panel) renders
          standardised coefficients when a `std` field is supplied on a
          loading or path.
        - **`panels`**: an array of SEM specs → rendered with
          `plt.subplots(1, N)` as a single row of N panels labelled `(A)`,
          `(B)`, `(C)` …; each panel keeps its own coordinate system so they
          never interfere.
      Output: `<WS>/process/figures/sem_path.pdf` + `sem_path.png`.
    - A **generic table** with a `"rows"` array (e.g.
      `{"title": "...", "chart": "bar", "rows": [{"a":1,"b":2}, ...]}`),
      rendered as a chart.
  - **`.csv`** → read with pandas and rendered as a chart.  Use
    `--x`, `--y`, `--hue` to pick columns, `--chart` to change the type.
    With no `--x/--y`, the first categorical and first numeric columns are
    inferred automatically.
- `--chart` accepts **`bar`** (default), **`line`**, **`scatter`**, **`box`**.
- `--title` overrides the figure title (defaults to the file's own title).
- **This skill runs in a sandboxed process (sandbox_required: true).**
  The 120-second circuit-breaker force-kills the child on timeout and returns
  `UNVERIFIED` — not `FAIL`. Do not treat a timeout as a data failure.

## Publication-grade styling (always applied)

The engine pushes a fixed `rcParams` block so every output is journal-ready:

- **Editable, extractable TrueType text** — the engine forces
  `pdf.fonttype=42` / `ps.fonttype=42` (and `svg.fonttype="none"`) at render
  time, and resolves a guaranteed-installed font (Arial if present, else a
  bundled substitute) so the PDF text layer is **copyable / extractable**
  (verify with `pdftotext` or `pypdf`), not outlined garbage.
- **Colour-blind-safe palette** — the Okabe-Ito 8-colour set is the default
  categorical palette (also prints well in greyscale).
- **Clean frame** — top/right spines removed (`despine`) and a tight bounding
  box with a small `pad_inches`.
- **Arial family, 8–10 pt** body text, 300 dpi, vector PDF + raster PNG.
- Long/over-many bar labels are auto-rotated 45° and right-aligned so they
  never collapse into an unreadable blob.

## Status

**IMPLEMENTED (v1.2.0).** The engine (`scripts/engine.py`) renders
publication-quality charts with matplotlib/seaborn and writes a PDF + PNG into
the workspace, including a dedicated **SEM path-diagram renderer** with a
layered, rank-based layout (exogenous left / latents middle / indicators
right), border-to-border `FancyArrowPatch` edges (no line passes through a
node), exogenous nodes with **no** `e` circle, disturbance arcs on latents,
`e → y` measurement-error circles on endogenous indicators, structural paths
with significance stars, and `plt.subplots(1, N)` multi-panel support.  The
PDF text layer is embedded as extractable TrueType.  Bar / line / scatter /
box charts are also supported under the publication-grade styling above.
A missing dependency degrades to `UNVERIFIED`, never a crash.

The SEM `sem_path` JSON is the documented interchange format for path-diagram
rendering: any modelling tool (an AMOS-style GUI, a lavaan/R script, or a
bespoke exporter) can write it to `<WS>/process/figures/sem_path_input.json`,
and `figure-generator` *draws* the diagram from that spec with no human glue.

## When to use
- A manuscript needs a publication-quality chart (box plot, regression
  scatter, factor-loading heatmap) derived from a structured dataset.
- A figure must be generated reproducibly (seeded) for peer review.

## When NOT to use
- A figure must be hand-drawn or vector-illustrated (out of scope).
- Real-time interactive plotting (matplotlib is batch-only here).

## Dependencies
- `matplotlib` — chart backend
- `seaborn` — statistical plot styles
- `pandas` — data preparation
