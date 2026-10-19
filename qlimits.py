"""Generator reactive limits: PV -> PQ switching around solve_loadflow.

The base solver is not touched. A PV bus whose required generation
Qg = Q_inj + Qd leaves [Qmin, Qmax] becomes a PQ bus with Qg held at the
violated limit, and the case is solved again. A switched bus goes back to
PV when its voltage returns to the right side of its setpoint (at Qmax
with V > Vset, or at Qmin with V < Vset). Bus columns Qmin / Qmax are in
per unit like Qg; missing values mean no limit.
"""
import numpy as np

from solver import solve_loadflow


def solve_with_qlimits(bus, lines, method="Newton-Raphson", tol=1e-8,
                       max_rounds=20):
    """Returns (res, flows, ok, hist, final bus table, switch log)."""
    b = bus.copy().reset_index(drop=True)
    qmin = b["Qmin"].astype(float).fillna(-np.inf).to_numpy() if "Qmin" in b \
        else np.full(len(b), -np.inf)
    qmax = b["Qmax"].astype(float).fillna(np.inf).to_numpy() if "Qmax" in b \
        else np.full(len(b), np.inf)
    vset = b["V"].astype(float).to_numpy()
    pv0 = b["Type"].to_numpy() == "PV"
    at = {}                     # bus index -> "max" / "min" while switched
    log, hist_all = [], []
    for rnd in range(1, max_rounds + 1):
        res, flows, ok, hist = solve_loadflow(b, lines, method, tol)
        hist_all = hist
        qg = res["Q_inj"].to_numpy() + b["Qd"].astype(float).to_numpy()
        v = res["V (pu)"].to_numpy()
        changed = False
        for i in np.flatnonzero(pv0):
            if i not in at:
                lim = "max" if qg[i] > qmax[i] + 1e-9 else \
                    "min" if qg[i] < qmin[i] - 1e-9 else None
                if lim:
                    q = qmax[i] if lim == "max" else qmin[i]
                    b.loc[i, ["Type", "Qg"]] = ["PQ", q]
                    at[i] = lim
                    changed = True
                    log.append(dict(Round=rnd, Bus=i + 1, Action="PV → PQ",
                                    Detail=f"Q needed {qg[i]:.4f} pu, held at "
                                           f"Q{lim} = {q:.4f} pu"))
            elif (at[i] == "max" and v[i] > vset[i] + 1e-9) or \
                    (at[i] == "min" and v[i] < vset[i] - 1e-9):
                b.loc[i, ["Type", "V"]] = ["PV", vset[i]]
                del at[i]
                changed = True
                log.append(dict(Round=rnd, Bus=i + 1, Action="PQ → PV",
                                Detail=f"|V| {v[i]:.4f} back past setpoint "
                                       f"{vset[i]:.4f}"))
        if not changed:
            return res, flows, ok, hist_all, b, log
    return res, flows, False, hist_all, b, log
