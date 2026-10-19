import numpy as np
import pandas as pd

METHODS = ["Newton-Raphson", "Fast Decoupled", "Gauss-Seidel"]


# ----------------------------------------------------------------- solver
def build_ybus(n, lines, bus=None):
    """Ybus with optional off-nominal taps (line col 'Tap') and bus shunts (bus col 'Bs')."""
    Y = np.zeros((n, n), complex)
    for _, l in lines.iterrows():
        i, j = int(l["From"]) - 1, int(l["To"]) - 1
        a = l["Tap"] if "Tap" in l and l["Tap"] > 0 else 1.0
        y, b = 1 / complex(l["R"], l["X"]), 1j * l["B"] / 2
        Y[i, i] += y / a**2 + b
        Y[j, j] += y + b
        Y[i, j] -= y / a
        Y[j, i] -= y / a
    if bus is not None and "Bs" in bus:
        Y[np.diag_indices(n)] += 1j * bus["Bs"].fillna(0).values
    return Y


def injections(Y, V, th):
    Vc = V * np.exp(1j * th)
    return Vc * np.conj(Y @ Vc)


def newton_raphson(Y, V0, th0, Psp, Qsp, ang, mag, tol, max_iter=30):
    def unpack(x):
        th, V = th0.copy(), V0.copy()
        th[ang] = x[: len(ang)]
        V[mag] = x[len(ang):]
        return th, V

    def mismatch(x):
        S = injections(Y, *unpack(x)[::-1])
        return np.r_[(S.real - Psp)[ang], (S.imag - Qsp)[mag]]

    x = np.r_[th0[ang], V0[mag]]
    hist = []
    for _ in range(max_iter):
        f = mismatch(x)
        hist.append(abs(f).max())
        if hist[-1] < tol:
            return *unpack(x), True, hist
        J = np.zeros((len(x), len(x)))
        for c in range(len(x)):  # central-difference Jacobian
            d = np.zeros(len(x))
            d[c] = 1e-6
            J[:, c] = (mismatch(x + d) - mismatch(x - d)) / 2e-6
        x = x - np.linalg.solve(J, f)
    return *unpack(x), False, hist


def fast_decoupled(Y, lines, V0, th0, Psp, Qsp, ang, mag, tol, max_iter=200):
    """XB version: B' from series X only, B'' from the full Ybus."""
    n = len(V0)
    Bp = np.zeros((n, n))
    for _, l in lines.iterrows():
        i, j = int(l["From"]) - 1, int(l["To"]) - 1
        b = 1 / l["X"]
        Bp[i, i] += b
        Bp[j, j] += b
        Bp[i, j] -= b
        Bp[j, i] -= b
    B1 = Bp[np.ix_(ang, ang)]
    B2 = -Y.imag[np.ix_(mag, mag)]
    th, V = th0.copy(), V0.copy()
    hist = []
    for _ in range(max_iter):
        S = injections(Y, V, th)
        dP, dQ = (Psp - S.real)[ang], (Qsp - S.imag)[mag]
        err = max(abs(dP).max(initial=0), abs(dQ).max(initial=0))
        hist.append(err)
        if err < tol:
            return th, V, True, hist
        th[ang] += np.linalg.solve(B1, dP / V[ang])
        if len(mag):
            dQ = (Qsp - injections(Y, V, th).imag)[mag]
            V[mag] += np.linalg.solve(B2, dQ / V[mag])
    return th, V, False, hist


def gauss_seidel(Y, V0, th0, t, Psp, Qsp, tol=1e-6, max_iter=5000):
    """PV buses: Q is recomputed each sweep and |V| is held at the setpoint."""
    V = V0 * np.exp(1j * th0)
    hist = [float("nan")]  # so len(hist) - 1 = number of sweeps
    for _ in range(max_iter):
        dmax = 0.0
        for i in range(len(V)):
            if t[i] == "Slack":
                continue
            s = Y[i] @ V - Y[i, i] * V[i]
            Qc = -(np.conj(V[i]) * (Y[i] @ V)).imag if t[i] == "PV" else Qsp[i]
            new = ((Psp[i] - 1j * Qc) / np.conj(V[i]) - s) / Y[i, i]
            if t[i] == "PV":
                new = V0[i] * new / abs(new)
            dmax = max(dmax, abs(new - V[i]))
            V[i] = new
        hist.append(dmax)
        if dmax < tol:
            return np.angle(V), np.abs(V), True, hist
    return np.angle(V), np.abs(V), False, hist


def solve_loadflow(bus, lines, method="Newton-Raphson", tol=1e-8):
    n = len(bus)
    t = bus["Type"].values
    if (t == "Slack").sum() != 1:
        raise ValueError("Exactly one Slack bus is required.")
    if not lines[["From", "To"]].isin(range(1, n + 1)).all().all():
        raise ValueError("Line From/To must be bus numbers 1..N.")
    Y = build_ybus(n, lines, bus)
    V0 = bus["V"].astype(float).values.copy()
    V0[t == "PQ"] = 1.0  # flat start
    th0 = np.zeros(n)
    Psp = (bus["Pg"] - bus["Pd"]).astype(float).values
    Qsp = (bus["Qg"] - bus["Qd"]).astype(float).values
    ang = np.where(t != "Slack")[0]
    mag = np.where(t == "PQ")[0]

    if method == "Fast Decoupled":
        th, V, ok, hist = fast_decoupled(Y, lines, V0, th0, Psp, Qsp, ang, mag, tol)
    elif method == "Gauss-Seidel":
        th, V, ok, hist = gauss_seidel(Y, V0, th0, t, Psp, Qsp)
    else:
        th, V, ok, hist = newton_raphson(Y, V0, th0, Psp, Qsp, ang, mag, tol)

    Vc = V * np.exp(1j * th)
    S = Vc * np.conj(Y @ Vc)
    rows = []
    for _, l in lines.iterrows():
        i, j = int(l["From"]) - 1, int(l["To"]) - 1
        y, b = 1 / complex(l["R"], l["X"]), 1j * l["B"] / 2
        a = l["Tap"] if "Tap" in l and l["Tap"] > 0 else 1.0
        Sij = Vc[i] * np.conj((Vc[i] / a**2 - Vc[j] / a) * y + Vc[i] * b)
        Sji = Vc[j] * np.conj((Vc[j] - Vc[i] / a) * y + Vc[j] * b)
        L = Sij + Sji
        rows.append([i + 1, j + 1, Sij.real, Sij.imag, Sji.real, Sji.imag,
                     L.real, L.imag])
    flows = pd.DataFrame(rows, columns=["From", "To", "P_ij", "Q_ij", "P_ji",
                                        "Q_ji", "Loss_P", "Loss_Q"])
    res = pd.DataFrame({"Bus": np.arange(1, n + 1), "V (pu)": V,
                        "Angle (deg)": np.degrees(th),
                        "P_inj": S.real, "Q_inj": S.imag})
    return res, flows, ok, hist

# ============================================================================
# Generator Q limits (PV -> PQ switching)
# Generator reactive limits: PV -> PQ switching around solve_loadflow.
# 
# The base solver is not touched. A PV bus whose required generation
# Qg = Q_inj + Qd leaves [Qmin, Qmax] becomes a PQ bus with Qg held at the
# violated limit, and the case is solved again. A switched bus goes back to
# PV when its voltage returns to the right side of its setpoint (at Qmax
# with V > Vset, or at Qmin with V < Vset). Bus columns Qmin / Qmax are in
# per unit like Qg; missing values mean no limit.
# ============================================================================

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
