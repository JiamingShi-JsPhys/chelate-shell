"""Figure-generation engine for the chelate-shell figure-generator skill.

Renders publication-quality figures from structured data using matplotlib +
seaborn, with top-journal styling (Arial family, no top/right spines, 300 dpi,
font sizes 9-10pt, editable TrueType text, colour-blind-safe palette). Writes
a vector PDF + raster PNG into the workspace and returns their paths as
artifacts.

Input is dispatched by file extension, NOT by a single CSV reader:
  - ``.csv`` / ``.txt`` (table)   -> bar / line / scatter / box (pandas)
  - ``.json`` with ``type: "sem_path"`` -> a dedicated SEM path diagram
    (``draw_sem_path``). Layout is *layered* (rank-based): exogenous observed
    variables on the far LEFT, latent constructs as ellipses in the MIDDLE
    column, each latent's observed indicators as rectangles to its RIGHT;
    every loading arrow fans directly from a latent to its own indicators
    (no observed-to-observed chaining), exogenous nodes carry NO error
    circle, endogenous nodes carry a small 'e' measurement-error circle with a
    dashed arrow, and structural (causal) paths are directed arrows that bow
    around intermediate nodes. Multi-model specs use a ``panels`` array and
    are drawn with plt.subplots(1, N) so panels never interfere.
  - ``.json`` without ``type: "sem_path"`` -> a generic table (the JSON is
    parsed, then rendered as a bar chart of its first numeric column).

PDF text is emitted as embedded, extractable TrueType (pdf.fonttype=42 /
ps.fonttype=42) so the text layer can be copied out of the generated PDF.
No graphviz / external binary is required -- the layout is computed directly.

Graceful degradation: a missing matplotlib / seaborn dependency returns an
UNVERIFIED verdict rather than crashing, and a malformed input returns an
UNVERIFIED verdict that names the *expected* input contract instead of a raw
stack trace. License note: matplotlib (BSD-3-Clause / PSF), seaborn
(BSD-3-Clause), pandas (BSD-3-Clause) and numpy (BSD-3-Clause) are
permissive and MIT-compatible.
"""
from __future__ import annotations

import json
import math
import os

# Top-journal plotting defaults.
DPI = 300
FONT_FAMILY = "Arial"
# Journal figure panels are usually single/double column; 9pt is the floor
# (print-clarity requirement: all in-figure text 9-10pt Arial).
FONT_MIN_PT = 9

# Okabe-Ito colour-blind-safe palette (Universally readable, also prints well
# in greyscale). Used as the default categorical palette for all table charts.
OKABE_ITO = [
    "#000000", "#E69F00", "#56B4E9", "#009E73",
    "#F0E442", "#0072B2", "#D55E00", "#CC79A7",
]

# Publication-grade rcParams.  pdf.fonttype=42 keeps text as editable
# TrueType in Illustrator / Inkscape; svg.fonttype="none" keeps text as
# real text (not outlined paths) so the SVG stays editable.  These are the
# settings that make the PDF text layer copyable/extractable.
_PUB_RCPARAMS = {
    "font.family": FONT_FAMILY,
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": False,
    "figure.dpi": DPI,
    "savefig.dpi": DPI,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04,
    "pdf.fonttype": 42,        # editable TrueType outlines in vector editors
    "pdf.use14corefonts": False,
    "ps.fonttype": 42,
    "svg.fonttype": "none",    # keep text as text, not paths
    "mathtext.fontset": "custom",
    "mathtext.rm": FONT_FAMILY,
    "mathtext.it": FONT_FAMILY,
    "mathtext.bf": FONT_FAMILY,
}

# The SEM path-diagram input contract (what the spec / SKILL.md documents).
SEM_SPEC_HINT = (
    "expected a JSON object of shape: "
    '{"type": "sem_path", "title": "...", '
    '"latents": [{"name", "label", "indicators": [...], '
    '"loadings": [...]}], '
    '"structural_paths": [{"from", "to", "estimate", "se", "p"}], '
    '"fit_indices": {"CFI", "TLI", "RMSEA"}}; '
    "or a CSV table with --x/--y columns"
)


def _verdict(status, reason, artifacts=None, evidence="EMPIRICAL"):
    return {
        "status": status,
        "evidence_level": evidence,
        "reason": reason,
        "artifacts": list(artifacts or []),
    }


def _require_columns(df, *cols):
    missing = [c for c in cols if c and c not in df.columns]
    if missing:
        raise ValueError(f"column(s) not found in input: {missing}")


def _apply_pub_style(plt, table=True):
    """Push the publication-grade rcParams and (optionally) the colour-blind
    palette.  Safe to call repeatedly; it only updates, never resets."""
    plt.rcParams.update(_PUB_RCPARAMS)
    if table:
        try:
            import seaborn as sns
            sns.set_palette(OKABE_ITO)
        except Exception:
            pass


def _load_input(data_path):
    """Dispatch on extension: JSON -> dict, CSV/TXT -> DataFrame.

    Returns ``(kind, payload, meta)`` where kind is one of ``"sem_path"`` /
    ``"table"``. Raises ``ValueError`` (caught by the caller) when the input
    is malformed, so the caller can emit a self-explanatory UNVERIFIED.
    """
    ext = os.path.splitext(data_path)[1].lower()
    if ext == ".json":
        with open(data_path, encoding="utf-8") as fh:
            spec = json.load(fh)
        if not isinstance(spec, dict):
            raise ValueError("JSON input must be an object at the top level")
        if (spec.get("type") or "").lower() == "sem_path":
            return "sem_path", spec, {}
        # Generic JSON table: render the first row-mapped structure.
        rows = spec.get("rows") or []
        if rows:
            import pandas as pd
            return "table", pd.DataFrame(rows), {"title": spec.get("title"),
                                                "chart": spec.get("chart")}
        raise ValueError(
            f"JSON input has no recognisable 'type' or 'rows'; {SEM_SPEC_HINT}")
    # Default: a tabular dataset.
    import pandas as pd
    df = pd.read_csv(data_path)
    return "table", df, {}


def generate(data_path, chart=None, x=None, y=None, hue=None,
             title=None, output_dir=None, root=None):
    # --- graceful degradation ---
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless / sandbox-safe backend
    except ImportError:
        return _verdict("UNVERIFIED", "matplotlib not installed")
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        import pandas as pd
        import numpy as np  # noqa: F401
    except ImportError:
        return _verdict("UNVERIFIED", "seaborn/pandas not installed")

    if not data_path or not os.path.isfile(data_path):
        return _verdict("UNVERIFIED", f"dataset not found: {data_path}")

    # --- dispatch on extension; JSON never goes through the CSV reader ---
    try:
        kind, payload, meta = _load_input(data_path)
    except (json.JSONDecodeError, ValueError) as exc:
        return _verdict("UNVERIFIED",
                        f"could not parse input {os.path.basename(data_path)}: "
                        f"{exc}; {SEM_SPEC_HINT}")
    except Exception as exc:
        return _verdict("UNVERIFIED",
                       f"could not read input {data_path}: {exc}; "
                       f"expected a .csv table or a .json spec; {SEM_SPEC_HINT}")

    # Resolve output directory inside the workspace (never the skill dir).
    if output_dir:
        out_dir = output_dir
    elif root:
        out_dir = os.path.join(root, "process", "figures")
    else:
        out_dir = os.path.join(os.getcwd(), "process", "figures")
    os.makedirs(out_dir, exist_ok=True)

    if kind == "sem_path":
        return _render_sem_path(
            plt, payload, out_dir,
            title=title or payload.get("title"))

    # --- generic table path (bar / line / scatter / box) ---
    df = payload
    chart = (chart or meta.get("chart") or "bar").lower()
    if chart not in ("bar", "line", "scatter", "box"):
        return _verdict("UNVERIFIED",
                        f"unsupported chart type {chart!r}; "
                        f"expected one of bar/line/scatter/box")

    # When no x/y are given, pick sensible defaults: the first text/object
    # column as x and the first numeric column as y.  This makes a bare CSV
    # render without the caller having to name columns.
    if x is None or y is None:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        cat_cols = [c for c in df.columns if c not in num_cols]
        if x is None:
            x = cat_cols[0] if cat_cols else (num_cols[0] if num_cols else None)
        if y is None:
            y = num_cols[0] if num_cols else None
    if not x or not y:
        return _verdict("UNVERIFIED",
                        "could not infer x/y columns; pass --x and --y; "
                        + SEM_SPEC_HINT)

    # Top-journal styling.
    _apply_pub_style(plt, table=True)

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    try:
        if chart == "bar":
            _require_columns(df, x, y)
            sns.barplot(data=df, x=x, y=y, hue=hue, ax=ax,
                        errorbar=None, width=0.7)
            _fix_bar_labels(ax, df[x].astype(str).tolist())
        elif chart == "line":
            _require_columns(df, x, y)
            sns.lineplot(data=df, x=x, y=y, hue=hue, ax=ax)
        elif chart == "box":
            _require_columns(df, x, y)
            sns.boxplot(data=df, x=x, y=y, hue=hue, ax=ax, width=0.55)
            _fix_bar_labels(ax, df[x].astype(str).tolist())
        else:  # scatter
            _require_columns(df, x, y)
            sns.scatterplot(data=df, x=x, y=y, hue=hue, ax=ax)
        ax.set_title(title or f"{chart.title()} plot", fontsize=10)
        if x:
            ax.set_xlabel(x, fontsize=10)
        if y:
            ax.set_ylabel(y, fontsize=10)
        # Despine: drop the top/right frame for a clean journal look.
        try:
            sns.despine(ax=ax)
        except Exception:
            pass
    except Exception as exc:
        plt.close(fig)
        return _verdict("UNVERIFIED", f"plotting failed: {exc}")

    pdf_path = os.path.join(out_dir, "figure.pdf")
    png_path = os.path.join(out_dir, "figure.png")
    try:
        fig.savefig(pdf_path)
        fig.savefig(png_path)
    except Exception as exc:
        plt.close(fig)
        return _verdict("UNVERIFIED", f"failed to save figure: {exc}")
    finally:
        plt.close(fig)

    return _verdict(
        "PASS",
        f"{chart} figure written: {os.path.basename(pdf_path)}, "
        f"{os.path.basename(png_path)}",
        artifacts=[pdf_path, png_path])


def _fix_bar_labels(ax, labels):
    """Stop long categorical bar labels from turning into an unreadable blob.

    Rotates 45deg with right-alignment when labels are wide, otherwise keeps
    them horizontal. This is the single most common reviewer complaint in a
    bar chart, so it is applied unconditionally.
    """
    ticks = ax.get_xticklabels()
    if not ticks:
        return
    longest = max((len(str(s)) for s in labels), default=0) if labels else 0
    if longest > 8 or len(labels) > 6:
        for t in ticks:
            t.set_rotation(45)
            t.set_ha("right")
        ax.tick_params(axis="x", labelsize=FONT_MIN_PT + 1)


# ---------------------------------------------------------------------------
# SEM path diagram  (the dedicated draw_sem_path the spec asks for)
#
# Layout model (v1.2.0, rewritten for complex models):
#   * Layered, rank-based columns so edges never cross node bodies:
#       - exogenous observed variables  -> far LEFT  (NO error circle)
#       - latent constructs             -> MIDDLE column (ellipses)
#       - endogenous observed indicators -> RIGHT column, stacked per latent
#   * Every edge is drawn with FancyArrowPatch and terminates STRICTLY on a
#     node's border (never centre-to-centre), so no line "passes through" a
#     box (no '穿模').  Structural paths that span intermediate latents bow
#     away from them.
#   * Each endogenous observed node carries a small 'e' measurement-error
#     circle with a dashed arrow into the box (the e -> y convention).
#   * Multi-panel specs (``panels``) use plt.subplots(1, N); each panel keeps
#     its own coordinate system so they never interfere.
#   * Pure matplotlib -> fully vector, no graphviz / external binary needed.
# ---------------------------------------------------------------------------

# --- node geometry (single source of truth for sizing & spacing) ---
_SEM_LAT_W, _SEM_LAT_H = 2.2, 1.15     # latent ellipse (full width, height)
_SEM_IND_W, _SEM_IND_H = 1.75, 0.74    # observed rectangle
_SEM_ROW_GAP = 1.32                     # vertical gap between stacked nodes
_SEM_IND_DX = 2.6                        # latent -> its indicator column
_SEM_EXO_DX = 2.8                        # latents column -> exogenous column
_SEM_ERR_DX = 0.62                        # error circle offset past box edge
_SEM_ERR_R = 0.24                         # error circle radius
_SEM_PAD = 0.9                            # outer margin


def _resolve_font():
    """Pick a font that is guaranteed present AND embeds as extractable
    TrueType in the PDF.  Prefer Arial; fall back to a bundled substitute so
    the text layer is always copyable (never a missing-font bitmap)."""
    from matplotlib import font_manager
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ("Arial", "Liberation Sans", "DejaVu Sans"):
        if cand in names:
            return cand
    return "DejaVu Sans"


def _border_point(cx, cy, tx, ty, rx, ry, shape):
    """Point on the (rx, ry) node's border along the ray from its centre
    toward ``(tx, ty)``.  Every arrow starts/ends here -- never in the centre
    -- so lines do not "穿过" the node body."""
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    if shape == "latent":  # ellipse border
        ang = math.atan2(dy, dx)
        return cx + rx * math.cos(ang), cy + ry * math.sin(ang)
    # rectangle: clip the ray to the box border
    if dx == 0:
        return cx, cy + math.copysign(ry, dy)
    if dy == 0:
        return cx + math.copysign(rx, dx), cy
    k = min(rx / abs(dx), ry / abs(dy))
    return cx + dx * k, cy + dy * k


def _draw_node(ax, cx, cy, w, h, fc, label, fs, shape):
    """Draw a latent (ellipse) or observed (rectangle) node centred at
    ``(cx, cy)``."""
    if shape == "latent":
        from matplotlib.patches import Ellipse
        ax.add_patch(Ellipse((cx, cy), w, h, facecolor=fc,
                             edgecolor="black", linewidth=1.1, zorder=3))
    else:
        from matplotlib.patches import Rectangle
        ax.add_patch(Rectangle((cx - w / 2, cy - h / 2), w, h, facecolor=fc,
                               edgecolor="black", linewidth=1.0, zorder=3))
    ax.text(cx, cy, label, ha="center", va="center", fontsize=fs,
            fontweight="normal", zorder=4)


def _arrow(ax, x0, y0, x1, y1, color, lw, ms, rad=0.0):
    """A FancyArrowPatch from border point to border point.  ``rad != 0``
    bows the path so it clears intermediate nodes."""
    from matplotlib.patches import FancyArrowPatch
    cs = "arc3,rad=%.3f" % rad if rad else "arc3,rad=0"
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>",
                                 mutation_scale=ms, color=color, lw=lw,
                                 connectionstyle=cs, zorder=2))


def _disturbance_arc(ax, cx, cy, rx, ry):
    """Small dashed double-headed arc sitting clearly ABOVE the latent
    ellipse, marking its disturbance variance.  Lifted well clear of the
    ellipse border and of every incoming/loading edge."""
    from matplotlib.patches import FancyArrowPatch
    y = cy + ry + 0.22
    ax.add_patch(FancyArrowPatch((cx - rx * 0.32, y), (cx + rx * 0.32, y),
                                 arrowstyle="<->", connectionstyle="arc3,rad=0.45",
                                 linestyle=(0, (3, 2)), color="#777777",
                                 lw=0.9, zorder=1))


def _in_node(x, y, centers, pad=0.12):
    """True if ``(x, y)`` sits inside (or on the border of) any drawn node."""
    for c in centers.values():
        rx, ry = c["rx"], c["ry"]
        if c["shape"] == "latent":
            if ((x - c["x"]) / (rx + pad)) ** 2 + \
               ((y - c["y"]) / (ry + pad)) ** 2 < 1.0:
                return True
        else:
            if abs(x - c["x"]) < rx + pad and abs(y - c["y"]) < ry + pad:
                return True
    return False


def _error_term(ax, cx, cy, rx):
    """Measurement-error term for an ENDOGENOUS observed variable only.

    A small 'e' circle sits to the RIGHT of the box with a dashed arrow
    pointing left *into* the box (the e -> y convention).  Exogenous observed
    variables must NOT get one of these."""
    from matplotlib.patches import Circle, FancyArrowPatch
    ex = cx + rx + _SEM_ERR_DX
    ax.add_patch(Circle((ex, cy), _SEM_ERR_R, facecolor="white",
                        edgecolor="#666666", linewidth=0.9, zorder=3))
    ax.text(ex, cy, "e", ha="center", va="center", fontsize=9,
            color="#666666", zorder=4)
    ax.add_patch(FancyArrowPatch((ex - _SEM_ERR_R, cy), (cx + rx, cy),
                                 arrowstyle="-|>", mutation_scale=9,
                                 linestyle=(0, (3, 2)), color="#666666",
                                 lw=1.0, zorder=2))


def _coef_label(item, standardized, nd=2):
    """Extract a coefficient value to display.  ``item`` may be a scalar or a
    dict with ``estimate`` / ``est`` and optional ``std``.  When ``standardized``
    is requested and a ``std`` is present, the standardised value is shown."""
    if isinstance(item, dict):
        est = item.get("estimate", item.get("est"))
        std = item.get("std")
    else:
        est = item
        std = None
    val = std if (standardized and std is not None) else est
    if val is None:
        return None
    try:
        return f"{float(val):.{nd}f}"
    except (TypeError, ValueError):
        return str(val)


def _bow(A, B, centers, latent_names):
    """Bow factor for a structural path.  When latent nodes sit strictly
    between A and B along the path, curve the arrow (to the LEFT, away from
    the indicator column) so it clears them."""
    ax0, ay0 = A["x"], A["y"]
    ax1, ay1 = B["x"], B["y"]
    lo_x, hi_x = min(ax0, ax1), max(ax0, ax1)
    lo_y, hi_y = min(ay0, ay1), max(ay0, ay1)
    between = 0
    for nm, c in centers.items():
        if nm not in latent_names or c["shape"] != "latent":
            continue
        nx, ny = c["x"], c["y"]
        horiz = (lo_x - 1e-6) < nx < (hi_x + 1e-6)
        vert = (lo_y + 1e-6) < ny < (hi_y - 1e-6)
        if horiz and vert:
            between += 1
    return -0.22 - 0.20 * between


def _layout_sem(spec):
    """Compute deterministic, layered node coordinates.

    Returns ``(centers, bounds, w, h)`` where ``centers`` maps a node name to
    a dict with its geometry + semantic role, and ``bounds`` is
    ``(xmin, xmax, ymin, ymax)`` for the axes limits.
    """
    latents = spec.get("latents") or []
    exogenous = spec.get("exogenous") or []
    n = len(latents)
    max_ind = max([len(l.get("indicators") or []) for l in latents] + [1])

    x_exo = _SEM_PAD + _SEM_EXO_DX / 2 + 0.2
    x_lat = x_exo + _SEM_EXO_DX
    x_ind = x_lat + _SEM_IND_DX

    # Each latent owns a vertical block tall enough for its own indicators;
    # blocks are separated so nothing overlaps.
    block_h = max_ind * _SEM_ROW_GAP + 0.7
    total_h = n * block_h
    y_top = _SEM_PAD + total_h

    centers = {}
    for i, lat in enumerate(latents):
        cy = y_top - i * block_h - block_h / 2
        name = lat["name"]
        centers[name] = dict(x=x_lat, y=cy, rx=_SEM_LAT_W / 2, ry=_SEM_LAT_H / 2,
                             shape="latent", label=lat.get("label") or name)
        ind = lat.get("indicators") or []
        load = lat.get("loadings") or [None] * len(ind)
        m = len(ind)
        for ri, iname in enumerate(ind):
            iy = cy + (m - 1) / 2 * _SEM_ROW_GAP - ri * _SEM_ROW_GAP
            centers[iname] = dict(
                x=x_ind, y=iy, rx=_SEM_IND_W / 2, ry=_SEM_IND_H / 2,
                shape="obs", label=iname,
                loading=load[ri] if ri < len(load) else None, latent=name)

    if exogenous:
        span_top = y_top
        span_bot = (y_top - (n - 1) * block_h - block_h / 2) if n else \
                   (y_top - block_h / 2)
        mid_y = (span_top + span_bot) / 2
        me = len(exogenous)
        for ri, ex in enumerate(exogenous):
            ey = mid_y + (me - 1) / 2 * _SEM_ROW_GAP - ri * _SEM_ROW_GAP
            name = ex.get("name") or ex.get("label") or f"ex{ri}"
            centers[name] = dict(x=x_exo, y=ey, rx=_SEM_IND_W / 2,
                                 ry=_SEM_IND_H / 2, shape="obs",
                                 label=ex.get("label") or name,
                                 exogenous=True)

    xs_r = [c["x"] + c["rx"] for c in centers.values()]
    xs_l = [c["x"] - c["rx"] for c in centers.values()]
    ys_t = [c["y"] + c["ry"] for c in centers.values()]
    ys_b = [c["y"] - c["ry"] for c in centers.values()]
    # rightmost nodes (indicators) carry an error circle further right
    x_max = max(xs_r) + _SEM_ERR_DX + _SEM_ERR_R + 0.3
    x_min = min(xs_l) - 0.3
    y_max = max(ys_t) + 0.5          # room for the disturbance arc
    y_min = min(ys_b) - 0.4
    return centers, (x_min, x_max, y_min, y_max), x_max - x_min, y_max - y_min


def _draw_sem_panel(ax, centers, bounds, spec, opts):
    """Render one SEM panel.  ``centers`` carries geometry; edges are drawn
    border-to-border so no line passes through a node."""
    standardized = opts.get("standardized", False)
    latent_names = {nm for nm, c in centers.items() if c["shape"] == "latent"}

    # 1) nodes -------------------------------------------------------------
    for nm, c in centers.items():
        if c["shape"] == "latent":
            _draw_node(ax, c["x"], c["y"], _SEM_LAT_W, _SEM_LAT_H, "#DCE6F1",
                       c["label"], 10, "latent")
            _disturbance_arc(ax, c["x"], c["y"], c["rx"], c["ry"])
        else:
            _draw_node(ax, c["x"], c["y"], _SEM_IND_W, _SEM_IND_H, "white",
                       c["label"], 9, "obs")
            # exogenous observed variables NEVER get an error circle
            if not c.get("exogenous"):
                _error_term(ax, c["x"], c["y"], c["rx"])

    # 2) loading arrows: latent -> its OWN indicators (end at indicator LEFT
    #    border).  Because indicators sit in a single column to the right of
    #    their latent and arrows are horizontal, none ever crosses a sibling.
    for nm, c in centers.items():
        if c["shape"] == "obs" and not c.get("exogenous") and "latent" in c:
            L = centers[c["latent"]]
            sx, sy = _border_point(L["x"], L["y"], c["x"], c["y"],
                                  L["rx"], L["ry"], "latent")
            ex, ey = c["x"] - c["rx"], c["y"]          # indicator left border
            _arrow(ax, sx, sy, ex, ey, "#404040", 1.1, 13)
            lbl = _coef_label(c.get("loading"), standardized, 2)
            if lbl is not None:
                dxp, dyp = ex - sx, ey - sy
                Lp = math.hypot(dxp, dyp) or 1.0
                px, py = -dyp / Lp, dxp / Lp
                lx, ly = (sx + ex) / 2 + px * 0.16, (sy + ey) / 2 + py * 0.16
                if _in_node(lx, ly, centers):
                    lx, ly = (sx + ex) / 2 - px * 0.18, (sy + ey) / 2 - py * 0.18
                ax.text(lx, ly, lbl, fontsize=10, color="#333333",
                        ha="center", va="center", zorder=5)

    # 3) structural (causal) paths ----------------------------------------
    for p in spec.get("structural_paths") or []:
        a, b = p.get("from"), p.get("to")
        if a not in centers or b not in centers:
            continue
        A, B = centers[a], centers[b]
        sx, sy = _border_point(A["x"], A["y"], B["x"], B["y"], A["rx"], A["ry"],
                               A["shape"])
        ex, ey = _border_point(B["x"], B["y"], A["x"], A["y"], B["rx"], B["ry"],
                               B["shape"])
        rad = _bow(A, B, centers, latent_names)
        _arrow(ax, sx, sy, ex, ey, "#1F4E79", 1.8, 16, rad=rad)
        lbl = _coef_label(p, standardized, 3)
        if lbl is not None:
            sig = p.get("p")
            star = "**" if sig is not None and float(sig) < 0.001 else \
                   ("*" if sig is not None and float(sig) < 0.05 else "")
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            # Offset the label perpendicular to the edge, choosing the side
            # that lands in OPEN space (never on top of a node body).
            dxp, dyp = ex - sx, ey - sy
            Lp = math.hypot(dxp, dyp) or 1.0
            perp_x, perp_y = -dyp / Lp, dxp / Lp
            lx, ly = mx, my
            for sgn in (1, -1):
                cand_x = mx + sgn * perp_x * 0.42
                cand_y = my + sgn * perp_y * 0.42
                if not _in_node(cand_x, cand_y, centers):
                    lx, ly = cand_x, cand_y
                    break
            ax.text(lx, ly, f"{lbl}{star}",
                    fontsize=10, color="#1F4E79",
                    fontweight="bold", ha="center", va="center",
                    bbox=dict(facecolor="white", edgecolor="none",
                              boxstyle="round,pad=0.15", alpha=0.9),
                    zorder=6)

    # panel letter (A, B, C...) for multi-panel figures
    letter = opts.get("letter")
    if letter:
        ax.text(0.06, 0.94, f"({letter})", transform=ax.transAxes,
                ha="left", va="top", fontsize=10, fontweight="bold", zorder=6)

    # fit indices in the lower-right corner
    fit = spec.get("fit_indices") or {}
    fi = []
    if fit:
        for k in ("CFI", "TLI", "RMSEA"):
            if k in fit:
                fi.append(f"{k}={float(fit[k]):.3f}")
        if "chi2" in fit and "df" in fit:
            fi.insert(0, f"chi2={float(fit['chi2']):.1f} (df={int(fit['df'])})")
        if fi:
            # Bottom-LEFT: the lower-left quadrant is always empty (below the
            # exogenous column, left of the indicator column), so the fit box
            # never collides with an indicator box or its error circle.
            ax.text(0.012, 0.03, "  ".join(fi),
                    transform=ax.transAxes, ha="left", va="bottom",
                    fontsize=10, color="#555555", zorder=6,
                    bbox=dict(facecolor="#F7F7F7", edgecolor="#CCCCCC",
                              boxstyle="round,pad=0.3"))

    return centers


def _render_sem_path(plt, spec, out_dir, title=None):
    """Render a structural-equation path diagram (single panel, or a row of
    panels when the spec carries a ``panels`` list).

    Pure matplotlib patches, so the output is fully vector and reproducible
    -- no graphviz, no external binaries.  Indicators fan out to the right of
    each latent so loading arrows never fake an observed-to-observed causal
    chain, and every edge is clipped to a node border.
    """
    _apply_pub_style(plt, table=False)
    # Guarantee an installed, embeddable font and force TrueType embedding so
    # the PDF text layer is extractable / copyable.
    family = _resolve_font()
    plt.rcParams["font.family"] = family
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42
    plt.rcParams["svg.fonttype"] = "none"

    panels = spec.get("panels")
    sub_specs = panels if panels else [spec]
    standardized = spec.get("standardized", False)

    # Independent geometry per panel -> panels never interfere.
    geoms = [_layout_sem(s) for s in sub_specs]
    n = len(sub_specs)
    total_w = sum(g[2] for g in geoms) + 0.6 * (n - 1)
    max_h = max(g[3] for g in geoms)

    # Multi-panel specs explicitly use a single row of N columns.
    fig, axes = plt.subplots(1, n, figsize=(total_w, max_h))
    axes = [axes] if n == 1 else list(axes)
    for idx, s in enumerate(sub_specs):
        ax = axes[idx]
        centers, bounds, w, h = geoms[idx]
        ax.set_xlim(bounds[0], bounds[1])
        ax.set_ylim(bounds[2], bounds[3])
        ax.set_axis_off()
        letter = chr(ord("A") + idx) if n > 1 else None
        _draw_sem_panel(ax, centers, bounds, s,
                        {"standardized": s.get("standardized", standardized),
                         "letter": letter})

    if title:
        fig.suptitle(title, fontsize=12, fontweight="bold")

    pdf_path = os.path.join(out_dir, "sem_path.pdf")
    png_path = os.path.join(out_dir, "sem_path.png")
    try:
        fig.savefig(pdf_path)
        fig.savefig(png_path)
    except Exception as exc:
        plt.close(fig)
        return _verdict("UNVERIFIED", f"failed to save SEM figure: {exc}")
    finally:
        plt.close(fig)

    n_lat = sum(len(s.get("latents") or []) for s in sub_specs)
    n_paths = sum(len(s.get("structural_paths") or []) for s in sub_specs)
    return _verdict(
        "PASS",
        f"SEM path diagram written ({n_lat} latents, {n_paths} "
        f"structural paths, {n} panel(s)): {os.path.basename(pdf_path)}, "
        f"{os.path.basename(png_path)}",
        artifacts=[pdf_path, png_path])
