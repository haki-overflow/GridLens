"""GridLens UI theme: one palette dict -> Streamlit CSS + matplotlib style.

Roles, not decoration:
- text/muted  = body and secondary text
- accent      = the only accent (links, primary buttons, active tabs/selection)
- green/amber/red = status only (badges, violations, pass/fail), each with a
  light tinted background and same-hue text that passes WCAG AA
- line        = plot lines (mid grey)
"""
from string import Template

RADIUS = "4px"

LIGHT = {
    "bg": "#F3F5F7", "panel": "#FFFFFF", "side": "#E9EDF1", "card": "#FFFFFF",
    "field": "#FFFFFF", "border": "#C9D1DA", "plot_grid": "#E3E7EC",
    "text": "#14202B", "muted": "#4A5866",
    "accent": "#0B4F8A", "accent_hover": "#083B68", "accent_tint": "#E2ECF6",
    "accent_fg": "#FFFFFF",
    "green": "#1E6B34", "green_tint": "#E6F2E9", "green_border": "#B3D3BC",
    "amber": "#B26A00", "amber_text": "#7F4C00", "amber_tint": "#FCF3E1",
    "amber_border": "#E7CC98",
    "red": "#B3261E", "red_tint": "#FBEAE8", "red_border": "#E9B3AE",
    "violet": "#6A3FA0",
    "line": "#7D8794",
    "hdr": "#0F1B26", "hdr_text": "#E8EEF4", "hdr_muted": "#9FB0C2",
    "hazard": "#F2B705",
    "plot_bg": "#FFFFFF", "plot_ink": "#14202B", "plot_muted": "#4A5866",
}

DARK = {
    "bg": "#10161D", "panel": "#18212B", "side": "#141C25", "card": "#18212B",
    "field": "#18212B", "border": "#2B3846", "plot_grid": "#232D38",
    "text": "#E3E9EF", "muted": "#A3B0BE",
    "accent": "#6EA8E8", "accent_hover": "#8CBCF0", "accent_tint": "#1B2A3B",
    "accent_fg": "#10161D",
    "green": "#86D292", "green_tint": "#1A2A1F", "green_border": "#33503A",
    "amber": "#E5B268", "amber_text": "#E5B268", "amber_tint": "#2A2318",
    "amber_border": "#54452A",
    "red": "#F0908A", "red_tint": "#2B1E1D", "red_border": "#5A3734",
    "violet": "#B79CE8",
    "line": "#8A93A0",
    "hdr": "#0A1017", "hdr_text": "#E8EEF4", "hdr_muted": "#9FB0C2",
    "hazard": "#F2B705",
    "plot_bg": "#FFFFFF", "plot_ink": "#14202B", "plot_muted": "#4A5866",
}

PALETTES = {"light": LIGHT, "dark": DARK}

# Every text/background pair the UI uses; check_contrast.py enforces AA (4.5:1).
CONTRAST_PAIRS = [
    ("Body text on app background", "text", "bg"),
    ("Body text on panel", "text", "panel"),
    ("Body text on sidebar", "text", "side"),
    ("Body text on metric card", "text", "card"),
    ("Secondary text on app background", "muted", "bg"),
    ("Secondary text on panel", "muted", "panel"),
    ("Secondary text on sidebar", "muted", "side"),
    ("Secondary text on metric card", "muted", "card"),
    ("Accent link on app background", "accent", "bg"),
    ("Accent link on panel", "accent", "panel"),
    ("Accent link on sidebar", "accent", "side"),
    ("Primary button label on accent", "accent_fg", "accent"),
    ("Green status on tinted badge", "green", "green_tint"),
    ("Green status on app background", "green", "bg"),
    ("Amber status on tinted badge", "amber_text", "amber_tint"),
    ("Amber status on app background", "amber_text", "bg"),
    ("Red status on tinted badge", "red", "red_tint"),
    ("Red status on app background", "red", "bg"),
    ("Header text on header band", "hdr_text", "hdr"),
    ("Header secondary text on header band", "hdr_muted", "hdr"),
    ("Plot text on plot background", "plot_ink", "plot_bg"),
    ("Plot secondary text on plot background", "plot_muted", "plot_bg"),
]

CSS = Template("""<style>
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap");
.stApp, html, body { background:$bg; color:$text;
  font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
[data-testid="stHeader"] { background:transparent; }
[data-testid="stMainBlockContainer"] { padding-top:1.1rem; padding-bottom:2rem; }
[data-testid="stVerticalBlock"] { gap:0.55rem; }
h1,h2,h3,h4,h5,[data-testid="stHeading"] p {
  color:$text; font-weight:600; letter-spacing:0; text-transform:none; }
[data-testid="stCaptionContainer"] p,[data-testid="stCaptionContainer"] {
  color:$muted !important; font-size:12.5px; }
a, a:visited { color:$accent; }
[data-testid="stMarkdownContainer"] code, code, pre, kbd {
  font-family:ui-monospace,"Cascadia Mono",Menlo,Consolas,monospace;
  font-size:12.5px; background:$panel; color:$text; border-radius:$radius; }

/* --- header band: control-room bar with a hazard-yellow rule ------------ */
.gl-banner { display:flex; justify-content:space-between; align-items:center;
  flex-wrap:wrap; gap:8px 24px; background:$hdr; color:$hdr_text;
  padding:10px 16px; border-radius:$radius; border-bottom:3px solid $hazard;
  margin-bottom:4px; }
.gl-banner .gl-title { font-size:17px; font-weight:700; letter-spacing:.14em; }
.gl-banner .gl-sub { font-size:12px; color:$hdr_muted; letter-spacing:.02em; }
.gl-banner .gl-read { display:flex; gap:18px; flex-wrap:wrap; }
.gl-banner .gl-read div { font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:12.5px; color:$hdr_text; }
.gl-banner .gl-read span { display:block; font-family:"IBM Plex Sans",sans-serif;
  font-size:10px; color:$hdr_muted; text-transform:uppercase; letter-spacing:.08em; }
.gl-sec { font-size:11px; font-weight:600; color:$muted; text-transform:uppercase;
  letter-spacing:.09em; border-bottom:1px solid $border; padding-bottom:3px;
  margin:6px 0 2px; }

/* --- sidebar ------------------------------------------------------------ */
[data-testid="stSidebar"] { background:$side; border-right:1px solid $border; }
[data-testid="stSidebar"] [data-testid="stHeading"] p,
[data-testid="stSidebar"] h2 {
  font-size:11px !important; font-weight:600; color:$muted;
  text-transform:uppercase; letter-spacing:.09em; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:$text; }

/* --- buttons: flat, 4px radius, no glow --------------------------------- */
.stButton button, .stDownloadButton button {
  border-radius:$radius !important; box-shadow:none !important; font-weight:500; }
[data-testid="stBaseButton-primary"] { background:$accent !important;
  border:1px solid $accent !important; color:$accent_fg !important; }
[data-testid="stBaseButton-primary"]:hover { background:$accent_hover !important;
  border-color:$accent_hover !important; }
[data-testid="stBaseButton-secondary"],[data-testid="stBaseButton-tertiary"] {
  background:$field !important; border:1px solid $border !important;
  color:$text !important; }
[data-testid="stBaseButton-secondary"]:hover,[data-testid="stBaseButton-tertiary"]:hover {
  border-color:$accent !important; color:$accent !important; }

/* --- segmented control: one row, compact -------------------------------- */
[data-testid="stButtonGroup"] { flex-wrap:nowrap !important; gap:2px !important; }
[data-testid="stButtonGroup"] button { padding:2px 9px !important;
  min-height:1.7rem !important; border-radius:$radius !important; }
[data-testid="stButtonGroup"] button p { font-size:12.5px !important;
  white-space:nowrap !important; }
[data-testid="stBaseButton-segmented_control"] { background:transparent !important;
  border:1px solid transparent !important; color:$text !important; }
[data-testid="stBaseButton-segmented_control-active"] {
  background:$accent_tint !important; border:1px solid $accent !important;
  color:$accent !important; }
[data-testid="stBaseButton-pills"],[data-testid="stBaseButton-pills-active"] {
  border-radius:$radius !important; }
[data-testid="stBaseButton-pills-active"] { background:$accent_tint !important;
  border:1px solid $accent !important; color:$accent !important; }

/* --- tabs: accent underline, no pill chrome ----------------------------- */
[data-testid="stTab"] p { font-size:11.5px; color:$muted; font-weight:600;
  text-transform:uppercase; letter-spacing:.07em; }
[data-testid="stTab"][aria-selected="true"] p { color:$accent !important; }
[data-testid="stTab"][aria-selected="true"] { color:$accent !important; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] {
  background-color:$accent !important; }

/* --- metric cards: white card, 1px border, no side stripe --------------- */
[class*="st-key-kpi"] { background:$card; border:1px solid $border;
  border-top:2px solid $accent; border-radius:$radius; padding:6px 12px 1px;
  height:100%; }
[class*="st-key-kpi-bad"] { border-top-color:$red; }
[class*="st-key-kpi"] [data-testid="stMetricLabel"] p {
  color:$muted; font-size:10.5px; font-weight:600; text-transform:uppercase;
  letter-spacing:.07em; }
[class*="st-key-kpi"] [data-testid="stMetricValue"] {
  color:$text; font-size:1.25rem; font-weight:500; line-height:1.3;
  font-family:"IBM Plex Mono",ui-monospace,monospace; }
[class*="st-key-kpi"] [data-testid="stMetricDelta"] {
  color:$muted; font-size:12px; }
[class*="st-key-kpi-bad"] [data-testid="stMetricValue"] { color:$red !important; }

/* --- status badges: small, flat, tinted -------------------------------- */
.gl-badge { display:inline-block; padding:1px 8px; border-radius:2px;
  font-size:11px; font-weight:600; line-height:1.8; white-space:nowrap;
  border:1px solid transparent; font-family:"IBM Plex Mono",ui-monospace,monospace;
  text-transform:uppercase; letter-spacing:.04em; }
.gl-badge.ok { background:$green_tint; color:$green; border-color:$green_border; }
.gl-badge.bad { background:$red_tint; color:$red; border-color:$red_border; }
.gl-badge.warn { background:$amber_tint; color:$amber_text; border-color:$amber_border; }
.gl-badge.gray { background:$panel; color:$muted; border-color:$border; }

/* --- alerts, expander, popover, uploader -------------------------------- */
[data-testid="stAlertContainer"] { border-radius:$radius !important; }
[data-testid="stExpander"] details, [data-testid="stExpander"] {
  border-radius:$radius !important; border-color:$border !important; }
[data-testid="stFileUploaderDropzone"] { background:$panel;
  border:1px dashed $border; border-radius:$radius; }

/* --- inputs and popovers ------------------------------------------------ */
[data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
  background-color:$field !important; border-color:$border !important;
  color:$text !important; border-radius:$radius !important; }
[data-baseweb="popover"] [role="listbox"], [data-baseweb="popover"] ul {
  background-color:$card !important; color:$text !important; }
[role="option"][aria-selected="true"] { background-color:$accent_tint !important;
  color:$accent !important; }

/* --- data grids: 13px, light rules, no heavy chrome --------------------- */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { font-size:13px; }
[data-testid="stDataFrame"] { --gdg-font-family:"IBM Plex Mono",ui-monospace,monospace !important;
  --gdg-header-font-style:600 11px !important;
  --gdg-editor-font-size:13px !important; --gdg-bg-cell:$field !important;
  --gdg-bg-header:$panel !important; --gdg-bg-header-hovered:$panel !important;
  --gdg-text-header:$muted !important; --gdg-text-dark:$text !important;
  --gdg-text-medium:$text !important; --gdg-border-color:$border !important;
  --gdg-horizontal-border-color:$plot_grid !important; --gdg-accent-color:$accent !important;
  --gdg-accent-light:$accent_tint !important; --gdg-link-color:$accent !important; }

/* --- selection controls follow the accent ------------------------------- */
[data-testid="stCheckbox"] input:checked + span,
[data-testid="stToggle"] input:checked + span,
[data-testid="stToggle"] input:checked + div,
[data-testid="stRadioOption"] input:checked + span {
  background-color:$accent !important; border-color:$accent !important; }
$extra
</style>""")

_DARK_EXTRA = """/* dark surfaces for widgets Streamlit tints from its compiled theme */
[data-testid="stAlertContainer"] { background-color:$panel !important;
  border:1px solid $border !important; color:$text !important; }
[data-testid="stAlertContainer"] p { color:$text !important; }
[data-testid="stHeader"] { background:transparent !important; }
"""


def css(dark=False):
    """Full stylesheet for the chosen palette (colors live only in the dicts)."""
    pal = DARK if dark else LIGHT
    values = dict(pal)
    values["radius"] = RADIUS
    values["extra"] = Template(_DARK_EXTRA).substitute(values) if dark else ""
    return CSS.substitute(values)


def banner_html(readouts=()):
    """Header band; readouts is a list of (label, value) shown on the right."""
    read = "".join(f"<div><span>{k}</span>{v}</div>" for k, v in readouts)
    return ('<div class="gl-banner"><div><div class="gl-title">GRIDLENS</div>'
            '<div class="gl-sub">Steady-state network study &middot; load '
            'flow &middot; N-1 security &middot; voltage stability &middot; '
            f'fault levels</div></div><div class="gl-read">{read}</div></div>')


def section(text):
    """Small uppercase section label with a rule, as in report printouts."""
    return f'<div class="gl-sec">{text}</div>'


def badge(text, tone="ok"):
    if tone not in ("ok", "bad", "warn", "gray"):
        raise ValueError(f"badge tone must be ok/bad/warn/gray, got {tone!r}")
    return f'<span class="gl-badge {tone}">{text}</span>'


def inject(dark=None):
    import streamlit as st
    if dark is None:
        dark = bool(st.session_state.get("dark_theme", False))
    st.html(css(dark))


def mpl_style():
    """Matplotlib rcParams from the palette; figures stay light for export."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    p = LIGHT
    plt.rcParams.update({
        "figure.facecolor": p["plot_bg"], "axes.facecolor": p["plot_bg"],
        "savefig.facecolor": p["plot_bg"], "savefig.edgecolor": p["plot_bg"],
        "text.color": p["plot_ink"], "axes.labelcolor": p["plot_muted"],
        "axes.edgecolor": p["border"],
        "xtick.color": p["plot_muted"], "ytick.color": p["plot_muted"],
        "xtick.labelcolor": p["plot_ink"], "ytick.labelcolor": p["plot_ink"],
        "grid.color": p["plot_grid"], "grid.linewidth": 0.7,
        "axes.grid": False, "axes.axisbelow": True,
        "font.family": "sans-serif",
        "font.sans-serif": ["Inter", "DejaVu Sans", "Segoe UI", "sans-serif"],
        "font.size": 9,
        "axes.labelsize": 9, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "legend.facecolor": p["plot_bg"],
        "figure.dpi": 110,
    })
    return plt
