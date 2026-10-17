import numpy as np


def draw_network(res, lines, vmin, vmax):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(res)
    edges = [(int(a) - 1, int(b) - 1) for a, b in zip(lines["From"], lines["To"])]
    pos = np.random.default_rng(1).random((n, 2))
    k = 1 / np.sqrt(n)
    for it in range(250):  # Fruchterman-Reingold layout
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
    v = res["V (pu)"].values
    fig, ax = plt.subplots(figsize=(7, 5))
    for i, j in edges:
        ax.plot(*zip(pos[i], pos[j]), c="gray", lw=1.5, zorder=1)
    sc = ax.scatter(pos[:, 0], pos[:, 1], c=v, cmap="RdYlGn", s=650, zorder=2,
                    vmin=vmin - 0.03, vmax=vmax + 0.03, linewidths=2.5,
                    edgecolors=["red" if (x < vmin or x > vmax) else "black" for x in v])
    for i in range(n):
        ax.text(*pos[i], str(i + 1), ha="center", va="center", fontweight="bold", zorder=3)
    fig.colorbar(sc, label="Voltage (pu), red outline = violation")
    ax.axis("off")
    return fig
