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
