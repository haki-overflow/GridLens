"""GridLens figures: the palette, matplotlib / Plotly styles, the matplotlib
charts and the interactive one-line diagram. Streamlit-free, so the API server
can import it. Colours come only from theme.css (:root), the single source.

Roles, not decoration:
- text/muted  = body and secondary text
- accent      = the one strong accent: active page, primary buttons,
                selected options, focus (accent_strong = primary fill)
- hazard      = yellow rule under the header
- green/amber/red = status only (badges, violations, pass/fail), each with a
  dark tinted background and same-hue text that passes WCAG AA
- c1..c6      = plot data colours

Sections: palette -> matplotlib / Plotly styles -> matplotlib charts ->
one-line diagram (Plotly).
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

# ====================================================================== palette
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
    ("Primary button text on its fill", "accent_fg", "accent_strong"),
    ("Title on header band", "sel_text", "hdr"),
    ("STALE / amber on header band", "amber", "hdr"),
    ("Amber note on app background", "amber", "bg"),
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


# ================================================== matplotlib / Plotly styles
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


P = PAL   # short alias used by the charts and the diagram


# ============================================================ matplotlib charts
# All charts share the palette: dark canvas, thin boxed axis, cyan data, red only
# for limit violations and limits.

def voltage_profile(res, vmin, vmax):
    """Bus |V| bars in the accent colour, dashed red limit lines."""
    plt = mpl_style()
    x = res["Bus"].to_numpy(dtype=float)
    v = res["V (pu)"].to_numpy(dtype=float)
    lo = min(vmin, v.min()) - 0.015
    hi = max(vmax, v.max()) + 0.025
    fig, ax = plt.subplots(figsize=(7, 3.0))
    ax.bar(x, v - lo, bottom=lo, width=0.6, zorder=2,
           color=[P["red"] if (y < vmin or y > vmax) else P["c1"]
                  for y in v])
    for lim, name, va in ((vmax, "Vmax", "bottom"), (vmin, "Vmin", "top")):
        ax.axhline(lim, color=P["red"], linestyle="--", lw=1, zorder=3)
        ax.text(x.max() + 1.45, lim, f"{name} {lim:.2f} ", color=P["red"],
                fontsize=7.5, ha="right", va=va, zorder=4)
    ax.set_xticks(x.astype(int))
    ax.set_xlim(x.min() - 0.6, x.max() + 1.5)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Bus")
    ax.set_ylabel("|V| (pu)")
    ax.grid(axis="y", color=P["grid"], lw=0.7, zorder=0)
    fig.tight_layout()
    return fig


def convergence_history(hist):
    """Semilogy mismatch error per iteration (NaN sweep-inits are skipped)."""
    plt = mpl_style()
    h = np.asarray(list(hist), dtype=float)
    it = np.arange(1, len(h))
    y = h[1:]
    keep = np.isfinite(y) & (y > 0)
    fig, ax = plt.subplots(figsize=(7, 3.0))
    if keep.any():
        ax.semilogy(it[keep], y[keep], color=P["c1"], lw=1.8, marker="o",
                    ms=3.5)
    ax.set_xlim(0.5, max(len(h) - 0.5, 1.5))
    ax.set_xticks(np.arange(1, max(len(h), 2)).astype(int))
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Max mismatch (pu)")
    ax.grid(color=P["grid"], lw=0.7)
    fig.tight_layout()
    return fig


def fault_voltages(v_pu, vmin, vmax):
    """Bar chart of post-fault |V| magnitudes (v_pu: Series indexed by bus)."""
    plt = mpl_style()
    x = v_pu.index.to_numpy(dtype=float)
    y = v_pu.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(7, 3.0))
    ax.bar(x, y, width=0.6, color=P["c1"], zorder=2)
    top = max(y.max() * 1.15, 0.05)
    if vmin <= top:     # limit line only when the data reaches near it
        ax.axhline(vmin, color=P["red"], linestyle="--", lw=1, zorder=3)
        ax.text(x.max() + 1.45, vmin, f"Vmin {vmin:.2f} ", color=P["red"],
                fontsize=7.5, ha="right", va="bottom", zorder=4)
    for xi, yi in zip(x, y):   # the faulted bus collapses to ~0 pu
        if yi < top * 0.02:
            ax.text(xi, top * 0.02, "fault", ha="center", va="bottom",
                    fontsize=7.5, color=P["red"], zorder=4)
    ax.set_xticks(x.astype(int))
    ax.set_xlim(x.min() - 0.6, x.max() + 1.5)
    ax.set_ylim(0, top)
    ax.set_xlabel("Bus")
    ax.set_ylabel("Post-fault |V| (pu)")
    ax.grid(axis="y", color=P["grid"], lw=0.7, zorder=0)
    fig.tight_layout()
    return fig


def pv_curves(pv, lam_max, vmin, highlight=3):
    """P-V (nose) curves: |V| vs load multiplier; the weakest buses in
    red/cyan, the rest dim grey, base case and last solvable point marked.
    Buses with a held voltage (Slack, PV) are flat lines and are left out."""
    plt = mpl_style()
    lam = pv["lambda"].to_numpy(dtype=float)
    V = pv.drop(columns="lambda")
    V = V.loc[:, (V.max() - V.min()) > 1e-6]
    weak = V.iloc[-1].nsmallest(highlight).index
    fig, ax = plt.subplots(figsize=(7, 3.0))
    for c in V.columns:
        if c not in weak:
            ax.plot(lam, V[c], color=P["axis"], lw=1.2, zorder=1)
    for c, col in zip(weak, (P["red"], P["c1"], P["text"])):
        ax.plot(lam, V[c], color=col, lw=1.9, label=c, zorder=3)
    ax.set_xlim(lam.min(), lam_max * 1.04)
    lo, hi = min(V.values.min(), vmin) - 0.03, V.values.max() + 0.04
    ax.set_ylim(lo, hi)
    ax.axvline(1.0, color=P["text"], lw=0.9, ls=":", zorder=2)
    ax.text(1.0, hi - 0.01, " base case", fontsize=8, va="top",
            color=P["text"])
    ax.axvline(lam_max, color=P["red"], lw=0.9, ls="--", zorder=2)
    ax.text(lam_max, lo + 0.01, f"\u03bb max {lam_max:.2f} ",
            fontsize=8, ha="right", va="bottom", color=P["red"])
    ax.axhline(vmin, color=P["red"], lw=0.8, ls=(0, (2, 3)), alpha=0.6)
    ax.set_xlabel("Load multiplier \u03bb (all loads and generation)")
    ax.set_ylabel("|V| (pu)")
    ax.grid(color=P["grid"], lw=0.7)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    return fig


# ================================================= one-line diagram (Plotly)
# Interactive single-line diagram (Plotly), IEEE/IEC style.
# 
# Buses are horizontal busbars. A branch is a straight line when the two bars
# overlap horizontally (vertical drop) or sit on the same row (end to end),
# otherwise one elbow: down from the upper bar, across into the end of the
# lower bar. Parallel branches get a small fixed offset.
# 
# Positions come from, in order: bus columns `x`, `y` (diagram units, y grows
# downward; whole numbers are read as grid column / row), the `coords` passed
# in (layout of a preset case), else a layered layout: rows by BFS depth from
# the slack, order by neighbour barycenter (deterministic).

GAP_X = 3.0       # between bars in the layered fallback
ROW_Y = 5.0       # between rows
GRID_X, GRID_Y = 7.0, 5.0   # grid column / row size for whole-number x, y
LABEL_W = 2.8     # left part of a bar kept free of top ports (bus label)
END_W = 1.0       # corner kept for the generator / load symbol
PORT_GAP = 0.7
SYM = 0.45        # symbol inset from the bar end
BANDS = (("normal", "text"), ("near limit", "amber"),
         ("low", "red"), ("high", "violet"))
MONO = "Consolas, DejaVu Sans Mono, monospace"


def bar_width(deg):
    return max(4.2, PORT_GAP * deg + LABEL_W + END_W + 0.4)


def _band(v, vmin, vmax, margin=0.02):
    if v < vmin:
        return "low"
    if v > vmax:
        return "high"
    if v < vmin + margin or v > vmax - margin:
        return "near limit"
    return "normal"


# ------------------------------------------------------------------ layout
def _depths(n, edges, root):
    adj = [[] for _ in range(n)]
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    d = [-1] * n
    d[root] = 0
    queue = [root]
    for u in queue:
        for w in adj[u]:
            if d[w] < 0:
                d[w] = d[u] + 1
                queue.append(w)
    return [x if x >= 0 else max(d) + 1 for x in d]


def _layered(n, edges, types, width):
    """Rows by BFS depth from the slack, order inside a row by the mean x
    of the neighbours (a few sweeps), rows centred."""
    root = next((i for i, t in enumerate(types) if t == "Slack"), 0)
    row = _depths(n, edges, root)
    R = max(row) + 1
    rows = [[i for i in range(n) if row[i] == r] for r in range(R)]
    nbr = [[] for _ in range(n)]
    for a, b in edges:
        if row[a] != row[b]:
            nbr[a].append(b)
            nbr[b].append(a)
    cx = np.zeros(n)

    def place(buses):
        total = sum(width[i] for i in buses) + GAP_X * (len(buses) - 1)
        x = -total / 2
        for i in buses:
            cx[i] = x + width[i] / 2
            x += width[i] + GAP_X

    for r in range(R):
        place(rows[r])
    for _ in range(4):
        for r in list(range(1, R)) + list(range(R - 2, -1, -1)):
            key = {i: (np.mean([cx[j] for j in nbr[i]]) if nbr[i] else cx[i])
                   for i in rows[r]}
            rows[r].sort(key=lambda i: (key[i], i))
            place(rows[r])
    return cx, np.array(row, float) * ROW_Y


def _xy_columns(bus, n):
    if bus is None or len(bus) != n:
        return None
    cols = {str(c).lower(): c for c in bus.columns}
    if "x" not in cols or "y" not in cols:
        return None
    xy = bus[[cols["x"], cols["y"]]].apply(pd.to_numeric, errors="coerce")
    if xy.isna().any().any():
        return None
    xy = xy.to_numpy(dtype=float)
    if np.allclose(xy, np.round(xy)):
        xy = xy * [GRID_X, GRID_Y]
    return xy


def layout(n, edges, bus=None, coords=None):
    """Bar centres (cx, cy; cy grows downward), widths and one polyline per
    branch. Returns dict(cx, cy, w, routes)."""
    deg = np.zeros(n, int)
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1
    w = np.array([bar_width(d) for d in deg])
    xy = _xy_columns(bus, n)
    if xy is None and coords is not None and len(coords) == n:
        xy = np.asarray(coords, float)
    if xy is not None:
        cx, cy = xy[:, 0].copy(), xy[:, 1].copy()
    else:
        types = bus["Type"].to_numpy() if bus is not None else [""] * n
        cx, cy = _layered(n, edges, types, w)
    L, R = cx - w / 2, cx + w / 2

    def free_h(y, x0, x1, skip):
        x0, x1 = min(x0, x1) - 0.2, max(x0, x1) + 0.2
        return not any(abs(cy[i] - y) < 0.5 and L[i] < x1 and R[i] > x0
                       for i in range(n) if i not in skip)

    def free_v(x, y0, y1, skip):
        y0, y1 = min(y0, y1), max(y0, y1)
        return not any(y0 < cy[i] < y1 and L[i] - 0.2 < x < R[i] + 0.2
                       for i in range(n) if i not in skip)

    def zone(i, side):        # where ports may sit on a bar side
        if side == "up":
            return L[i] + LABEL_W, R[i] - END_W
        return L[i] + END_W, R[i] - 0.5

    def clamp(x, i, side):
        z0, z1 = zone(i, side)
        return min(max(x, z0), z1)

    # kind per edge: "h" end to end, "v" straight drop, "a" down-then-across,
    # "b" across-then-down; want[(bus, side)] = [(desired x, edge)]
    kind, want = [], {}
    for k, (a, b) in enumerate(edges):
        if abs(cy[a] - cy[b]) < 0.5:
            kind.append("h")
            continue
        up, lo = (a, b) if cy[a] < cy[b] else (b, a)
        z0 = max(zone(up, "dn")[0], zone(lo, "up")[0])
        z1 = min(zone(up, "dn")[1], zone(lo, "up")[1])
        both = {up, lo}
        if z1 > z0 and free_v((z0 + z1) / 2, cy[up], cy[lo], both):
            x = (z0 + z1) / 2
            kind.append("v")
            want.setdefault((up, "dn"), []).append((x, k))
            want.setdefault((lo, "up"), []).append((x, k))
            continue
        xa = clamp(cx[lo], up, "dn")
        end_lo = L[lo] if xa < cx[lo] else R[lo]
        xb = clamp(cx[up], lo, "up")
        end_up = L[up] if xb < cx[up] else R[up]
        if free_v(xa, cy[up], cy[lo], both) and free_h(cy[lo], xa, end_lo, {lo}):
            kind.append("a")
            want.setdefault((up, "dn"), []).append((xa, k))
        elif free_h(cy[up], end_up, xb, {up}) and free_v(xb, cy[up], cy[lo], both):
            kind.append("b")
            want.setdefault((lo, "up"), []).append((xb, k))
        else:                 # crowded: straight line between two ports
            kind.append("v")
            want.setdefault((up, "dn"), []).append((xa, k))
            want.setdefault((lo, "up"), []).append((xb, k))

    port = {}
    for (i, side), lst in want.items():
        lst = sorted(lst)
        lo_x, hi_x = zone(i, side)
        xs = [min(max(x, lo_x), hi_x) for x, _ in lst]
        for j in range(1, len(xs)):
            xs[j] = max(xs[j], xs[j - 1] + PORT_GAP)
        over = xs[-1] - hi_x
        if over > 0:
            xs = [x - over for x in xs]
        for x, (_, k) in zip(xs, lst):
            port[(k, i)] = x

    pair_seen, routes = {}, []
    for k, (a, b) in enumerate(edges):
        key = (min(a, b), max(a, b))
        nth = pair_seen.get(key, 0)
        pair_seen[key] = nth + 1
        off = 0.22 * nth
        if kind[k] == "h":
            le, ri = (a, b) if cx[a] < cx[b] else (b, a)
            routes.append([(R[le], cy[a] + off), (L[ri], cy[a] + off)])
            continue
        up, lo = (a, b) if cy[a] < cy[b] else (b, a)
        if kind[k] == "v":
            routes.append([(port[(k, up)], cy[up]), (port[(k, lo)], cy[lo])])
        elif kind[k] == "a":
            x = port[(k, up)]
            if L[lo] <= x <= R[lo]:       # the drop lands on the lower bar
                routes.append([(x, cy[up]), (x, cy[lo])])
                continue
            end = L[lo] if x < cx[lo] else R[lo]
            routes.append([(x, cy[up]), (x, cy[lo] + off), (end, cy[lo] + off)])
        else:
            x = port[(k, lo)]
            if L[up] <= x <= R[up]:
                routes.append([(x, cy[up]), (x, cy[lo])])
                continue
            end = L[up] if x < cx[up] else R[up]
            routes.append([(end, cy[up] + off), (x, cy[up] + off), (x, cy[lo])])
    return dict(cx=cx, cy=cy, w=w, routes=routes)


def _along(pts, step=0.8):
    """Points every `step` along a polyline (hover / click targets)."""
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        m = max(int(np.hypot(x1 - x0, y1 - y0) / step), 1)
        out += [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
                for t in np.linspace(0, 1, m + 1)[:-1]]
    return out + [pts[-1]]


def _midpoint(pts):
    """Point at half the length of a polyline and the direction there."""
    seg = [np.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:])]
    half, acc = sum(seg) / 2, 0.0
    for s, (p, q) in zip(seg, zip(pts, pts[1:])):
        if acc + s >= half:
            t = (half - acc) / (s or 1)
            return ((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t),
                    np.subtract(q, p) / (s or 1))
        acc += s
    return pts[-1], np.array([1.0, 0.0])


# ------------------------------------------------------------------ data
def bus_info(res, bus, base):
    """Per-bus values for hover and the inspector (MW / MVAr)."""
    n = len(res)
    types = bus["Type"].to_numpy() if bus is not None else np.full(n, "PQ")
    pd_ = bus["Pd"].to_numpy(float) * base if bus is not None else np.zeros(n)
    qd_ = bus["Qd"].to_numpy(float) * base if bus is not None else np.zeros(n)
    out = []
    for i in range(n):
        gen = types[i] != "PQ"
        out.append(dict(
            bus=i + 1, type=types[i], v=float(res["V (pu)"].iloc[i]),
            ang=float(res["Angle (deg)"].iloc[i]),
            pg=float(res["P_inj"].iloc[i]) * base + pd_[i] if gen else 0.0,
            qg=float(res["Q_inj"].iloc[i]) * base + qd_[i] if gen else 0.0,
            pl=float(pd_[i]), ql=float(qd_[i])))
    return out


def line_info(lines, flows, base, tripped=None):
    """Per-line values (MW / MVAr / MVA); flows lacks the tripped line."""
    fl = flows
    if fl is not None and tripped is not None:
        fl = pd.concat([fl.iloc[:tripped], fl.iloc[:0].reindex([0]),
                        fl.iloc[tripped:]])
    rows = []
    for k, (f, t) in enumerate(zip(lines["From"], lines["To"])):
        r = dict(k=k, name=f"{int(f)}-{int(t)}", frm=int(f), to=int(t),
                 tap=float(lines["Tap"].iloc[k]) if "Tap" in lines else 1.0,
                 out=k == tripped)
        if fl is not None and len(fl) == len(lines) and k != tripped:
            v = fl.iloc[k][["P_ij", "Q_ij", "P_ji", "Q_ji", "Loss_P",
                            "Loss_Q"]].to_numpy(float) * base
            r.update(pij=v[0], qij=v[1], pji=v[2], qji=v[3], lp=v[4], lq=v[5],
                     sij=float(np.hypot(v[0], v[1])),
                     sji=float(np.hypot(v[2], v[3])))
        rows.append(r)
    return rows


def _bus_hover(b):
    s = (f"<b>Bus {b['bus']}</b> ({b['type']})<br>|V| {b['v']:.4f} pu"
         f"<br>angle {b['ang']:.2f}°")
    if b["type"] != "PQ":
        s += f"<br>gen  {b['pg']:.1f} MW  {b['qg']:.1f} MVAr"
    if b["pl"] or b["ql"]:
        s += f"<br>load {b['pl']:.1f} MW  {b['ql']:.1f} MVAr"
    return s


def _line_hover(r):
    s = f"<b>Line {r['name']}</b>" + (f"  tap {r['tap']:g}" if r["tap"] != 1 else "")
    if r["out"]:
        return s + "<br>OUT OF SERVICE"
    if "pij" in r:
        s += (f"<br>{r['frm']}→{r['to']}: {r['pij']:.1f} MW  {r['qij']:.1f} MVAr"
              f"  ({r['sij']:.1f} MVA)"
              f"<br>{r['to']}→{r['frm']}: {r['pji']:.1f} MW  {r['qji']:.1f} MVAr"
              f"  ({r['sji']:.1f} MVA)"
              f"<br>loss {r['lp']:.2f} MW  {r['lq']:.2f} MVAr")
    return s


# ------------------------------------------------------------------ figure
def figure(res, lines, vmin, vmax, flows=None, base=100.0, bus=None,
           coords=None, show=None, tripped=None, selected=None, height=None):
    """Plotly one-line diagram.

    show: subset of {"flows", "angles", "loads", "gens", "breakers"}.
    selected: ("bus", i) or ("line", k) to highlight. Click targets carry
    customdata [kind, index]."""
    import plotly.graph_objects as go
    plotly_style()
    show = {"loads", "gens"} if show is None else set(show)
    n = len(res)
    edges = [(int(a) - 1, int(b) - 1) for a, b in zip(lines["From"], lines["To"])]
    g = layout(n, edges, bus, coords)
    cx, cy, w, routes = g["cx"], g["cy"], g["w"], g["routes"]
    Y = -cy                                   # plot y grows upward
    binfo = bus_info(res, bus, base)
    linfo = line_info(lines, flows, base, tripped)
    ink = P["text"]
    fig = go.Figure()

    def poly(pts_list, **kw):
        xs, ys = [], []
        for pts in pts_list:
            xs += [p[0] for p in pts] + [None]
            ys += [-p[1] for p in pts] + [None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip",
                                 showlegend=False, **kw))

    poly([r for k, r in enumerate(routes) if k != tripped],
         line=dict(color=P["muted"], width=1.4))
    if tripped is not None:
        poly([routes[tripped]], line=dict(color=P["red"], width=1.4, dash="dash"))

    # symbols: generator stems + circles, load arrows, transformers, breakers
    stems, gx, gy, lx, ly = [], [], [], [], []
    for i, b in enumerate(binfo):
        if "gens" in show and b["type"] != "PQ":
            x = cx[i] + w[i] / 2 - SYM
            stems.append([(x, cy[i]), (x, cy[i] - 0.7)])
            gx.append(x)
            gy.append(Y[i] + 1.15)
        if "loads" in show and (b["pl"] > 0 or b["ql"] > 0):
            x = cx[i] - w[i] / 2 + SYM
            stems.append([(x, cy[i]), (x, cy[i] + 0.9)])
            lx.append(x)
            ly.append(Y[i] - 1.05)
    if stems:
        poly(stems, line=dict(color=ink, width=1.2))
    if gx:
        fig.add_trace(go.Scatter(
            x=gx, y=gy, mode="markers+text", text=["G"] * len(gx),
            textfont=dict(size=9, color=ink), hoverinfo="skip", showlegend=False,
            marker=dict(symbol="circle", size=17, color=P["canvas"],
                        line=dict(color=ink, width=1.2))))
    if lx:
        fig.add_trace(go.Scatter(
            x=lx, y=ly, mode="markers", hoverinfo="skip", showlegend=False,
            marker=dict(symbol="triangle-down", size=9, color=ink)))
    tx, ty, bx, by = [], [], [], []
    for k, (r, pts) in enumerate(zip(linfo, routes)):
        if abs(r["tap"] - 1) > 1e-9:
            (mx, my), d = _midpoint(pts)
            for s in (-0.22, 0.22):
                tx.append(mx + s * d[0])
                ty.append(-(my + s * d[1]))
        if "breakers" in show and k != tripped:
            for (x0, y0), (x1, y1) in ((pts[0], pts[1]), (pts[-1], pts[-2])):
                d = np.subtract((x1, y1), (x0, y0))
                d = d / (np.hypot(*d) or 1)
                bx.append(x0 + 0.5 * d[0])
                by.append(-(y0 + 0.5 * d[1]))
    if tx:
        fig.add_trace(go.Scatter(
            x=tx, y=ty, mode="markers", hoverinfo="skip", showlegend=False,
            marker=dict(symbol="circle-open", size=15, color=ink,
                        line=dict(width=1.3))))
    if bx:
        fig.add_trace(go.Scatter(
            x=bx, y=by, mode="markers", hoverinfo="skip", showlegend=False,
            marker=dict(symbol="square", size=7, color=P["canvas"],
                        line=dict(color=ink, width=1))))

    # busbars, one trace per voltage band (these make the legend)
    band = [_band(b["v"], vmin, vmax) for b in binfo]
    names = {"low": f"low < {vmin:.2f} pu", "high": f"high > {vmax:.2f} pu",
             "near limit": "within 0.02 pu of limit", "normal": "normal"}
    for name, key in BANDS:
        xs, ys = [], []
        for i in range(n):
            if band[i] == name:
                xs += [cx[i] - w[i] / 2, cx[i] + w[i] / 2, None]
                ys += [Y[i], Y[i], None]
        fig.add_trace(go.Scatter(x=xs or [None], y=ys or [None], mode="lines",
                                 name=names[name], hoverinfo="skip",
                                 line=dict(color=P[key], width=4)))

    if selected is not None:
        kind, j = selected
        if kind == "bus" and j < n:
            fig.add_trace(go.Scatter(
                x=[cx[j] - w[j] / 2, cx[j] + w[j] / 2], y=[Y[j], Y[j]],
                mode="lines", hoverinfo="skip", showlegend=False,
                line=dict(color=P["accent"], width=8)))
        elif kind == "line" and j < len(routes):
            poly([routes[j]], line=dict(color=P["accent"], width=3.5))

    # labels: bus number + |V| (+ angle); flows only on request
    # drawn as boxed annotations so a wire passing behind never strikes
    # through the numbers (text is in pixels, the bar geometry in units)
    for j, b in enumerate(binfo):
        fig.add_annotation(
            x=cx[j] - w[j] / 2, y=Y[j] + 0.12, xanchor="left", yanchor="bottom",
            showarrow=False, bgcolor=P["canvas"], borderpad=1,
            font=dict(size=10.5, color=ink, family=MONO),
            text=f"<b>{b['bus']}</b> {b['v']:.3f}"
                 + (f" ∠{b['ang']:.1f}°" if "angles" in show else ""))
    if "flows" in show:
        for r, pts in zip(linfo, routes):
            if "pij" in r:
                (mx, my), _ = _midpoint(pts)
                fig.add_annotation(x=mx, y=-my, text=f"{abs(r['pij']):.1f}",
                                   showarrow=False, bgcolor=P["canvas"],
                                   borderpad=1,
                                   font=dict(size=9, color=ink, family=MONO))

    # transparent hover / click targets along every bar and line
    hx, hy, hc, ht = [], [], [], []
    for i, b in enumerate(binfo):
        for x in np.linspace(cx[i] - w[i] / 2, cx[i] + w[i] / 2, 7):
            hx.append(x)
            hy.append(Y[i])
            hc.append(["bus", i])
            ht.append(_bus_hover(b))
    for k, (r, pts) in enumerate(zip(linfo, routes)):
        for x, y in _along(pts)[1:-1] or [_midpoint(pts)[0]]:
            hx.append(x)
            hy.append(-y)
            hc.append(["line", k])
            ht.append(_line_hover(r))
    fig.add_trace(go.Scatter(
        x=hx, y=hy, mode="markers", customdata=hc, hovertext=ht,
        hoverinfo="text", showlegend=False, name="targets",
        marker=dict(size=14, color="rgba(0,0,0,0)"),
        selected=dict(marker=dict(opacity=0)),
        unselected=dict(marker=dict(opacity=0))))

    fig.update_layout(
        height=height, margin=dict(l=4, r=4, t=4, b=4),
        dragmode="pan", hovermode="closest", uirevision="oneline",
        xaxis=dict(visible=False,
                   range=[(cx - w / 2).min() - 1.5, (cx + w / 2).max() + 1.5]),
        yaxis=dict(visible=False, range=[Y.min() - 2.0, Y.max() + 2.4],
                   scaleanchor="x", scaleratio=1),
        legend=dict(x=0.995, y=0.005, xanchor="right", yanchor="bottom",
                    itemclick=False, itemdoubleclick=False))
    return fig


def inspect(res, lines, flows, base, bus, selected):
    """(title, rows) for the inspector panel of a selected bus or line."""
    kind, j = selected
    if kind == "bus":
        b = bus_info(res, bus, base)[j]
        rows = [("Type", b["type"]), ("|V|", f"{b['v']:.4f} pu"),
                ("Angle", f"{b['ang']:.2f}°"), ("P gen", f"{b['pg']:.2f} MW"),
                ("Q gen", f"{b['qg']:.2f} MVAr"), ("P load", f"{b['pl']:.2f} MW"),
                ("Q load", f"{b['ql']:.2f} MVAr")]
        for r in line_info(lines, flows, base):
            if "pij" in r and b["bus"] in (r["frm"], r["to"]):
                p, q = (r["pij"], r["qij"]) if r["frm"] == b["bus"] else \
                    (r["pji"], r["qji"])
                rows.append((f"Out on {r['name']}", f"{p:.1f} MW {q:.1f} MVAr"))
        return f"Bus {b['bus']}", rows
    r = line_info(lines, flows, base)[j]
    rows = [("From / to", f"{r['frm']} / {r['to']}"), ("Tap", f"{r['tap']:g}")]
    if "pij" in r:
        rows += [("P from", f"{r['pij']:.2f} MW"), ("Q from", f"{r['qij']:.2f} MVAr"),
                 ("S from", f"{r['sij']:.2f} MVA"), ("P to", f"{r['pji']:.2f} MW"),
                 ("Q to", f"{r['qji']:.2f} MVAr"), ("S to", f"{r['sji']:.2f} MVA"),
                 ("Loss P", f"{r['lp']:.3f} MW"), ("Loss Q", f"{r['lq']:.3f} MVAr")]
    return f"Line {r['name']}", rows
