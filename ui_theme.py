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
    "bg": "#FFFFFF", "panel": "#F5F7FA", "side": "#F0F3F7", "card": "#FFFFFF",
    "field": "#FFFFFF", "border": "#D5DAE1", "plot_grid": "#E7EAF0",
    "text": "#1F2933", "muted": "#52606D",
    "accent": "#1F4E8C", "accent_hover": "#173D6E", "accent_tint": "#E7EEF7",
    "accent_fg": "#FFFFFF",
    "green": "#2E7D32", "green_tint": "#EDF7EF", "green_border": "#BCD9C0",
    "amber": "#B26A00", "amber_text": "#8A5200", "amber_tint": "#FDF6E7",
    "amber_border": "#EBD3A8",
    "red": "#B3261E", "red_tint": "#FBEDEB", "red_border": "#EBB8B3",
    "line": "#8A929E",
    "plot_bg": "#FFFFFF", "plot_ink": "#1F2933", "plot_muted": "#52606D",
}

DARK = {
    "bg": "#14181F", "panel": "#1B212A", "side": "#1B212A", "card": "#1B212A",
    "field": "#1B212A", "border": "#2C3542", "plot_grid": "#232B36",
    "text": "#E6EAF0", "muted": "#A7B1BD",
    "accent": "#6EA8E8", "accent_hover": "#8CBCF0", "accent_tint": "#1D2A3B",
    "accent_fg": "#14181F",
    "green": "#86D292", "green_tint": "#1D2A21", "green_border": "#33503A",
    "amber": "#E5B268", "amber_text": "#E5B268", "amber_tint": "#2A2318",
    "amber_border": "#54452A",
    "red": "#F0908A", "red_tint": "#2B1E1D", "red_border": "#5A3734",
    "line": "#8A93A0",
    "plot_bg": "#FFFFFF", "plot_ink": "#1F2933", "plot_muted": "#52606D",
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
    ("Plot text on plot background", "plot_ink", "plot_bg"),
    ("Plot secondary text on plot background", "plot_muted", "plot_bg"),
]

CSS = Template("""<style>
.stApp, html, body { background:$bg; color:$text;
  font-family:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
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

/* --- inside the app banner: plain header, no icon, no gradient ---------- */
.gl-banner { padding:2px 0 10px; margin-bottom:6px; border-bottom:1px solid $border; }
.gl-banner h1 { margin:0; font-size:22px; font-weight:600; color:$text; }
.gl-banner p { margin:2px 0 0; font-size:13px; color:$muted; }

/* --- sidebar ------------------------------------------------------------ */
[data-testid="stSidebar"] { background:$side; border-right:1px solid $border; }
[data-testid="stSidebar"] [data-testid="stHeading"] p {
  font-size:13px; font-weight:600; color:$muted; }
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
[data-testid="stTab"] { font-size:13.5px; color:$muted; }
[data-testid="stTab"][aria-selected="true"] { color:$accent !important; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] {
  background-color:$accent !important; }

/* --- metric cards: white card, 1px border, no side stripe --------------- */
[class*="st-key-kpi"] { background:$card; border:1px solid $border;
  border-radius:$radius; padding:7px 12px 1px; height:100%; }
[class*="st-key-kpi"] [data-testid="stMetricLabel"] p {
  color:$muted; font-size:12px; font-weight:500; }
[class*="st-key-kpi"] [data-testid="stMetricValue"] {
  color:$text; font-size:1.35rem; font-weight:600; line-height:1.3; }
[class*="st-key-kpi"] [data-testid="stMetricDelta"] {
  color:$muted; font-size:12px; }
[class*="st-key-kpi-bad"] [data-testid="stMetricValue"] { color:$red !important; }

/* --- status badges: small, flat, tinted -------------------------------- */
.gl-badge { display:inline-block; padding:1px 8px; border-radius:$radius;
  font-size:12px; font-weight:600; line-height:1.7; white-space:nowrap;
  border:1px solid transparent; font-family:inherit; }
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
[data-testid="stDataFrame"] { --gdg-font-family:"Inter",system-ui,sans-serif !important;
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


def banner_html():
    return ('<div class="gl-banner"><h1>GridLens</h1>'
            '<p>Power system analysis &middot; load flow &middot; '
            'N-1 contingency &middot; fault study</p></div>')


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
