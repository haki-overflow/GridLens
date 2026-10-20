import numpy as np
import pandas as pd

from solver import build_ybus, solve_loadflow


# ------------------------------------------------------ study extras
def branch_names(lines):
    """"From-To" per branch; parallel branches get " (2)", " (3)"..."""
    seen, out = {}, []
    for f, t in zip(lines["From"], lines["To"]):
        key = f"{int(f)}-{int(t)}"
        seen[key] = seen.get(key, 0) + 1
        out.append(key if seen[key] == 1 else f"{key} ({seen[key]})")
    return out


def overloads(flows, lines, base):
    """Branches loaded above their Rate (MVA; 0 or missing = no rating)."""
    if "Rate" not in lines:
        return []
    rate = pd.to_numeric(lines["Rate"], errors="coerce").fillna(0).to_numpy(float)
    s = np.maximum(np.hypot(flows["P_ij"], flows["Q_ij"]),
                   np.hypot(flows["P_ji"], flows["Q_ji"])).to_numpy(float) * base
    names = branch_names(lines)
    return [names[k] for k in range(len(rate)) if rate[k] > 0 and s[k] > rate[k] + 1e-9]


def contingency(bus, lines, vmin, vmax, base=100.0):
    """N-1: remove each in-service line, re-solve (Newton-Raphson), rank by
    severity (voltage violations, then overloads, then lowest voltage)."""
    rows = []
    names = branch_names(lines)
    on = lines["InService"].fillna(1).astype(float).to_numpy() != 0 \
        if "InService" in lines else np.ones(len(lines), bool)
    for k in range(len(lines)):
        if not on[k]:
            continue
        name = names[k]
        try:
            rest = lines.drop(lines.index[k]).reset_index(drop=True)
            r, fl, ok, _ = solve_loadflow(bus, rest)
            if not ok or not np.isfinite(r["V (pu)"]).all():
                raise ValueError("no convergence")
            v = r["V (pu)"]
            bad = r[(v < vmin) | (v > vmax)]["Bus"].tolist()
            over = overloads(fl, rest, base)
            rows.append([name, "OK", len(bad), round(v.min(), 4),
                         int(r.loc[v.idxmin(), "Bus"]), round(fl["Loss_P"].sum(), 4),
                         ", ".join(map(str, bad)) or "-", len(over), ", ".join(over) or "-"])
        except Exception:
            rows.append([name, "FAILED", None, None, None, None, "islanded/diverged", None, "-"])
    df = pd.DataFrame(rows, columns=["Outage", "Status", "Violations", "Min V (pu)",
                                     "At bus", "Loss (pu)", "Buses violating",
                                     "Overloads", "Lines overloaded"])
    return df.sort_values(["Status", "Violations", "Overloads", "Min V (pu)"],
                          ascending=[True, False, False, True]).reset_index(drop=True)


def fault_analysis(bus, lines, res, xd, zf, base, kv):
    """3-phase fault at every bus via Zbus (loads neglected, generators = Xd'')."""
    n = len(bus)
    Y = build_ybus(n, lines)
    for i in np.where(bus["Type"].values != "PQ")[0]:
        Y[i, i] += 1 / (1j * xd)
    Z = np.linalg.inv(Y)
    V0 = res["V (pu)"].values * np.exp(1j * np.radians(res["Angle (deg)"].values))
    If = V0 / (np.diag(Z) + zf)
    ib = base / (np.sqrt(3) * kv)
    df = pd.DataFrame({"Bus": np.arange(1, n + 1), "Fault I (pu)": abs(If),
                       "Fault I (kA)": abs(If) * ib, "Fault MVA": abs(If) * base})
    return df, Z, V0, If


def outage(bus, lines, k):
    """Re-solve the case with line k removed (Newton-Raphson)."""
    return solve_loadflow(bus, lines.drop(lines.index[k]).reset_index(drop=True))


def pv_curve(bus, lines, step=0.1, lmax=6.0):
    """P-V curve: scale every load and generator by lambda until NR fails.

    The step halves on each failure (3 times), so the last converged lambda
    is a lower bound on the nose (maximum loadability) of the case.
    Returns (DataFrame with 'lambda' + one |V| column per bus, last lambda).
    """
    rows, lam, h = [], 0.0, step
    while h >= step / 8 and lam + h <= lmax:
        trial = round(lam + h, 6) if rows else 0.0
        b = bus.copy()
        b[["Pg", "Qg", "Pd", "Qd"]] = b[["Pg", "Qg", "Pd", "Qd"]] * trial
        try:
            r, _, ok, _ = solve_loadflow(b, lines)
            v = r["V (pu)"].to_numpy(dtype=float)
            ok = ok and np.isfinite(v).all() and v.min() > 0.3
        except Exception:
            ok = False
        if ok:
            rows.append([trial, *v])
            lam = trial
        elif not rows:
            break
        else:
            h /= 2
    cols = ["lambda"] + [f"Bus {i}" for i in range(1, len(bus) + 1)]
    return pd.DataFrame(rows, columns=cols), lam
