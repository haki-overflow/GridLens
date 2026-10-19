"""GridLens UI theme: theme.css (KiCad-style dark) -> Streamlit CSS, the
palette dict, matplotlib rcParams and the Plotly template.

Roles, not decoration:
- text/muted  = body and secondary text
- sel/marker  = selected state in UI chrome (greyscale, no blue)
- accent      = charts only (diagram selection highlight)
- green/amber/red = status only (badges, violations, pass/fail), each with a
  dark tinted background and same-hue text that passes WCAG AA
- c1..c6      = plot data colours
"""
import re
from pathlib import Path

CSS_FILE = Path(__file__).with_name("theme.css")


def _palette(css_text):
    """Hex colour variables of the :root block; CSS is the single source of
    truth for every colour."""
    root = css_text.split(":root", 1)[1].split("}", 1)[0]
    return {k.replace("-", "_"): v for k, v in
            re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", root)}


PAL = _palette(CSS_FILE.read_text())
PALETTES = {"dark": PAL}

# Every text/background pair the UI uses; check_contrast.py enforces AA (4.5:1).
CONTRAST_PAIRS = [
    ("Body text on app background", "text", "bg"),
    ("Body text on panel", "text", "panel"),
    ("Body text on sidebar", "text", "side"),
    ("Body text on input field", "text", "field"),
    ("Body text on title strip", "text", "hdr"),
    ("Selected text on selected fill", "sel_text", "sel"),
    ("Body text on hover", "text", "hover"),
    ("Secondary text on app background", "muted", "bg"),
    ("Secondary text on panel", "muted", "panel"),
    ("Secondary text on sidebar", "muted", "side"),
    ("Green status on tinted badge", "green", "green_tint"),
    ("Amber status on tinted badge", "amber", "amber_tint"),
    ("Red status on tinted badge", "red", "red_tint"),
    ("Red status on app background", "red", "bg"),
    ("Plot text on canvas", "text", "canvas"),
    ("Plot secondary text on canvas", "muted", "canvas"),
]


def banner_html(readouts=()):
    """Header band; readouts is a list of (label, value) shown on the right."""
    read = "".join(f"<div><span>{k}</span>{v}</div>" for k, v in readouts)
    return ('<div class="gl-banner"><div><div class="gl-title">GRIDLENS</div>'
            '<div class="gl-sub">Steady-state network study &middot; load '
            'flow &middot; N-1 security &middot; voltage stability &middot; '
            f'fault levels</div></div><div class="gl-read">{read}</div></div>')


def section(text):
    """Small section label in a title strip, as in report printouts."""
    return f'<div class="gl-sec">{text}</div>'


def badge(text, tone="ok"):
    if tone not in ("ok", "bad", "warn", "gray"):
        raise ValueError(f"badge tone must be ok/bad/warn/gray, got {tone!r}")
    return f'<span class="gl-badge {tone}">{text}</span>'


def inspector_html(title, rows):
    """Key/value table for the diagram inspector; rows = [(label, value)]."""
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return (f'{section(title)}<div class="gl-insp"><table>{body}</table>'
            '</div>')


def statusbar_html(items):
    """Fixed bottom status bar; items is a list of (label, value) cells and
    the last cell stretches (use it for the message)."""
    cells = "".join(f"<div><b>{k}</b>{v}</div>" for k, v in items)
    return f'<div class="gl-status">{cells}</div>'


def inject():
    """Stylesheet plus the matplotlib / Plotly styles; call once per run."""
    import streamlit as st
    st.html(f"<style>{CSS_FILE.read_text()}</style>")
    mpl_style()
    plotly_style()


_MPL_READY = False


def mpl_style():
    """Matplotlib rcParams from the palette (dark canvas, thin boxed spines),
    set once."""
    global _MPL_READY
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if _MPL_READY:
        return plt
    p = PAL
    plt.rcParams.update({
        "figure.facecolor": p["canvas"], "axes.facecolor": p["canvas"],
        "savefig.facecolor": p["canvas"], "savefig.edgecolor": p["canvas"],
        "text.color": p["text"], "axes.labelcolor": p["text"],
        "axes.edgecolor": p["axis"], "axes.linewidth": 0.7,
        "xtick.color": p["axis"], "ytick.color": p["axis"],
        "xtick.labelcolor": p["text"], "ytick.labelcolor": p["text"],
        "xtick.direction": "in", "ytick.direction": "in",
        "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "grid.color": p["grid"], "grid.linewidth": 0.5,
        "axes.grid": False, "axes.axisbelow": True,
        "axes.prop_cycle": matplotlib.cycler(color=[
            p["c1"], p["c2"], p["c3"], p["c4"], p["c5"], p["c6"]]),
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Tahoma", "Arial", "Liberation Sans",
                            "DejaVu Sans"],
        "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8.5,
        "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
        "axes.spines.top": True, "axes.spines.right": True,
        "legend.frameon": True, "legend.facecolor": p["canvas"],
        "legend.edgecolor": p["axis"], "legend.fancybox": False,
        "legend.borderpad": 0.4, "figure.dpi": 110,
    })
    _MPL_READY = True
    return plt


def plotly_style():
    """Register the 'gridlens' Plotly template and make it the default."""
    import plotly.graph_objects as go
    import plotly.io as pio
    if pio.templates.default == "gridlens":
        return
    p = PAL
    axis = dict(gridcolor=p["grid"], linecolor=p["axis"], zerolinecolor=p["grid"],
                tickcolor=p["axis"], showline=True, mirror=True)
    pio.templates["gridlens"] = go.layout.Template(layout=dict(
        paper_bgcolor=p["canvas"], plot_bgcolor=p["canvas"],
        font=dict(color=p["text"], size=11,
                  family="Segoe UI, Tahoma, Arial, Liberation Sans, sans-serif"),
        colorway=[p["c1"], p["c2"], p["c3"], p["c4"], p["c5"], p["c6"]],
        xaxis=axis, yaxis=axis,
        hoverlabel=dict(bgcolor=p["panel"], bordercolor=p["axis"],
                        font=dict(color=p["text"], size=11,
                                  family="Consolas, DejaVu Sans Mono, monospace"),
                        align="left"),
        legend=dict(bgcolor=p["canvas"], bordercolor=p["axis"], borderwidth=1,
                    font=dict(size=10))))
    pio.templates.default = "gridlens"
