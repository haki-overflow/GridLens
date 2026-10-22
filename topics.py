"""Textbook calculators, one file: symmetrical components, transmission line
ABCD, sequence-network faults (SLG / LL / DLG), economic dispatch, and real
units -> per unit. Pure functions, no Streamlit. Sections in that order.
"""
import numpy as np
import pandas as pd


# ============================================================================
# Symmetrical components
# Symmetrical components: phase (a, b, c) <-> sequence (0, 1, 2).
# 
# a = 1∠120°,  [Va; Vb; Vc] = A [V0; V1; V2],  A = [[1, 1, 1], [1, a², a],
# [1, a, a²]],  [V0; V1; V2] = (1/3) [[1, 1, 1], [1, a, a²], [1, a², a]] [Va; Vb; Vc].
# ============================================================================

a = np.exp(2j * np.pi / 3)
A = np.array([[1, 1, 1], [1, a**2, a], [1, a, a**2]])
A_INV = np.array([[1, 1, 1], [1, a, a**2], [1, a**2, a]]) / 3


def polar(mag, deg):
    return mag * np.exp(1j * np.radians(deg))


def to_sequence(abc):
    """[Va, Vb, Vc] -> [V0, V1, V2]."""
    return A_INV @ np.asarray(abc, complex)


def to_phase(s012):
    """[V0, V1, V2] -> [Va, Vb, Vc]."""
    return A @ np.asarray(s012, complex)


# ============================================================================
# Transmission line (ABCD)
# Transmission line ABCD parameters, voltage regulation and efficiency.
# 
# Per-phase models from per-km series impedance z = R + jX (Ω/km) and shunt
# admittance y = jB (S/km) over a length l:
#   short       A = D = 1, B = Z, C = 0
#   medium (π)  A = D = 1 + ZY/2, B = Z, C = Y (1 + ZY/4)
#   long        γ = √(zy), Zc = √(z/y), A = D = cosh γl, B = Zc sinh γl,
#               C = sinh γl / Zc
# V_S = A V_R + B I_R, I_S = C V_R + D I_R (per phase, kV and kA).
# Regulation % = (|V_S|/|A| − |V_R|) / |V_R| · 100, efficiency = P_R / P_S.
# ============================================================================

MODELS = ("short", "medium (π)", "long")


def abcd(model, R, X, B_uS, length):
    """ABCD constants (B in Ω, C in S) for one of MODELS."""
    z, y = complex(R, X), complex(0, B_uS * 1e-6)
    Z, Y = z * length, y * length
    if model == "short":
        return 1 + 0j, Z, 0j, 1 + 0j
    if model == "medium (π)":
        A = 1 + Z * Y / 2
        return A, Z, Y * (1 + Z * Y / 4), A
    if model == "long":
        g, zc = np.sqrt(z * y), np.sqrt(z / y)
        A = np.cosh(g * length)
        return A, zc * np.sinh(g * length), np.sinh(g * length) / zc, A
    raise ValueError(f"model must be one of {MODELS}")


def performance(model, R, X, B_uS, length, VR_kV, PR_MW, pf, lagging=True):
    """Sending-end quantities for a 3-phase load at the receiving end
    (VR_kV line-to-line, PR_MW three-phase, power factor pf)."""
    A, B, C, D = abcd(model, R, X, B_uS, length)
    VR = VR_kV / np.sqrt(3) + 0j                                   # kV per phase
    phi = np.arccos(pf) * (-1 if lagging else 1)
    IR = PR_MW / (np.sqrt(3) * VR_kV * pf) * np.exp(1j * phi)      # kA
    VS = A * VR + B * IR
    IS = C * VR + D * IR
    SS, SR = 3 * VS * np.conj(IS), 3 * VR * np.conj(IR)            # MVA
    out = dict(A=A, B=B, C=C, D=D, VR=VR, IR=IR, VS=VS, IS=IS, SS=SS, SR=SR,
               VS_LL=abs(VS) * np.sqrt(3),
               reg=(abs(VS) / abs(A) - abs(VR)) / abs(VR) * 100,
               eff=SR.real / SS.real * 100, loss=SS.real - SR.real,
               check=A * D - B * C)
    if model == "long":
        z, y = complex(R, X), complex(0, B_uS * 1e-6)
        out.update(gamma=np.sqrt(z * y), Zc=np.sqrt(z / y),
                   SIL=VR_kV ** 2 / abs(np.sqrt(z / y)))
    return out


# ============================================================================
# Sequence-network faults
# Unsymmetrical faults with sequence networks (3-phase, SLG, LL, DLG).
# 
# Networks are reactance-only, as in the textbook method (loads neglected).
# 
# gens      Bus, X1, X2, X0, Xn (neutral reactance), Conn ("Yg" | "Y" | "D")
# branches  From, To, Kind ("line" | "transformer"), X1, X2, X0,
#           Conn From, Conn To ("Yg" | "Y" | "D", transformers only)
# 
# Zero-sequence paths (standard connection table):
#   line                 series X0
#   transformer Yg-Yg    series X0
#   transformer Yg-D     X0 from the Yg-side bus to ground; D side open
#   any other pair       open (no zero-sequence current passes)
#   generator Yg         X0 + 3 Xn to ground; Y or D: open
# Delta-wye phase shifts are not modelled (sequence magnitudes are right,
# angles across a D-Y transformer are not shifted by 30°).
# 
# Fault currents use each faulted bus's own base kV for kA.
# ============================================================================

A_OP = np.exp(2j * np.pi / 3)
A_SEQ = np.array([[1, 1, 1], [1, A_OP**2, A_OP], [1, A_OP, A_OP**2]])
TYPES = ("3-phase", "SLG", "LL", "DLG")
OPEN = 1e9          # stand-in impedance for "no zero-sequence path"


def _y(x):
    if float(x) == 0:   # e.g. seeded from a resistance-only line (X = 0)
        raise ValueError("a sequence reactance is 0: the sequence networks are reactance "
                         "only, so give every generator and branch a reactance in the "
                         "sequence data.")
    return 1 / complex(0, float(x))


def seq_ybus(n, gens, branches, seq):
    """Ybus of sequence network seq (0, 1 or 2)."""
    col = f"X{seq}"
    Y = np.zeros((n, n), complex)
    for _, g in gens.iterrows():
        i = int(g["Bus"]) - 1
        if seq == 0:
            if str(g.get("Conn", "Yg")) == "Yg":
                Y[i, i] += _y(float(g["X0"]) + 3 * float(g.get("Xn", 0) or 0))
        else:
            Y[i, i] += _y(g[col])
    for _, r in branches.iterrows():
        i, j = int(r["From"]) - 1, int(r["To"]) - 1
        y = _y(r[col])
        if seq == 0 and str(r.get("Kind", "line")) == "transformer":
            cf, ct = str(r.get("Conn From", "Yg")), str(r.get("Conn To", "Yg"))
            if cf == "Yg" and ct == "Yg":
                pass                          # series path, below
            elif cf == "Yg" and ct == "D":
                Y[i, i] += y
                continue
            elif cf == "D" and ct == "Yg":
                Y[j, j] += y
                continue
            else:
                continue
        Y[i, i] += y
        Y[j, j] += y
        Y[i, j] -= y
        Y[j, i] -= y
    return Y


def seq_zbus(n, gens, branches):
    """[Z0, Z1, Z2]; buses with no path to ground in a sequence network get
    a tiny admittance to ground, so their Zkk is huge (current ~ 0)."""
    out = []
    for s in (0, 1, 2):
        Y = seq_ybus(n, gens, branches, s) + np.eye(n) / OPEN
        out.append(np.linalg.inv(Y))
    return out


def fault_currents(kind, Z0, Z1, Z2, vf, zf):
    """Sequence fault currents (I0, I1, I2) for a fault through zf at a bus
    with Thevenin impedances Z0, Z1, Z2 and prefault voltage vf."""
    if kind == "3-phase":
        I1 = vf / (Z1 + zf)
        return 0j, I1, 0j
    if kind == "SLG":
        I = vf / (Z1 + Z2 + Z0 + 3 * zf)
        return I, I, I
    if kind == "LL":
        I1 = vf / (Z1 + Z2 + zf)
        return 0j, I1, -I1
    if kind == "DLG":
        z0 = Z0 + 3 * zf
        I1 = vf / (Z1 + Z2 * z0 / (Z2 + z0))
        return -I1 * Z2 / (Z2 + z0), I1, -I1 * z0 / (Z2 + z0)
    raise ValueError(f"fault type must be one of {TYPES}")


def solve_fault(kind, k, gens, branches, vf, zf=0j, base=100.0, kv=None):
    """Fault of type kind at bus k (1-based). vf: prefault voltages (complex,
    one per bus). Returns dict with sequence/phase currents at the fault,
    sequence/phase voltages at every bus and sequence currents in branches."""
    n = len(vf)
    Z0, Z1, Z2 = seq_zbus(n, gens, branches)
    i = k - 1
    I0, I1, I2 = fault_currents(kind, Z0[i, i], Z1[i, i], Z2[i, i], vf[i], zf)
    Iabc = A_SEQ @ np.array([I0, I1, I2])
    Vs = np.vstack([-Z0[:, i] * I0, vf - Z1[:, i] * I1, -Z2[:, i] * I2]).T
    Vabc = Vs @ A_SEQ.T
    kv = np.full(n, np.nan) if kv is None else np.asarray(kv, float)
    ib = base / (np.sqrt(3) * kv)        # kA per pu at each bus
    rows = []
    for _, r in branches.iterrows():
        a, b = int(r["From"]) - 1, int(r["To"]) - 1
        I = []
        for s, V in ((0, Vs[:, 0]), (1, Vs[:, 1]), (2, Vs[:, 2])):
            x = float(r[f"X{s}"])
            passes = s != 0 or str(r.get("Kind", "line")) == "line" or (
                str(r.get("Conn From", "Yg")) == "Yg" and str(r.get("Conn To", "Yg")) == "Yg")
            I.append((V[a] - V[b]) / complex(0, x) if passes else 0j)
        Ip = A_SEQ @ np.array(I)
        rows.append([f"{a + 1}-{b + 1}", *I, *Ip])
    lines = pd.DataFrame(rows, columns=["Branch", "I0", "I1", "I2", "Ia", "Ib", "Ic"])
    return dict(I012=np.array([I0, I1, I2]), Iabc=Iabc, V012=Vs, Vabc=Vabc,
                lines=lines, kA=abs(Iabc) * ib[i], Ibase_kA=ib[i],
                Zth=(Z0[i, i], Z1[i, i], Z2[i, i]))


def fault_table(kind, gens, branches, vf, zf=0j, base=100.0, kv=None):
    """Fault current at every bus for one fault type: the largest phase
    current in pu, kA (bus's own base kV) and MVA."""
    n = len(vf)
    Z0, Z1, Z2 = seq_zbus(n, gens, branches)
    kv = np.full(n, np.nan) if kv is None else np.asarray(kv, float)
    rows = []
    for i in range(n):
        I = A_SEQ @ np.array(fault_currents(kind, Z0[i, i], Z1[i, i], Z2[i, i],
                                        vf[i], zf))
        imax = abs(I).max()
        rows.append([i + 1, kv[i], imax, imax * base / (np.sqrt(3) * kv[i]),
                     imax * base])
    return pd.DataFrame(rows, columns=["Bus", "Base kV", "If (pu)", "If (kA)",
                                       "Fault MVA"])


def seed_tables(bus, lines):
    """Default sequence data for a solved case: generators X1 = X2 = 0.2,
    X0 = 0.05 solidly grounded; lines X1 = X2 = X, X0 = 3X; branches with
    an off-nominal tap are treated as Yg-Yg transformers with X0 = X."""
    gb = [i + 1 for i, t in enumerate(bus["Type"]) if t != "PQ"]
    gens = pd.DataFrame({"Bus": gb, "X1": 0.2, "X2": 0.2, "X0": 0.05,
                         "Xn": 0.0, "Conn": "Yg"})
    tr = (lines["Tap"].astype(float) - 1).abs() > 1e-9 if "Tap" in lines \
        else pd.Series(False, index=lines.index)
    X = lines["X"].astype(float)
    br = pd.DataFrame({"From": lines["From"].astype(int).values,
                       "To": lines["To"].astype(int).values,
                       "Kind": np.where(tr, "transformer", "line"),
                       "X1": X.values, "X2": X.values,
                       "X0": np.where(tr, X, 3 * X),
                       "Conn From": "Yg", "Conn To": "Yg"})
    return gens, br


# ============================================================================
# Economic dispatch
# Economic dispatch by lambda iteration (equal incremental cost).
# 
# Units: cost C_i = a_i + b_i P_i + c_i P_i² ($/h, P in MW); limits
# Pmin/Pmax in MW. Losses by Kron's B-coefficient formula with P in MW:
# P_L = Pᵀ B P + B0ᵀ P + B00 (B in 1/MW, B0 dimensionless, B00 in MW);
# b_from_pu converts coefficients given on an MVA base.
# 
# Each iteration: P_i from the coordination equation
#     P_i = (λ(1 - B0_i) - b_i - 2λ Σ_{j≠i} B_ij P_j) / (2 (c_i + λ B_ii)),
# clamped to its limits, then ΔP = P_D + P_L - ΣP and
#     Δλ = ΔP / Σ ∂P_i/∂λ  (free units only),
#     ∂P_i/∂λ = (c_i (1 - B0_i) + B_ii b_i - 2 c_i Σ_{j≠i} B_ij P_j)
#               / (2 (c_i + λ B_ii)²).
# ============================================================================

def b_from_pu(B, B0, B00, base):
    """B-coefficients given in per unit on `base` MVA -> MW units."""
    return np.asarray(B, float) / base, np.asarray(B0, float), float(B00) * base


def losses(P, B, B0, B00):
    P = np.asarray(P, float)
    return float(P @ B @ P + B0 @ P + B00)


def dispatch(units, PD, B=None, B0=None, B00=0.0, use_limits=True,
             tol=1e-6, max_iter=200):
    """units: DataFrame with a, b, c (and Pmin, Pmax). Returns dict(P, lam,
    PL, cost, ok, its: DataFrame of iterations, table: per-unit summary)."""
    a, b, c = (units[k].astype(float).to_numpy() for k in ("a", "b", "c"))
    n = len(a)
    lo = units["Pmin"].astype(float).to_numpy() if use_limits and "Pmin" in units \
        else np.full(n, -np.inf)
    hi = units["Pmax"].astype(float).to_numpy() if use_limits and "Pmax" in units \
        else np.full(n, np.inf)
    B = np.zeros((n, n)) if B is None else np.asarray(B, float)
    B0 = np.zeros(n) if B0 is None else np.asarray(B0, float)
    lam = (PD + np.sum(b / (2 * c))) / np.sum(1 / (2 * c))   # lossless start
    P = np.clip((lam - b) / (2 * c), lo, hi)
    rows, ok = [], False
    for k in range(1, max_iter + 1):
        off = B @ P - np.diag(B) * P                     # Σ_{j≠i} B_ij P_j
        P = (lam * (1 - B0) - b - 2 * lam * off) / (2 * (c + lam * np.diag(B)))
        P = np.clip(P, lo, hi)
        free = (P > lo + 1e-9) & (P < hi - 1e-9)
        PL = losses(P, B, B0, B00)
        dP = PD + PL - P.sum()
        rows.append([k, lam, *P, PL, dP])
        if abs(dP) < tol:
            ok = True
            break
        off = B @ P - np.diag(B) * P
        dPdl = (c * (1 - B0) + np.diag(B) * b - 2 * c * off) / \
            (2 * (c + lam * np.diag(B)) ** 2)
        s = dPdl[free].sum()
        if s <= 0:                                        # every unit at a limit
            break
        lam += dP / s
    its = pd.DataFrame(rows, columns=["Iter", "λ ($/MWh)"]
                       + [f"P{i + 1} (MW)" for i in range(n)] + ["PL (MW)", "ΔP (MW)"])
    dPL = 2 * B @ P + B0
    ic = b + 2 * c * P
    table = pd.DataFrame({
        "Unit": np.arange(1, n + 1), "P (MW)": P, "IC = b + 2cP": ic,
        "∂PL/∂Pi": dPL, "Penalty L = 1/(1 - ∂PL/∂Pi)": 1 / (1 - dPL),
        "L·IC": ic / (1 - dPL), "At limit": np.where(free, "", "yes"),
        "Cost ($/h)": a + b * P + c * P**2})
    return dict(P=P, lam=lam, PL=losses(P, B, B0, B00),
                cost=float(np.sum(a + b * P + c * P**2)), ok=ok, its=its,
                table=table)


DISPATCH_EXAMPLE = dict(
    units=pd.DataFrame({"a": [200.0, 180.0, 140.0], "b": [7.0, 6.3, 6.8],
                        "c": [0.008, 0.009, 0.007], "Pmin": [10.0, 10.0, 10.0],
                        "Pmax": [85.0, 80.0, 70.0]}),
    PD=150.0, base=100.0,
    B=[[0.0218, 0.0093, 0.0028], [0.0093, 0.0228, 0.0017],
       [0.0028, 0.0017, 0.0179]],
    B0=[0.0003, 0.0031, 0.0015], B00=0.00030523,
)


# ============================================================================
# Real units to per unit
# Real units -> per unit, the way textbook problems give the data.
# 
# Input tables (one row per item, buses numbered by row order like the rest
# of GridLens):
# 
# buses   Type, V (pu), Pg (MW), Qg (MVAr), Pd (MW), Qd (MVAr),
#         Qmin (MVAr), Qmax (MVAr), Shunt (MVAr at 1 pu, + = capacitive)
# lines   From, To, R, X, Z unit ("ohm" | "ohm/km"), Length (km),
#         B, B unit ("uS" | "uS/km" | "MVAr" = total charging at base kV)
# trafos  From, To, kV From, kV To (rated), MVA (rating),
#         R, X (pu on own rating), Tap (off-nominal, at the From side)
# 
# Zones: buses joined by lines share a base kV; a transformer moves to the
# next zone with base_to = base_from * kV_To / kV_From. The base kV of one
# reference bus is given, the rest follows.
# ============================================================================

Z_UNITS = ("ohm", "ohm/km")
B_UNITS = ("uS", "uS/km", "MVAr")


def _num(df, col, fill=0.0):
    return pd.to_numeric(df[col], errors="coerce").fillna(fill).to_numpy(float) \
        if col in df else np.full(len(df), fill)


def zones(n, lines, trafos, ref_bus, ref_kv):
    """Zone index and base kV per bus. Raises ValueError on a bus that no
    line or transformer reaches, or on a loop with inconsistent ratios."""
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for f, t in zip(_num(lines, "From").astype(int), _num(lines, "To").astype(int)):
        parent[find(f - 1)] = find(t - 1)
    roots = sorted({find(i) for i in range(n)})
    zone = np.array([roots.index(find(i)) for i in range(n)])
    kv = {zone[ref_bus - 1]: float(ref_kv)}
    links = [(zone[int(f) - 1], zone[int(t) - 1], float(kf), float(kt))
             for f, t, kf, kt in zip(_num(trafos, "From"), _num(trafos, "To"),
                                     _num(trafos, "kV From"), _num(trafos, "kV To"))]
    changed = True
    while changed:
        changed = False
        for zf, zt, kf, kt in links:
            for a, b, ka, kb in ((zf, zt, kf, kt), (zt, zf, kt, kf)):
                if a in kv:
                    want = kv[a] * kb / ka
                    if b not in kv:
                        kv[b] = want
                        changed = True
                    elif abs(kv[b] - want) > 1e-6 * want:
                        raise ValueError(
                            f"Transformer ratios disagree around zone {b + 1}: "
                            f"{kv[b]:g} kV vs {want:g} kV.")
    missing = sorted({i + 1 for i in range(n) if zone[i] not in kv})
    if missing:
        raise ValueError("No base kV reaches bus(es) "
                         + ", ".join(map(str, missing))
                         + ": connect them by a line or transformer.")
    return zone, np.array([kv[z] for z in zone])


def to_pu(sbase, ref_bus, ref_kv, buses, lines, trafos):
    """Convert the three real-unit tables to the GridLens per-unit data model.

    Returns dict(bus, lines, kv, zones, table): bus/lines are ready for
    solve_loadflow (bus also carries Qmin/Qmax in pu and kV = base kV),
    zones is the base table per zone and table lists every conversion."""
    n = len(buses)
    zone, kv = zones(n, lines, trafos, ref_bus, ref_kv)
    zbase = kv ** 2 / sbase
    rows = []

    def note(item, given, unit, base, pu):
        rows.append([item, given, unit, base, pu])

    pu = pd.DataFrame({"Type": buses["Type"].astype(str).to_numpy(),
                       "V": _num(buses, "V", 1.0)})
    for col, unit in (("Pg", "MW"), ("Qg", "MVAr"), ("Pd", "MW"), ("Qd", "MVAr")):
        val = _num(buses, col)
        pu[col] = val / sbase
        for i in np.flatnonzero(val):
            note(f"Bus {i + 1} {col}", val[i], unit, f"{sbase:g} MVA", val[i] / sbase)
    sh = _num(buses, "Shunt")
    pu["Bs"] = sh / sbase
    for i in np.flatnonzero(sh):
        note(f"Bus {i + 1} shunt", sh[i], "MVAr", f"{sbase:g} MVA", sh[i] / sbase)
    for col in ("Qmin", "Qmax"):
        val = _num(buses, col, -9999.0 if col == "Qmin" else 9999.0)
        pu[col] = val / sbase
    pu["kV"] = kv

    out = []
    for k, r in lines.reset_index(drop=True).iterrows():
        i, j = int(r["From"]) - 1, int(r["To"]) - 1
        zb, name = zbase[i], f"Line {i + 1}-{j + 1}"
        length = float(r.get("Length", 0) or 0)
        per_km = str(r.get("Z unit", "ohm")) == "ohm/km"
        R = float(r["R"]) * (length if per_km else 1.0)
        X = float(r["X"]) * (length if per_km else 1.0)
        bu, Bv = str(r.get("B unit", "uS")), float(r.get("B", 0) or 0)
        if bu == "MVAr":
            Bpu = Bv / sbase
            note(f"{name} charging", Bv, "MVAr", f"{sbase:g} MVA", Bpu)
        else:
            Bs = Bv * 1e-6 * (length if bu == "uS/km" else 1.0)
            Bpu = Bs * zb
            note(f"{name} B", Bs * 1e6, "µS", f"Ybase {1e6 / zb:.4g} µS", Bpu)
        note(f"{name} R", R, "Ω", f"Zbase {zb:.4g} Ω", R / zb)
        note(f"{name} X", X, "Ω", f"Zbase {zb:.4g} Ω", X / zb)
        out.append([i + 1, j + 1, R / zb, X / zb, Bpu, 1.0])
    for _, r in trafos.reset_index(drop=True).iterrows():
        i, j = int(r["From"]) - 1, int(r["To"]) - 1
        name = f"Trafo {i + 1}-{j + 1}"
        kf, kt, mva = float(r["kV From"]), float(r["kV To"]), float(r["MVA"])
        scale = (sbase / mva) * (kf / kv[i]) ** 2
        R, X = float(r.get("R", 0) or 0), float(r["X"])
        tap = float(r.get("Tap", 1) or 1) * (kf / kt) / (kv[i] / kv[j])
        note(f"{name} X", X, f"pu on {mva:g} MVA, {kf:g} kV",
             f"{sbase:g} MVA, {kv[i]:g} kV", X * scale)
        if R:
            note(f"{name} R", R, f"pu on {mva:g} MVA, {kf:g} kV",
                 f"{sbase:g} MVA, {kv[i]:g} kV", R * scale)
        if abs(tap - 1) > 1e-9:
            note(f"{name} tap", float(r.get("Tap", 1) or 1), "ratio",
                 "nominal", tap)
        out.append([i + 1, j + 1, R * scale, X * scale, 0.0, tap])
    lpu = pd.DataFrame(out, columns=["From", "To", "R", "X", "B", "Tap"])

    zt = pd.DataFrame({"Zone": np.arange(1, zone.max() + 2)})
    zt["Buses"] = [", ".join(str(i + 1) for i in np.flatnonzero(zone == z))
                   for z in range(len(zt))]
    zt["Base kV"] = [kv[zone == z][0] for z in range(len(zt))]
    zt["Zbase (Ω)"] = zt["Base kV"] ** 2 / sbase
    zt["Ibase (A)"] = sbase * 1e3 / (np.sqrt(3) * zt["Base kV"])
    table = pd.DataFrame(rows, columns=["Item", "Given", "Unit", "Base", "Per unit"])
    return dict(bus=pu, lines=lpu, kv=kv, zones=zt, table=table)


# ------------------------------------------- case in actual units -> pu
# A whole case typed in actual units (case setting units = "actual"), the
# way textbook questions give it. Each bus carries its base kV; every branch
# is converted on the base of its From bus:
#   bus     V (pu), Pg Pd Qmin... in MW / MVAr, Bs / Gs in MVAr / MW drawn at
#           1 pu voltage (Bs > 0 = capacitor), kV = base kV
#   branch  R, X in ohm (a transformer: referred to its From side), B in uS
#           (total line charging), Rate in MVA, Tap and Shift unchanged
# Zbase = kV_from^2 / Sbase, Ybase = 1 / Zbase, Pbase = Sbase.

BUS_MW = ("Pg", "Qg", "Pd", "Qd", "Qmin", "Qmax", "Bs", "Gs")


def case_to_pu(bus, lines, sbase):
    """Actual-unit case -> per-unit (bus, lines, table, problems, notes)."""
    b, l = bus.copy(), lines.copy()
    probs, notes, rows = [], [], []
    kv = _num(b, "kV", np.nan)
    missing = [i + 1 for i, v in enumerate(kv) if not np.isfinite(v) or v <= 0]
    if missing:
        probs.append("Actual units need the base kV of every bus (column kV); missing "
                     "or not positive at bus rows " + ", ".join(map(str, missing)) + ".")
        return b, l, pd.DataFrame(), probs, notes
    for c in BUS_MW:
        if c in b:
            given = pd.to_numeric(b[c], errors="coerce")
            b[c] = given / sbase
    rows.append(("Bus powers", "MW, MVAr", f"S base = {sbase:g} MVA", "divide by S base"))
    zb = kv ** 2 / sbase
    f = pd.to_numeric(l["From"], errors="coerce").fillna(0).astype(int).to_numpy() \
        if "From" in l else np.zeros(0, int)
    t = pd.to_numeric(l["To"], errors="coerce").fillna(0).astype(int).to_numpy() \
        if "To" in l else np.zeros(0, int)
    ok = (f >= 1) & (f <= len(b)) & (t >= 1) & (t <= len(b))
    z = np.where(ok, zb[np.clip(f, 1, len(b)) - 1], np.nan)
    for c in ("R", "X"):
        if c in l:
            l[c] = _num(l, c) / z
    if "B" in l:
        l["B"] = _num(l, "B") * 1e-6 * z
    for k in np.flatnonzero(ok):
        name = f"{f[k]}-{t[k]}"
        kf, kt = kv[f[k] - 1], kv[t[k] - 1]
        trafo = str(l["Kind"].iloc[k]).lower() == "trafo" if "Kind" in l else False
        if abs(kf - kt) > 0.01 * max(kf, kt) and not trafo:
            notes.append(f"Branch {name} joins {kf:g} kV and {kt:g} kV buses but is not "
                         "marked as a transformer (Kind = trafo); its ohms were referred to "
                         "the From side.")
        rows.append((f"Branch {name}", "ohm, uS", f"Z base = {kf:g}² / {sbase:g} = "
                     f"{zb[f[k] - 1]:.4g} Ω", f"R = {l['R'].iloc[k]:.5g}, X = "
                     f"{l['X'].iloc[k]:.5g}, B = {l['B'].iloc[k] if 'B' in l else 0:.5g} pu"))
    table = pd.DataFrame(rows, columns=["Item", "Given in", "Base", "Per unit"])
    return b, l, table, probs, notes


UNITS_EXAMPLE = dict(
    sbase=100.0, ref_bus=1, ref_kv=11.0,
    buses=pd.DataFrame({
        "Type": ["Slack", "PQ", "PQ", "PV"], "V": [1.05, 1.0, 1.0, 1.02],
        "Pg": [0.0, 0.0, 0.0, 60.0], "Qg": [0.0] * 4,
        "Pd": [0.0, 0.0, 100.0, 20.0], "Qd": [0.0, 0.0, 50.0, 10.0],
        "Qmin": [-9999.0, -9999.0, -9999.0, -20.0],
        "Qmax": [9999.0, 9999.0, 9999.0, 25.0], "Shunt": [0.0] * 4}),
    lines=pd.DataFrame({
        "From": [2, 3, 2], "To": [3, 4, 4],
        "R": [0.12, 10.0, 12.0], "X": [0.4, 30.0, 40.0],
        "Z unit": ["ohm/km", "ohm", "ohm"], "Length": [80.0, 0.0, 0.0],
        "B": [2.8, 150.0, 10.0], "B unit": ["uS/km", "uS", "MVAr"]}),
    trafos=pd.DataFrame({
        "From": [1], "To": [2], "kV From": [11.0], "kV To": [132.0],
        "MVA": [100.0], "R": [0.0], "X": [0.1], "Tap": [1.0]}),
)
