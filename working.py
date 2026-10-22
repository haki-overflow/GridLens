"""Worked solution: Ybus formation and traced load-flow iterations.

Same formulas as solver.py, but every intermediate value is recorded so a
student can follow the hand method. solver.py is not touched; tests check
that each trace ends on the solver's answer.

- ybus_parts: every term added to each Ybus element (series y, y/a, y/a^2,
  line charging B/2, bus shunts).
- gauss_seidel_trace: V at every bus per iteration, acceleration factor.
- newton_trace: mismatch vector, analytical Jacobian J1..J4, corrections.
- fast_decoupled_trace: B', B'' and the per-iteration corrections.
"""
import numpy as np
import pandas as pd

from solver import branch_y, build_ybus, in_service

TEACH_MAX = 30   # buses: Show working and Gauss-Seidel are for cases up to this size


def _setup(bus):
    t = bus["Type"].values
    V0 = bus["V"].astype(float).values.copy()
    V0[t == "PQ"] = 1.0
    Psp = (bus["Pg"] - bus["Pd"]).astype(float).values
    Qsp = (bus["Qg"] - bus["Qd"]).astype(float).values
    ang = np.where(t != "Slack")[0]
    mag = np.where(t == "PQ")[0]
    return t, V0, Psp, Qsp, ang, mag


def cfmt(z, d=4):
    """a + jb as text."""
    return f"{z.real:.{d}f} {'+' if z.imag >= 0 else '-'} j{abs(z.imag):.{d}f}"


def pfmt(z, d=4):
    """|z|∠angle° as text (a numerically zero value prints as 0)."""
    if abs(z) < 1e-10:
        return f"{0:.{d}f}"
    return f"{abs(z):.{d}f}∠{np.degrees(np.angle(z)):.2f}°"


# ------------------------------------------------------------------ Ybus
def ybus_parts(bus, lines):
    """One row per term: Element (i, j), source, value. Summing the terms
    of an element gives build_ybus (taps on the From side)."""
    rows = []
    for _, l in in_service(lines).iterrows():
        i, j = int(l["From"]) - 1, int(l["To"]) - 1
        a = l["Tap"] if "Tap" in l and l["Tap"] > 0 else 1.0
        y, b = 1 / complex(l["R"], l["X"]), 1j * l["B"] / 2
        name = f"line {i + 1}-{j + 1}"
        tap = abs(a - 1) > 1e-12
        sh = float(l["Shift"]) if "Shift" in l and l["Shift"] else 0.0
        if sh:  # phase shifter: t = a e^{j shift}, Yft = -y/t*, Ytf = -y/t
            _, _, yft, ytf = branch_y(l)
            rows += [(i, i, f"{name}: series y/|t|² (a = {a:g}, shift {sh:g}°)", y / a**2),
                     (j, j, f"{name}: series y", y),
                     (i, j, f"{name}: -y/t*", yft), (j, i, f"{name}: -y/t", ytf)]
        else:
            rows += [(i, i, f"{name}: series y" + (f"/a² (a = {a:g})" if tap else ""), y / a**2),
                     (j, j, f"{name}: series y", y),
                     (i, j, f"{name}: -y" + ("/a" if tap else ""), -y / a),
                     (j, i, f"{name}: -y" + ("/a" if tap else ""), -y / a)]
        if l["B"]:   # the From half sits behind the tap: jB/2 / a^2 there
            rows += [(i, i, f"{name}: charging jB/2" + (f"/a² (a = {a:g})" if tap or sh else ""),
                      b / a**2),
                     (j, j, f"{name}: charging jB/2", b)]
    if "Bs" in bus:
        for i, bs in enumerate(bus["Bs"].fillna(0).astype(float)):
            if bs:
                rows.append((i, i, f"bus {i + 1}: shunt jBs", 1j * bs))
    if "Gs" in bus:
        for i, gs in enumerate(bus["Gs"].fillna(0).astype(float)):
            if gs:
                rows.append((i, i, f"bus {i + 1}: shunt Gs", complex(gs, 0)))
    df = pd.DataFrame(rows, columns=["i", "j", "Source", "Value"])
    df["Element"] = [f"Y{i + 1},{j + 1}" for i, j in zip(df["i"], df["j"])]
    return df.sort_values(["i", "j"], kind="stable").reset_index(drop=True)


def matrix_text(M, fmt=cfmt, labels=None):
    """Complex matrix as a DataFrame of strings (rows/cols = bus numbers)."""
    n = M.shape[0]
    labels = labels or [str(k + 1) for k in range(n)]
    return pd.DataFrame([[fmt(M[r, c]) for c in range(M.shape[1])]
                         for r in range(n)], index=labels[:n],
                        columns=labels[:M.shape[1]])


# ------------------------------------------------------------- Gauss-Seidel
def gauss_seidel_trace(bus, lines, alpha=1.0, tol=1e-6, max_iter=500):
    """Gauss-Seidel as in solver.gauss_seidel, plus an acceleration factor
    (V <- V + alpha (Vcalc - V); PV buses are then rescaled to |Vset|).
    Returns dict(V: list of complex vectors (iteration 0 = start),
    Q: list of PV-bus Q used, dmax, ok)."""
    n = len(bus)
    Y = build_ybus(n, lines, bus)
    t, V0, Psp, Qsp, _, _ = _setup(bus)
    V = V0.astype(complex)
    hist_V, hist_Q, dmax_l = [V.copy()], [np.full(n, np.nan)], []
    for _ in range(max_iter):
        dmax, Qk = 0.0, np.full(n, np.nan)
        for i in range(n):
            if t[i] == "Slack":
                continue
            s = Y[i] @ V - Y[i, i] * V[i]
            Qc = -(np.conj(V[i]) * (Y[i] @ V)).imag if t[i] == "PV" else Qsp[i]
            if t[i] == "PV":
                Qk[i] = Qc
            new = ((Psp[i] - 1j * Qc) / np.conj(V[i]) - s) / Y[i, i]
            if alpha != 1.0:
                new = V[i] + alpha * (new - V[i])
            if t[i] == "PV":
                new = V0[i] * new / abs(new)
            dmax = max(dmax, abs(new - V[i]))
            V[i] = new
        hist_V.append(V.copy())
        hist_Q.append(Qk)
        dmax_l.append(dmax)
        if dmax < tol:
            return dict(V=hist_V, Q=hist_Q, dmax=dmax_l, ok=True, Y=Y)
    return dict(V=hist_V, Q=hist_Q, dmax=dmax_l, ok=False, Y=Y)


# ----------------------------------------------------------- Newton-Raphson
def jacobian(Y, V, th, ang, mag):
    """Analytical polar Jacobian blocks (J1 = dP/dδ, J2 = dP/d|V|,
    J3 = dQ/dδ, J4 = dQ/d|V|) for the unknowns ang (δ) and mag (|V|)."""
    Vc = V * np.exp(1j * th)
    I = Y @ Vc
    dS_dth = 1j * np.diag(Vc) @ np.conj(np.diag(I) - Y @ np.diag(Vc))
    dS_dV = np.diag(Vc) @ np.conj(Y @ np.diag(Vc / V)) + \
        np.conj(np.diag(I)) @ np.diag(Vc / V)
    return (dS_dth.real[np.ix_(ang, ang)], dS_dV.real[np.ix_(ang, mag)],
            dS_dth.imag[np.ix_(mag, ang)], dS_dV.imag[np.ix_(mag, mag)])


def newton_trace(bus, lines, tol=1e-8, max_iter=30):
    """Newton-Raphson with the analytical Jacobian; one record per iteration:
    dict(k, dP, dQ, J1..J4, dth, dV, th, V) where dP = Psp - Pcalc."""
    n = len(bus)
    Y = build_ybus(n, lines, bus)
    t, V, Psp, Qsp, ang, mag = _setup(bus)
    th = np.zeros(n)
    its = []
    for k in range(1, max_iter + 1):
        S = (V * np.exp(1j * th)) * np.conj(Y @ (V * np.exp(1j * th)))
        dP, dQ = (Psp - S.real)[ang], (Qsp - S.imag)[mag]
        err = max(abs(dP).max(initial=0), abs(dQ).max(initial=0))
        if err < tol:
            its.append(dict(k=k, dP=dP, dQ=dQ, err=err, done=True,
                            th=th.copy(), V=V.copy()))
            return dict(its=its, ok=True, Y=Y, ang=ang, mag=mag)
        J1, J2, J3, J4 = jacobian(Y, V, th, ang, mag)
        J = np.block([[J1, J2], [J3, J4]])
        dx = np.linalg.solve(J, np.r_[dP, dQ])
        th, V = th.copy(), V.copy()
        th[ang] += dx[:len(ang)]
        V[mag] += dx[len(ang):]
        its.append(dict(k=k, dP=dP, dQ=dQ, err=err, done=False,
                        J1=J1, J2=J2, J3=J3, J4=J4,
                        dth=dx[:len(ang)], dV=dx[len(ang):],
                        th=th.copy(), V=V.copy()))
    return dict(its=its, ok=False, Y=Y, ang=ang, mag=mag)


# ----------------------------------------------------------- Fast Decoupled
def fd_matrices(bus, lines):
    """B' (from series X only, reduced to the angle unknowns) and B''
    (-Im Ybus reduced to the |V| unknowns), as in solver.fast_decoupled."""
    n = len(bus)
    Y = build_ybus(n, lines, bus)
    _, _, _, _, ang, mag = _setup(bus)
    Bp = np.zeros((n, n))
    for _, l in in_service(lines).iterrows():
        i, j = int(l["From"]) - 1, int(l["To"]) - 1
        if l["X"] == 0:
            raise ValueError(f"Fast Decoupled needs X ≠ 0 on every line (line {i + 1}-{j + 1} "
                             "has X = 0): B' is 1/X. Use Newton-Raphson for this case.")
        b = 1 / l["X"]
        Bp[i, i] += b
        Bp[j, j] += b
        Bp[i, j] -= b
        Bp[j, i] -= b
    return Bp[np.ix_(ang, ang)], -Y.imag[np.ix_(mag, mag)], ang, mag, Y


def fast_decoupled_trace(bus, lines, tol=1e-8, max_iter=200):
    """Fast Decoupled iterations: dP/V -> dθ, then dQ/V -> d|V|."""
    B1, B2, ang, mag, Y = fd_matrices(bus, lines)
    _, V, Psp, Qsp, _, _ = _setup(bus)
    th = np.zeros(len(V))
    its = []
    for k in range(1, max_iter + 1):
        S = (V * np.exp(1j * th)) * np.conj(Y @ (V * np.exp(1j * th)))
        dP, dQ = (Psp - S.real)[ang], (Qsp - S.imag)[mag]
        err = max(abs(dP).max(initial=0), abs(dQ).max(initial=0))
        if err < tol:
            its.append(dict(k=k, err=err, done=True, th=th.copy(), V=V.copy()))
            return dict(its=its, ok=True, B1=B1, B2=B2, ang=ang, mag=mag)
        dth = np.linalg.solve(B1, dP / V[ang])
        th = th.copy()
        th[ang] += dth
        dV = np.zeros(0)
        if len(mag):
            S = (V * np.exp(1j * th)) * np.conj(Y @ (V * np.exp(1j * th)))
            dQ = (Qsp - S.imag)[mag]
            dV = np.linalg.solve(B2, dQ / V[mag])
            V = V.copy()
            V[mag] += dV
        its.append(dict(k=k, err=err, done=False, dP=dP, dQ=dQ, dth=dth,
                        dV=dV, th=th.copy(), V=V.copy()))
    return dict(its=its, ok=False, B1=B1, B2=B2, ang=ang, mag=mag)


# ------------------------------------------------------------ answer text
def _table(df):
    return df.to_string(index=False)


def results_tables(res, flows, bus, base):
    """Bus and line results in MW / MVAr, textbook style."""
    Pd = bus["Pd"].astype(float).values * base
    Qd = bus["Qd"].astype(float).values * base
    gen = bus["Type"].values != "PQ"
    Pg = np.where(gen, res["P_inj"].values * base + Pd, 0.0)
    Qg = np.where(gen, res["Q_inj"].values * base + Qd, 0.0)
    b = pd.DataFrame({
        "Bus": res["Bus"], "Type": bus["Type"].values,
        "|V| (pu)": res["V (pu)"].round(4), "δ (deg)": res["Angle (deg)"].round(3),
        "Pg (MW)": Pg.round(3), "Qg (MVAr)": Qg.round(3),
        "Pd (MW)": Pd.round(3), "Qd (MVAr)": Qd.round(3)})
    f = pd.DataFrame({
        "Line": [f"{a}-{c}" for a, c in zip(flows["From"], flows["To"])],
        "P i→j (MW)": (flows["P_ij"] * base).round(3),
        "Q i→j (MVAr)": (flows["Q_ij"] * base).round(3),
        "P j→i (MW)": (flows["P_ji"] * base).round(3),
        "Q j→i (MVAr)": (flows["Q_ji"] * base).round(3),
        "Loss (MW)": (flows["Loss_P"] * base).round(4),
        "Loss (MVAr)": (flows["Loss_Q"] * base).round(4)})
    return b, f


def answer_text(bus, lines, res, flows, base, method, trace=None,
                conversion=None, title="Load flow solution"):
    """Plain-text worked solution: given data -> per unit -> Ybus ->
    iterations -> final results."""
    n = len(bus)
    Y = build_ybus(n, lines, bus)
    out = [title.upper(), "=" * len(title), "",
           f"Base: {base:g} MVA.  Method: {method}.", ""]
    if conversion is not None:
        out += ["1. PER-UNIT CONVERSION", "", "Base values per zone:",
                _table(conversion["zones"].round(4)), "",
                _table(conversion["table"].round(6)), ""]
    out += [f"{'2' if conversion is not None else '1'}. GIVEN DATA (per unit)",
            "", "Buses:", _table(bus[[c for c in ("Type", "V", "Pg", "Qg", "Pd",
                                                    "Qd", "Bs") if c in bus]]
                                 .assign(Bus=range(1, n + 1))
                                 .set_index("Bus").reset_index()),
            "", "Lines (From = tap side):", _table(lines), ""]
    sec = 3 if conversion is not None else 2
    out += [f"{sec}. BUS ADMITTANCE MATRIX Ybus (pu)", "",
            matrix_text(Y).to_string(), ""]
    sec += 1
    out += [f"{sec}. ITERATIONS ({method})", ""]
    if trace is not None:
        out += trace
    sec += 1
    b, f = results_tables(res, flows, bus, base)
    k = int(np.where(bus["Type"].values == "Slack")[0][0])
    out += ["", f"{sec}. RESULTS", "", "Bus voltages and powers:", _table(b), "",
            f"Slack bus {k + 1} power: S = {res['P_inj'].iloc[k] * base + b['Pd (MW)'].iloc[k]:.3f}"
            f" + j{res['Q_inj'].iloc[k] * base + b['Qd (MVAr)'].iloc[k]:.3f} MVA", "",
            "Line flows and losses:", _table(f), "",
            f"Total losses: {flows['Loss_P'].sum() * base:.4f} MW, "
            f"{flows['Loss_Q'].sum() * base:.4f} MVAr"]
    return "\n".join(out)


def trace_lines(method, bus, lines, alpha=1.0, tol=1e-8, show=2):
    """The ITERATIONS section of the answer for a method (first `show`
    iterations in full, then the count)."""
    lab = [str(i + 1) for i in range(len(bus))]
    if method == "Gauss-Seidel":
        tr = gauss_seidel_trace(bus, lines, alpha, max(tol, 1e-10))
        out = [f"Acceleration factor α = {alpha:g}. Start: flat start "
               "(PQ buses 1∠0°, PV at |Vset|)."]
        for k in range(1, min(show, len(tr["V"]) - 1) + 1):
            out.append(f"Iteration {k}: " + "  ".join(
                f"V{lab[i]} = {pfmt(v)}" for i, v in enumerate(tr["V"][k])))
        out.append(f"Converged in {len(tr['dmax'])} iterations "
                   f"(max |ΔV| = {tr['dmax'][-1]:.2e})." if tr["ok"]
                   else "Did not converge.")
        return out
    if method == "Fast Decoupled":
        tr = fast_decoupled_trace(bus, lines, tol)
        out = ["B' (series X only, angle unknowns):",
               pd.DataFrame(tr["B1"], index=[f"δ{lab[i]}" for i in tr["ang"]],
                            columns=[f"δ{lab[i]}" for i in tr["ang"]]).round(4).to_string(),
               "", "B'' (-Im Ybus, |V| unknowns):",
               pd.DataFrame(tr["B2"], index=[f"V{lab[i]}" for i in tr["mag"]],
                            columns=[f"V{lab[i]}" for i in tr["mag"]]).round(4).to_string(), ""]
        for it in tr["its"][:show]:
            if it["done"]:
                break
            out.append(f"Iteration {it['k']}: Δδ = {np.round(np.degrees(it['dth']), 4).tolist()} deg, "
                       f"Δ|V| = {np.round(it['dV'], 5).tolist()}")
        out.append(f"Converged after {len(tr['its']) - 1} iterations." if tr["ok"]
                   else "Did not converge.")
        return out
    tr = newton_trace(bus, lines, tol)
    out = []
    for it in tr["its"][:show]:
        if it["done"]:
            break
        rows = [f"P{lab[i]}" for i in tr["ang"]] + [f"Q{lab[i]}" for i in tr["mag"]]
        cols = [f"δ{lab[i]}" for i in tr["ang"]] + [f"|V{lab[i]}|" for i in tr["mag"]]
        J = np.block([[it["J1"], it["J2"]], [it["J3"], it["J4"]]])
        out += [f"Iteration {it['k']}:",
                "Mismatch [ΔP; ΔQ] = " + ", ".join(
                    f"{r} {v:.5f}" for r, v in zip(rows, np.r_[it["dP"], it["dQ"]])),
                "Jacobian [J1 J2; J3 J4]:",
                pd.DataFrame(J, index=rows, columns=cols).round(4).to_string(),
                "Corrections: " + ", ".join(
                    [f"Δδ{lab[i]} {np.degrees(d):.4f}°" for i, d in zip(tr["ang"], it["dth"])]
                    + [f"Δ|V{lab[i]}| {d:.5f}" for i, d in zip(tr["mag"], it["dV"])]), ""]
    out.append(f"Converged after {len(tr['its']) - 1} iterations." if tr["ok"]
               else "Did not converge.")
    return out
