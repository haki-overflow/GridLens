"""GridLens matplotlib figures, styled by ui_theme (planning-tool look).

All figures share one palette (ui_theme.PAL): dark canvas with a thin boxed
axis, cyan data, red only for limit violations/limits. The interactive
one-line diagram lives in oneline.py (Plotly).
"""
import numpy as np

import ui_theme as T

P = T.PAL


def voltage_profile(res, vmin, vmax):
    """Bus |V| bars in the accent colour, dashed red limit lines."""
    plt = T.mpl_style()
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
    plt = T.mpl_style()
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
    plt = T.mpl_style()
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
    red/cyan, the rest dim grey, base case and last solvable point marked."""
    plt = T.mpl_style()
    lam = pv["lambda"].to_numpy(dtype=float)
    V = pv.drop(columns="lambda")
    weak = V.iloc[-1].nsmallest(highlight).index
    fig, ax = plt.subplots(figsize=(7, 3.0))
    for c in V.columns:
        if c not in weak:
            ax.plot(lam, V[c], color=P["axis"], lw=1.2, zorder=1)
    for c, col in zip(weak, (P["red"], P["c1"], P["text"])):
        ax.plot(lam, V[c], color=col, lw=1.9, label=c, zorder=3)
    ax.axvline(1.0, color=P["text"], lw=0.9, ls=":", zorder=2)
    ax.text(1.0, ax.get_ylim()[1], " base case", fontsize=8, va="top",
            color=P["text"])
    ax.axvline(lam_max, color=P["red"], lw=0.9, ls="--", zorder=2)
    ax.text(lam_max, ax.get_ylim()[0], f"\u03bb max {lam_max:.2f} ",
            fontsize=8, ha="right", va="bottom", color=P["red"])
    ax.axhline(vmin, color=P["red"], lw=0.8, ls=(0, (2, 3)), alpha=0.6)
    ax.set_xlabel("Load multiplier \u03bb (all loads and generation)")
    ax.set_ylabel("|V| (pu)")
    ax.grid(color=P["grid"], lw=0.7)
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    return fig
