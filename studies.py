import numpy as np
import pandas as pd

from solver import build_ybus, islands, solve_loadflow, solve_with_qlimits


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


def contingency(bus, lines, vmin, vmax, base=100.0, qlim=False, progress=None):
    """N-1: remove each in-service line, re-solve (Newton-Raphson; generator Q
    limits when qlim), rank by severity: no solution (FAILED) first, then lost
    load, voltage violations, overloads and lowest voltage. An outage that
    cuts buses off from every Slack solves the rest (Status ISLANDED) and
    reports the load of the buses cut off as lost. progress(done, total) is
    called before the first outage and after each one (a background job uses
    it; whatever it raises stops the study)."""
    rows = []
    names = branch_names(lines)
    on = lines["InService"].fillna(1).astype(float).to_numpy() != 0 \
        if "InService" in lines else np.ones(len(lines), bool)
    pd_ = bus["Pd"].astype(float).to_numpy()
    tick, todo = progress or _quiet, int(on.sum())
    tick(0, todo)
    for k in range(len(lines)):
        if not on[k]:
            continue
        name = names[k]
        try:
            r, fl, ok, _, cut = outage(bus, lines, k, qlim)
            live = np.ones(len(bus), bool)
            live[cut] = False
            v = r["V (pu)"][live]
            if not ok or not np.isfinite(v).all():
                raise ValueError("no convergence")
            bad = r[live & ((r["V (pu)"] < vmin) | (r["V (pu)"] > vmax))]["Bus"].tolist()
            over = overloads(fl, lines.drop(lines.index[k]).reset_index(drop=True), base)
            rows.append([name, "ISLANDED" if len(cut) else "OK", len(bad), round(v.min(), 4),
                         int(r.loc[v.idxmin(), "Bus"]), round(fl["Loss_P"].sum(), 4),
                         ", ".join(map(str, bad)) or "-", len(over), ", ".join(over) or "-",
                         round(pd_[cut].sum() * base, 4),
                         ", ".join(str(i + 1) for i in cut) or "-"])
        except Exception:
            rows.append([name, "FAILED", None, None, None, None, "no solution (diverged)", None,
                         "-", None, "-"])
        tick(len(rows), todo)
    df = pd.DataFrame(rows, columns=["Outage", "Status", "Violations", "Min V (pu)", "At bus",
                                     "Loss (pu)", "Buses violating", "Overloads",
                                     "Lines overloaded", "Lost load (MW)", "Buses cut off"])
    solved = df["Status"] != "FAILED"
    return df.assign(_s=solved).sort_values(
        ["_s", "Lost load (MW)", "Violations", "Overloads", "Min V (pu)"],
        ascending=[True, False, False, False, True]).drop(columns="_s").reset_index(drop=True)


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


def outage(bus, lines, k, qlim=False):
    """Re-solve the case with line k removed (Newton-Raphson; Q limits when
    qlim): (res, flows, ok, hist, cut). Buses the outage cuts off from every
    Slack lose supply: they are left out of the solve and come back with
    V = 0 and no flow; cut lists their rows (0-based). flows has the other
    lines in their order."""
    rest = lines.drop(lines.index[k]).reset_index(drop=True)
    return solve_supplied(bus, rest, qlim)


def solve_supplied(bus, lines, qlim=False):
    """Load flow of the buses still joined to a Slack: (res, flows, ok, hist,
    cut) over the whole case (see outage)."""
    n = len(bus)
    slack = bus["Type"].to_numpy() == "Slack"
    cut = np.array(sorted(i for isl in islands(n, lines) if not slack[isl].any() for i in isl),
                   dtype=int)
    if not len(cut):
        return (*_solve(bus, lines, qlim), cut)
    keep = np.setdiff1d(np.arange(n), cut)
    row = np.full(n, -1)
    row[keep] = np.arange(len(keep))
    f, t = lines["From"].to_numpy(int) - 1, lines["To"].to_numpy(int) - 1
    inside = (row[f] >= 0) & (row[t] >= 0)
    r, fl, ok, hist = _solve(bus.iloc[keep].reset_index(drop=True),
                             lines[inside].assign(From=row[f[inside]] + 1, To=row[t[inside]] + 1)
                             .reset_index(drop=True), qlim)
    res = pd.DataFrame({"Bus": np.arange(1, n + 1), "V (pu)": 0.0, "Angle (deg)": 0.0,
                        "P_inj": 0.0, "Q_inj": 0.0})
    res.iloc[keep, 1:] = r.iloc[:, 1:].to_numpy()
    flows = pd.DataFrame({"From": f + 1, "To": t + 1, **{c: 0.0 for c in fl.columns[2:]}})
    flows.iloc[np.flatnonzero(inside), 2:] = fl.iloc[:, 2:].to_numpy()
    return res, flows, ok, hist, cut


def _quiet(*_):
    """The progress callback when nobody listens."""


def _solve(bus, lines, qlim=False):
    """Newton-Raphson, with generator Q limits (PV -> PQ) when qlim."""
    return solve_with_qlimits(bus, lines)[:4] if qlim else solve_loadflow(bus, lines)


def pv_curve(bus, lines, step=0.1, lmax=6.0, qlim=False, progress=None):
    """P-V curve: scale every load and generator by lambda until NR fails
    (with generator Q limits when qlim; the limits are not scaled).

    The step halves on each failure (3 times), so the last converged lambda
    is a lower bound on the nose (maximum loadability) of the case.
    Returns (DataFrame with 'lambda' + one |V| column per bus, last lambda).
    progress(points, None) is called after each load flow (the total is not
    known in advance), as in contingency.
    """
    rows, lam, h = [], 0.0, step
    tick = progress or _quiet
    while h >= step / 8 and lam + h <= lmax:
        trial = round(lam + h, 6) if rows else 0.0
        b = bus.copy()
        b[["Pg", "Qg", "Pd", "Qd"]] = b[["Pg", "Qg", "Pd", "Qd"]] * trial
        try:
            r, _, ok, _ = _solve(b, lines, qlim)
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
        tick(len(rows), None)
    cols =["lambda"] + [f"Bus {i}" for i in range(1, len(bus) + 1)]
    return pd.DataFrame(rows, columns=cols), lam
