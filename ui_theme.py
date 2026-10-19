"""GridLens Streamlit helpers: the stylesheet injection and the small HTML
pieces (banner, badge, section label, status bar). The palette and the
matplotlib / Plotly styles live in figures.py."""
from figures import CSS_FILE, mpl_style, plotly_style


def banner_html(readouts=()):
    """Header band; readouts is a list of (label, value) or (label, value,
    css class) shown on the right (class "stale" turns the value amber)."""
    read = "".join(f'<div class="{r[2] if len(r) > 2 else ""}"><span>{r[0]}'
                   f"</span>{r[1]}</div>" for r in readouts)
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
