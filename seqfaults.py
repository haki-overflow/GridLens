"""Unsymmetrical faults with sequence networks (3-phase, SLG, LL, DLG).

Networks are reactance-only, as in the textbook method (loads neglected).

gens      Bus, X1, X2, X0, Xn (neutral reactance), Conn ("Yg" | "Y" | "D")
branches  From, To, Kind ("line" | "transformer"), X1, X2, X0,
          Conn From, Conn To ("Yg" | "Y" | "D", transformers only)

Zero-sequence paths (standard connection table):
  line                 series X0
  transformer Yg-Yg    series X0
  transformer Yg-D     X0 from the Yg-side bus to ground; D side open
  any other pair       open (no zero-sequence current passes)
  generator Yg         X0 + 3 Xn to ground; Y or D: open
Delta-wye phase shifts are not modelled (sequence magnitudes are right,
angles across a D-Y transformer are not shifted by 30°).

Fault currents use each faulted bus's own base kV for kA.
"""
import numpy as np
import pandas as pd

A_OP = np.exp(2j * np.pi / 3)
A = np.array([[1, 1, 1], [1, A_OP**2, A_OP], [1, A_OP, A_OP**2]])
TYPES = ("3-phase", "SLG", "LL", "DLG")
OPEN = 1e9          # stand-in impedance for "no zero-sequence path"


def _y(x):
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
    Iabc = A @ np.array([I0, I1, I2])
    Vs = np.vstack([-Z0[:, i] * I0, vf - Z1[:, i] * I1, -Z2[:, i] * I2]).T
    Vabc = Vs @ A.T
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
        Ip = A @ np.array(I)
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
        I = A @ np.array(fault_currents(kind, Z0[i, i], Z1[i, i], Z2[i, i],
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
