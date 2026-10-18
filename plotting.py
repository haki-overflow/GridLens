"""GridLens matplotlib figures, styled by ui_theme (plain engineering look).

All figures share one palette (ui_theme.LIGHT): white background, grey axes,
accent blue data, red only for limit violations/limits.
"""
import numpy as np

import ui_theme as T

P = T.LIGHT


def _layout(n, edges, seed=1):
    """Deterministic spring layout in [0, 1]^2 with a minimum separation."""
    rng = np.random.default_rng(seed)
    pos = rng.random((n, 2))
    k = 1 / np.sqrt(n)
    for it in range(250):
        d = pos[:, None] - pos[None]
        dist = np.linalg.norm(d, axis=2) + 1e-9
        disp = (d / dist[..., None] * (k**2 / dist)[..., None]).sum(1)
        for i, j in edges:
            dv = pos[i] - pos[j]
            dd = np.linalg.norm(dv) + 1e-9
            disp[i] -= dv / dd * dd**2 / k
            disp[j] += dv / dd * dd**2 / k
        L = np.linalg.norm(disp, axis=1)[:, None] + 1e-9
        pos += disp / L * np.minimum(L, 0.1 * (1 - it / 250))
    for _ in range(40):  # push apart nodes that ended up too close
        d = pos[:, None] - pos[None]
        dist = np.linalg.norm(d, axis=2) + 1e-9
        close = (dist < 0.09) & (dist > 1e-6)
        if not close.any():
            break
        i, j = np.argwhere(np.triu(close, 1)).T
        for a, b in zip(i, j):
            u = d[a, b] / dist[a, b]
            pos[a] += 0.5 * (0.09 - dist[a, b]) * u
            pos[b] -= 0.5 * (0.09 - dist[a, b]) * u
    pos -= pos.min(0)
    span = pos.max(0) + 1e-9
    pos = 0.08 + 0.84 * pos / span
    return pos


def draw_network(res, lines, vmin, vmax, flows=None, base=100.0):
    """Network diagram: white-fill bus circles (accent outline, red when |V|
    is outside the limits), mid-grey lines whose width follows |P_ij|, one
    small midpoint arrow for flow direction, P in MW labelled on each line."""
    plt = T.mpl_style()
    n = len(res)
    edges = [(int(a) - 1, int(b) - 1)
             for a, b in zip(lines["From"], lines["To"])]
    pos = _layout(n, edges)
    v = res["V (pu)"].to_numpy(dtype=float)
    anchors = np.vstack([pos, pos - [0.0, 0.05]])  # node circles + |V| texts

    lw = np.full(len(edges), 1.5)
    p_mw = None
    dirs = np.ones(len(edges))
    if flows is not None and len(flows) == len(edges):
        pij = np.asarray(flows["P_ij"], dtype=float)
        p_mw = pij * base
        p = np.abs(pij)
        if len(p) and p.max() > 0:
            lw = 1.5 + 2.5 * p / p.max()
        dirs = np.where(pij >= 0, 1, -1)

    fig, ax = plt.subplots(figsize=(8, 5))
    for ek, (i, j) in enumerate(edges):
        a, b = pos[i], pos[j]
        ax.plot(*zip(a, b), c=P["line"], lw=float(lw[ek]), zorder=1,
                solid_capstyle="round")
        u = b - a
        u = u / (np.linalg.norm(u) + 1e-9)
        if dirs[ek] < 0:
            u = -u
        mid = (a + b) / 2
        ax.annotate("", xy=mid + 0.028 * u, xytext=mid - 0.028 * u, zorder=3,
                    arrowprops=dict(arrowstyle="-|>", color=P["muted"],
                                    lw=1.0, mutation_scale=9))
        if p_mw is not None:
            t = 0.34 if dirs[ek] > 0 else 0.66
            perp = np.array([-u[1], u[0]]) * 0.032

            def pick(pos_):
                s_ = (pos_ + perp, pos_ - perp)
                near_ = [np.linalg.norm(anchors - q, axis=1).min() for q in s_]
                return (s_[0], near_[0]) if near_[0] >= near_[1] else \
                    (s_[1], near_[1])

            lab, gap = pick(a + (b - a) * t)
            if gap < 0.055:  # blocked by a node or its |V| label: slide to mid
                lab2, gap2 = pick(a + (b - a) * (t + (0.5 - t) * 0.6))
                if gap2 > gap:
                    lab = lab2
            ax.text(lab[0], lab[1], f"{abs(p_mw[ek]):.0f}", fontsize=7.5,
                    ha="center", va="center", color=P["muted"], zorder=4,
                    bbox=dict(boxstyle="round,pad=0.12", facecolor=P["plot_bg"],
                              edgecolor=P["border"], linewidth=0.6))

    bad = (v < vmin) | (v > vmax)
    ax.scatter(pos[:, 0], pos[:, 1], s=430, facecolor=P["plot_bg"],
               edgecolors=[P["red"] if x else P["accent"] for x in bad],
               linewidths=2.0, zorder=5)
    for i in range(n):
        ax.text(*pos[i], f"{i + 1}", ha="center", va="center", fontsize=9,
                fontweight=600, color=P["text"], zorder=6)
        ax.text(pos[i, 0], pos[i, 1] - 0.05, f"{v[i]:.3f}", ha="center",
                va="top", fontsize=7.5, color=P["muted"], zorder=6,
                bbox=dict(boxstyle="round,pad=0.08", facecolor=P["plot_bg"],
                          edgecolor="none"))

    ax.set_aspect("equal")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.tight_layout()
    return fig


def voltage_profile(res, vmin, vmax):
    """Bus |V| bars in the accent colour, dashed red limit lines."""
    plt = T.mpl_style()
    x = res["Bus"].to_numpy(dtype=float)
    v = res["V (pu)"].to_numpy(dtype=float)
    lo = min(vmin, v.min()) - 0.015
    hi = max(vmax, v.max()) + 0.025
    fig, ax = plt.subplots(figsize=(8, 2.8))
    ax.bar(x, v, bottom=lo, width=0.6, color=P["accent"], zorder=2)
    for lim, name in ((vmax, "Vmax"), (vmin, "Vmin")):
        ax.axhline(lim, color=P["red"], linestyle="--", lw=1, zorder=3)
        ax.text(x.max() + 0.45, lim, f" {name} {lim:.2f}", color=P["red"],
                fontsize=8, va="center")
    ax.set_xticks(x.astype(int))
    ax.set_xlim(x.min() - 0.6, x.max() + 0.6)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Bus")
    ax.set_ylabel("|V| (pu)")
    ax.grid(axis="y", color=P["plot_grid"], lw=0.7, zorder=0)
    fig.tight_layout()
    return fig


def convergence_history(hist):
    """Semilogy mismatch error per iteration (NaN sweep-inits are skipped)."""
    plt = T.mpl_style()
    h = np.asarray(list(hist), dtype=float)
    it = np.arange(1, len(h))
    y = h[1:]
    keep = np.isfinite(y) & (y > 0)
    fig, ax = plt.subplots(figsize=(8, 2.6))
    if keep.any():
        ax.semilogy(it[keep], y[keep], color=P["accent"], lw=1.8, marker="o",
                    ms=3.5)
    ax.set_xlim(0.5, max(len(h) - 0.5, 1.5))
    ax.set_xticks(np.arange(1, max(len(h), 2)).astype(int))
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Max mismatch (pu)")
    ax.grid(color=P["plot_grid"], lw=0.7)
    fig.tight_layout()
    return fig


def fault_voltages(v_pu, vmin, vmax):
    """Bar chart of post-fault |V| magnitudes (v_pu: Series indexed by bus)."""
    plt = T.mpl_style()
    x = v_pu.index.to_numpy(dtype=float)
    y = v_pu.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(8, 2.8))
    ax.bar(x, y, width=0.6, color=P["accent"], zorder=2)
    ax.axhline(vmin, color=P["red"], linestyle="--", lw=1, zorder=3)
    ax.text(x.max() + 0.45, vmin, f" Vmin {vmin:.2f}", color=P["red"],
            fontsize=8, va="center")
    ax.set_xticks(x.astype(int))
    ax.set_xlim(x.min() - 0.6, x.max() + 0.6)
    ax.set_ylim(0, max(y.max() * 1.08, 0.1))
    ax.set_xlabel("Bus")
    ax.set_ylabel("Post-fault |V| (pu)")
    ax.grid(axis="y", color=P["plot_grid"], lw=0.7, zorder=0)
    fig.tight_layout()
    return fig
