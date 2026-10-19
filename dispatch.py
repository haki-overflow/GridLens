"""Economic dispatch by lambda iteration (equal incremental cost).

Units: cost C_i = a_i + b_i P_i + c_i P_i² ($/h, P in MW); limits
Pmin/Pmax in MW. Losses by Kron's B-coefficient formula with P in MW:
P_L = Pᵀ B P + B0ᵀ P + B00 (B in 1/MW, B0 dimensionless, B00 in MW);
b_from_pu converts coefficients given on an MVA base.

Each iteration: P_i from the coordination equation
    P_i = (λ(1 - B0_i) - b_i - 2λ Σ_{j≠i} B_ij P_j) / (2 (c_i + λ B_ii)),
clamped to its limits, then ΔP = P_D + P_L - ΣP and
    Δλ = ΔP / Σ ∂P_i/∂λ  (free units only),
    ∂P_i/∂λ = (c_i (1 - B0_i) + B_ii b_i - 2 c_i Σ_{j≠i} B_ij P_j)
              / (2 (c_i + λ B_ii)²).
"""
import numpy as np
import pandas as pd


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


EXAMPLE = dict(
    units=pd.DataFrame({"a": [200.0, 180.0, 140.0], "b": [7.0, 6.3, 6.8],
                        "c": [0.008, 0.009, 0.007], "Pmin": [10.0, 10.0, 10.0],
                        "Pmax": [85.0, 80.0, 70.0]}),
    PD=150.0, base=100.0,
    B=[[0.0218, 0.0093, 0.0028], [0.0093, 0.0228, 0.0017],
       [0.0028, 0.0017, 0.0179]],
    B0=[0.0003, 0.0031, 0.0015], B00=0.00030523,
)
