import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import splu

METHODS = ["Newton-Raphson", "Fast Decoupled", "Gauss-Seidel"]


# ----------------------------------------------------------------- solver
def in_service(lines):
    """The branches that carry current (line column InService; missing = all)."""
    if "InService" not in lines:
        return lines
    return lines[lines["InService"].fillna(1).astype(float) != 0]


def _on(lines):
    """in_service as a mask over the row positions."""
    if "InService" not in lines:
        return np.ones(len(lines), bool)
    return lines["InService"].fillna(1).astype(float).to_numpy() != 0


def islands(n, lines):
    """Groups of bus rows (0-based, ascending) joined by in-service branches
    between existing buses, ordered by their first bus."""
    f, t = (pd.to_numeric(lines[c], errors="coerce").to_numpy(float) - 1
            for c in ("From", "To"))
    use = _on(lines) & (f >= 0) & (f < n) & (t >= 0) & (t < n)
    A = sp.coo_array((np.ones(int(np.sum(use))), (f[use].astype(int), t[use].astype(int))),
                     shape=(n, n))
    _, label = connected_components(A, directed=False)
    groups = {}
    for i, g in enumerate(label):
        groups.setdefault(g, []).append(i)
    return sorted(groups.values())


def branch_y(l):
    """(Yff, Ytt, Yft, Ytf) of one branch: series y = 1/(R + jX), charging
    jB/2 at each end, off-nominal tap a and phase shift (deg) on the From
    side (t = a e^{j shift}); the From half of the charging sits behind the
    tap, Yff = (y + jB/2)/a^2, as in MATPOWER. With no shift this is the plain
    tap model."""
    a = l["Tap"] if "Tap" in l and l["Tap"] > 0 else 1.0
    y, b = 1 / complex(l["R"], l["X"]), 1j * l["B"] / 2
    s = float(l["Shift"]) if "Shift" in l and l["Shift"] else 0.0
    if not s:
        return (y + b) / a**2, y + b, -y / a, -y / a
    t = a * np.exp(1j * np.radians(s))
    return (y + b) / a**2, y + b, -y / np.conj(t), -y / t


def build_ybus(n, lines, bus=None):
    """Ybus with optional off-nominal taps and phase shifts (line cols 'Tap',
    'Shift'), out-of-service branches left out (col 'InService') and bus
    shunts (bus cols 'Bs', 'Gs')."""
    Y = np.zeros((n, n), complex)
    for _, l in in_service(lines).iterrows():
        i, j = int(l["From"]) - 1, int(l["To"]) - 1
        yff, ytt, yft, ytf = branch_y(l)
        Y[i, i] += yff
        Y[j, j] += ytt
        Y[i, j] += yft
        Y[j, i] += ytf
    if bus is not None and "Bs" in bus:
        Y[np.diag_indices(n)] += 1j * bus["Bs"].fillna(0).values
    if bus is not None and "Gs" in bus and bus["Gs"].fillna(0).astype(float).any():
        Y[np.diag_indices(n)] += bus["Gs"].fillna(0).astype(float).values
    return Y


def branch_admittances(lines):
    """branch_y for every in-service branch at once: (k, f, t, yff, ytt, yft,
    ytf) with k the row positions and f, t the 0-based From / To bus rows."""
    k = np.flatnonzero(_on(lines))

    def col(c, missing=None):
        return lines[c].to_numpy(float)[k] if missing is None or c in lines \
            else np.full(len(k), missing)
    a = col("Tap", 1.0)
    a = np.where(a > 0, a, 1.0)                  # 0 / blank = no tap
    s = np.nan_to_num(col("Shift", 0.0))
    y = 1 / (col("R") + 1j * col("X"))
    b = 0.5j * col("B")
    t = a * np.exp(1j * np.radians(s))
    return (k, col("From").astype(int) - 1, col("To").astype(int) - 1,
            (y + b) / a**2, y + b, -y / np.conj(t), -y / t)


def ybus_sparse(n, lines, bus=None):
    """build_ybus as a sparse CSR array, made in one step from the branch
    admittances (no Python loop). The engine uses this one; build_ybus stays
    for the worked solution and the textbook pages."""
    _, f, t, yff, ytt, yft, ytf = branch_admittances(lines)
    Y = sp.csr_array((np.r_[yff, ytt, yft, ytf], (np.r_[f, t, f, t], np.r_[f, t, t, f])),
                     shape=(n, n))
    ysh = np.zeros(n, complex)
    for c, unit in (("Gs", 1), ("Bs", 1j)):
        if bus is not None and c in bus:
            ysh += unit * bus[c].fillna(0).astype(float).to_numpy()
    return (Y + sp.diags_array(ysh)).tocsr()


def injections(Y, V, th):
    Vc = V * np.exp(1j * th)
    return Vc * np.conj(Y @ Vc)


def newton_raphson(Y, V0, th0, Psp, Qsp, ang, mag, tol, max_iter=30, damp=1.0):
    """Polar Newton-Raphson on the sparse Ybus with the analytical Jacobian
    (as MATPOWER's newtonpf), unknowns θ at ang and |V| at mag, one sparse
    LU solve per iteration. Stops early when the mismatch is no longer a
    number (diverged)."""
    th, V = th0.copy(), V0.copy()
    S0 = Psp + 1j * Qsp
    jacobian = _jacobian(Y, ang, mag)
    hist = []
    for _ in range(max_iter):
        E = np.exp(1j * th)
        Vc = V * E
        I = Y @ Vc
        mis = Vc * np.conj(I) - S0
        f = np.r_[mis.real[ang], mis.imag[mag]]
        hist.append(np.abs(f).max(initial=0))
        if hist[-1] < tol:
            return th, V, True, hist
        if not np.isfinite(hist[-1]):
            break
        dx = _lu(jacobian(Vc, E, I)).solve(f)
        th[ang] -= damp * dx[:len(ang)]
        V[mag] -= damp * dx[len(ang):]
    return th, V, False, hist


def _jacobian(Y, ang, mag):
    """The Jacobian as a function of (Vc, E, I), filled into a sparse pattern
    that is fixed once per solve. From S = diag(Vc) conj(I), I = Y Vc,
    Vc = |V| E (MATPOWER dSbus_dV, polar), for each Ybus entry Y_ik:
        dS_i/dθ_k   = -j Vc_i conj(Y_ik Vc_k)  + (i = k) j Vc_i conj(I_i)
        dS_i/d|V|_k =  Vc_i conj(Y_ik E_k)     + (i = k) conj(I_i) E_i
    J = [[Re dS/dθ, Re dS/d|V|], [Im dS/dθ, Im dS/d|V|]] with the P rows at
    ang, the Q rows at mag, the θ columns at ang and the |V| columns at mag."""
    n, na = Y.shape[0], len(ang)
    Yc = Y.tocoo()
    i, k = np.r_[Yc.row, np.arange(n)], np.r_[Yc.col, np.arange(n)]  # + the (i = k) terms
    pa, pm = np.full(n, -1), np.full(n, -1)   # row / column of each bus's θ and |V|
    pa[ang], pm[mag] = np.arange(na), na + np.arange(len(mag))
    sel, rows, cols = [], [], []
    for r, c in ((pa, pa), (pa, pm), (pm, pa), (pm, pm)):
        s = np.flatnonzero((r[i] >= 0) & (c[k] >= 0))
        sel.append(s)
        rows.append(r[i[s]])
        cols.append(c[k[s]])
    N = na + len(mag)
    key, slot = np.unique(np.concatenate(cols) * N + np.concatenate(rows), return_inverse=True)
    indices, indptr = key % N, np.searchsorted(key // N, np.arange(N + 1))

    def jacobian(Vc, E, I):
        dth = np.r_[-1j * Vc[Yc.row] * np.conj(Yc.data * Vc[Yc.col]), 1j * Vc * np.conj(I)]
        dV = np.r_[Vc[Yc.row] * np.conj(Yc.data * E[Yc.col]), np.conj(I) * E]
        vals = np.r_[dth.real[sel[0]], dV.real[sel[1]], dth.imag[sel[2]], dV.imag[sel[3]]]
        data = np.bincount(slot, weights=vals, minlength=len(key))
        return sp.csc_array((data, indices, indptr), shape=(N, N))
    return jacobian


def _lu(A):
    """Sparse LU factors of A; an exactly singular A raises LinAlgError like
    numpy.linalg.solve (gridcore.loadflow then tries another method)."""
    try:
        return splu(sp.csc_array(A))
    except RuntimeError as e:   # SuperLU: "Factor is exactly singular"
        raise np.linalg.LinAlgError(str(e)) from None


def fast_decoupled(Y, lines, V0, th0, Psp, Qsp, ang, mag, tol, max_iter=200):
    """XB version on the sparse Ybus: B' from series X only, B'' = -Im Ybus;
    each is factorised once (sparse LU) and reused on every iteration."""
    k = np.flatnonzero(_on(lines))
    f, t = (lines[c].to_numpy(int)[k] - 1 for c in ("From", "To"))
    X = lines["X"].to_numpy(float)[k]
    if (X == 0).any():   # a LinAlgError: gridcore.loadflow moves on to Newton-Raphson
        raise np.linalg.LinAlgError("Fast Decoupled needs X ≠ 0 on every line in service "
                                    f"(lines {_names(f, t, X == 0)} have X = 0): B' is 1/X.")
    Bp = _susceptance(len(V0), f, t, 1 / X)
    lu1 = _lu(Bp[ang][:, ang])
    lu2 = _lu(-Y.imag[mag][:, mag]) if len(mag) else None
    th, V = th0.copy(), V0.copy()
    hist = []
    for _ in range(max_iter):
        S = injections(Y, V, th)
        dP, dQ = (Psp - S.real)[ang], (Qsp - S.imag)[mag]
        err = max(abs(dP).max(initial=0), abs(dQ).max(initial=0))
        hist.append(err)
        if err < tol:
            return th, V, True, hist
        th[ang] += lu1.solve(dP / V[ang])
        if len(mag):
            dQ = (Qsp - injections(Y, V, th).imag)[mag]
            V[mag] += lu2.solve(dQ / V[mag])
    return th, V, False, hist


def _names(f, t, mask):
    """"From-To" (1-based) of the branches where mask is true."""
    return ", ".join(f"{i + 1}-{j + 1}" for i, j in zip(f[mask], t[mask]))


def _susceptance(n, f, t, b):
    """The n x n matrix of branch susceptances b between buses f and t (each
    adds b at (f, f) and (t, t), -b at (f, t) and (t, f)): B' of Fast
    Decoupled and B of the DC load flow."""
    return sp.csr_array((np.r_[b, b, -b, -b], (np.r_[f, t, f, t], np.r_[f, t, t, f])),
                        shape=(n, n))


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


def _check(bus, lines):
    """The solvers' own minimum checks (gridcore.prep_case does the full validation)."""
    if (bus["Type"].values == "Slack").sum() < 1:  # one per island; prep_case checks islands
        raise ValueError("Exactly one Slack bus is required.")
    if not lines[["From", "To"]].isin(range(1, len(bus) + 1)).all().all():
        raise ValueError("Line From/To must be bus numbers 1..N.")


def _va(bus):
    """Bus angles in radians from the Va column (degrees; missing = 0)."""
    if "Va" not in bus:
        return np.zeros(len(bus))
    return np.radians(pd.to_numeric(bus["Va"], errors="coerce").fillna(0).to_numpy(float))


def solve_loadflow(bus, lines, method="Newton-Raphson", tol=1e-8, init="flat",
                   damp=1.0, max_iter=None):
    """init "flat": PQ buses start at 1∠0; "setpoint": every bus starts at
    its V column (and angle column Va in degrees when present). damp < 1
    shortens each Newton-Raphson step (for hard cases)."""
    _check(bus, lines)
    n = len(bus)
    t = bus["Type"].values
    Y = ybus_sparse(n, lines, bus)
    V0 = bus["V"].astype(float).values.copy()
    va = _va(bus)
    th0 = np.where(t == "Slack", va, 0.0)  # the reference angle (0 unless given)
    if init == "setpoint":
        V0[V0 <= 0] = 1.0
        th0 = va.copy()
    else:
        V0[t == "PQ"] = 1.0  # flat start
    Psp = (bus["Pg"] - bus["Pd"]).astype(float).values
    Qsp = (bus["Qg"] - bus["Qd"]).astype(float).values
    ang = np.where(t != "Slack")[0]
    mag = np.where(t == "PQ")[0]

    its = {} if max_iter is None else {"max_iter": max_iter}
    if method == "Fast Decoupled":
        th, V, ok, hist = fast_decoupled(Y, lines, V0, th0, Psp, Qsp, ang, mag, tol, **its)
    elif method == "Gauss-Seidel":   # dense: teaching only
        th, V, ok, hist = gauss_seidel(build_ybus(n, lines, bus), V0, th0, t, Psp, Qsp, tol,
                                       **its)
    else:
        th, V, ok, hist = newton_raphson(Y, V0, th0, Psp, Qsp, ang, mag, tol, damp=damp, **its)

    Vc = V * np.exp(1j * th)
    S = Vc * np.conj(Y @ Vc)
    res = pd.DataFrame({"Bus": np.arange(1, n + 1), "V (pu)": V,
                        "Angle (deg)": np.degrees(th),
                        "P_inj": S.real, "Q_inj": S.imag})
    return res, branch_flows(lines, Vc), ok, hist


def branch_flows(lines, Vc):
    """Power into each branch at both ends (S_ij at From, S_ji at To) and
    the loss S_ij + S_ji, per unit; out-of-service rows carry 0."""
    k, f, t, yff, ytt, yft, ytf = branch_admittances(lines)
    Sij, Sji = np.zeros(len(lines), complex), np.zeros(len(lines), complex)
    Sij[k] = Vc[f] * np.conj(yff * Vc[f] + yft * Vc[t])
    Sji[k] = Vc[t] * np.conj(ytt * Vc[t] + ytf * Vc[f])
    L = Sij + Sji
    return pd.DataFrame({"From": lines["From"].to_numpy(int), "To": lines["To"].to_numpy(int),
                         "P_ij": Sij.real, "Q_ij": Sij.imag, "P_ji": Sji.real,
                         "Q_ji": Sji.imag, "Loss_P": L.real, "Loss_Q": L.imag})


# ------------------------------------------------------------ DC load flow
def dc_model(n, lines):
    """DC model of the in-service branches (as MATPOWER makeBdc): series
    susceptance b = 1 / (X a); a phase shift φ (rad) acts as an injection
    -b φ at From and +b φ at To. Returns (k, f, t, b, φ, B, Pshift)."""
    k = np.flatnonzero(_on(lines))
    f, t = (lines[c].to_numpy(int)[k] - 1 for c in ("From", "To"))
    a = lines["Tap"].to_numpy(float)[k] if "Tap" in lines else np.ones(len(k))
    a = np.where(a > 0, a, 1.0)
    phi = np.radians(np.nan_to_num(lines["Shift"].to_numpy(float)[k])) if "Shift" in lines \
        else np.zeros(len(k))
    X = lines["X"].to_numpy(float)[k]
    if (X == 0).any():
        raise ValueError("the DC load flow needs X ≠ 0 on every line in service (lines "
                         f"{_names(f, t, X == 0)} have X = 0); use the AC load flow.")
    b = 1 / (X * a)
    Pshift = np.bincount(f, -b * phi, n) + np.bincount(t, b * phi, n)
    return k, f, t, b, phi, _susceptance(n, f, t, b), Pshift


def dc_loadflow(bus, lines):
    """DC load flow: |V| = 1; R, line charging and Bs left out; B θ = Pg - Pd
    - Gs - Pshift with θ held at every Slack (its Va, else 0). Same return as
    solve_loadflow (V = 1, Q = 0, no losses); hist is the largest P mismatch
    before and after the one linear solve."""
    _check(bus, lines)
    n = len(bus)
    k, f, t, b, phi, B, Pshift = dc_model(n, lines)
    gs = bus["Gs"].fillna(0).to_numpy(float) if "Gs" in bus else np.zeros(n)
    P = (bus["Pg"] - bus["Pd"]).astype(float).to_numpy() - gs - Pshift
    slack = bus["Type"].to_numpy() == "Slack"
    th = np.where(slack, _va(bus), 0.0)
    ang = np.flatnonzero(~slack)
    mis = (B @ th - P)[ang]
    th[ang] -= _lu(B[ang][:, ang]).solve(mis)
    hist = [np.abs(mis).max(initial=0), np.abs((B @ th - P)[ang]).max(initial=0)]
    Pf = np.zeros(len(lines))
    Pf[k] = b * (th[f] - th[t] - phi)
    zero = np.zeros(len(lines))
    flows = pd.DataFrame({"From": lines["From"].to_numpy(int), "To": lines["To"].to_numpy(int),
                          "P_ij": Pf, "Q_ij": zero, "P_ji": -Pf, "Q_ji": zero,
                          "Loss_P": zero, "Loss_Q": zero})
    res = pd.DataFrame({"Bus": np.arange(1, n + 1), "V (pu)": np.ones(n),
                        "Angle (deg)": np.degrees(th), "P_inj": B @ th + Pshift + gs,
                        "Q_inj": np.zeros(n)})
    return res, flows, True, hist

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
                       max_rounds=20, **solve_kw):
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
        res, flows, ok, hist = solve_loadflow(b, lines, method, tol, **solve_kw)
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
