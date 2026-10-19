"""GridLens core: case validation and the full study, with no Streamlit.

prep_case  bus / line tables + settings -> cleaned tables, problems, notes
run_study  load flow + method comparison + N-1 + P-V curve -> results dict
outage     load flow with one line removed

app.py (Streamlit) and api/server.py (FastAPI) both call these; the maths
itself lives in solver.py, studies.py and qlimits.py.
"""
import numpy as np
import pandas as pd

from qlimits import solve_with_qlimits
from solver import METHODS, solve_loadflow
from studies import contingency, pv_curve
from studies import outage as _outage


def prep_case(bus_df, lines_df, cfg):
    """Validate and clean the bus / line tables for the solver. Returns
    (bus, lines, problems, notes); problems non-empty = do not solve."""
    b = bus_df.copy()
    l = lines_df.copy()
    l = l.dropna(subset=["From", "To"]).reset_index(drop=True)
    b = b.dropna(subset=["Type"]).reset_index(drop=True)
    probs, notes = [], []
    if len(l) < len(lines_df):
        notes.append("Line rows without From/To were ignored.")
    if len(b) < len(bus_df):
        notes.append("Bus rows without a Type were ignored.")
    if not len(b):
        probs.append("There are no buses: every row needs a Type.")
        return b, l, probs, notes
    bad = [i + 1 for i, t in enumerate(b["Type"].astype(str))
           if t not in ("Slack", "PV", "PQ")]
    if bad:
        probs.append("Bus Type must be Slack, PV or PQ (row(s) "
                     + ", ".join(map(str, bad)) + ").")

    for c in ("V", "Pg", "Qg", "Pd", "Qd", "Bs"):
        b[c] = _num(b, c, probs, 1.0 if c == "V" else 0.0)
    if cfg["qlim"]:
        b["Qmin"] = _num(b, "Qmin", probs, -9999.0)
        b["Qmax"] = _num(b, "Qmax", probs, 9999.0)

    for c in ("From", "To", "R", "X", "B", "Tap"):
        l[c] = _num_l(l, c, probs, 1.0 if c == "Tap" else 0.0)

    if not cfg["shunts"]:
        if "Bs" in bus_df and \
                pd.to_numeric(bus_df["Bs"],
                              errors="coerce").fillna(0).abs().max() > 0:
            notes.append("Bus shunts exist in the data but 'Shunt elements' "
                         "is off; Bs = 0 was used. Turn it on to include them.")
        b["Bs"] = 0.0
    if "Tap" in l and not cfg["taps"]:
        if "Tap" in lines_df and \
                pd.to_numeric(lines_df["Tap"],
                              errors="coerce").fillna(1).sub(1).abs().max() \
                > 1e-9:
            notes.append("Transformer taps exist in the data but "
                         "'Transformer taps' is off; Tap = 1 was used. Turn "
                         "it on to include them.")
        l["Tap"] = 1.0

    n = len(b)
    for c in ("From", "To"):
        frac = l[c].to_numpy(dtype=float)
        nonint = np.flatnonzero(np.abs(frac % 1) > 1e-9)
        if len(nonint):
            probs.append(f"Line {c} must be whole bus numbers (rows "
                         f"{', '.join(str(x + 1) for x in nonint)}).")
    l["From"] = l["From"].round().astype(int)
    l["To"] = l["To"].round().astype(int)

    slacks = [i + 1 for i, t in enumerate(b["Type"]) if t == "Slack"]
    if not slacks:
        probs.append("No Slack bus: set exactly one bus Type to Slack.")
    elif len(slacks) > 1:
        probs.append("More than one Slack bus (buses " +
                     ", ".join(map(str, slacks)) + "); exactly one required.")
    out_of_range = []
    for c in ("From", "To"):
        out_of_range.extend(
            (i + 1, int(v), c) for i, v in enumerate(l[c]) if not 1 <= v <= n)
    if out_of_range:
        probs.append("Lines reference buses that do not exist (buses run "
                     "from 1 to N in row order): " + "; ".join(
            f"row {r}: {c} = {v}" for r, v, c in sorted(out_of_range)))
    zero_x = [f"{int(l['From'][i])}-{int(l['To'][i])}" for i in range(len(l))
              if l["X"][i] <= 0]
    if zero_x:
        probs.append("Series reactance X must be greater than 0 (lines " +
                     ", ".join(zero_x) + ").")

    adj = [[] for _ in range(n)]
    for f, t in zip(l["From"].to_numpy(dtype=int), l["To"].to_numpy(dtype=int)):
        if 1 <= f <= n and 1 <= t <= n:
            adj[f - 1].append(t - 1)
            adj[t - 1].append(f - 1)
    seen, todo = {0}, [0]
    while todo:
        for nb in adj[todo.pop()]:
            if nb not in seen:
                seen.add(nb)
                todo.append(nb)
    if n > 1 and len(seen) < n:
        lost = ", ".join(str(x + 1) for x in sorted(set(range(n)) - seen))
        probs.append(f"Network is disconnected: bus 1 cannot reach buses {lost}.")
    return b, l, probs, notes


def _num(df, col, probs, fill):
    if col not in df:
        return pd.Series(fill, index=df.index)
    raw = df[col]
    v = pd.to_numeric(raw, errors="coerce")
    for pos in np.flatnonzero(v.isna().to_numpy() & raw.notna().to_numpy()):
        probs.append(f"Bus row {pos + 1}: column {col} is not a number.")
    return v.fillna(fill)


def _num_l(df, col, probs, fill):
    if col not in df:
        return pd.Series(fill, index=df.index)
    raw = df[col]
    v = pd.to_numeric(raw, errors="coerce")
    for pos in np.flatnonzero(v.isna().to_numpy() & raw.notna().to_numpy()):
        probs.append(f"Line row {pos + 1}: column {col} is not a number.")
    return v.fillna(fill)


def run_study(b, l, method, tol, base, vmin, vmax, qlim=False):
    """Load flow plus every study (method comparison, N-1, P-V). With qlim
    the main load flow enforces generator Q limits (PV -> PQ)."""
    qlog, b_lf = [], b
    if qlim:
        res, flows, ok, hist, b_lf, qlog = solve_with_qlimits(b, l, method, tol)
    else:
        res, flows, ok, hist = solve_loadflow(b, l, method, tol)
    rows = []
    for m in METHODS:
        r2, f2, ok2, h2 = solve_loadflow(b, l, m)
        rows.append([m, ok2, len(h2) - 1,
                     round(f2["Loss_P"].sum() * base, 4),
                     round(r2["V (pu)"].min(), 4)])
    cmp_df = pd.DataFrame(rows, columns=["Method", "Converged", "Iterations",
                                         "Loss (MW)", "Min V (pu)"])
    n1 = contingency(b, l, vmin, vmax)
    pv = pv_curve(b, l)
    loss = flows["Loss_P"].sum() * base
    load = b["Pd"].sum() * base
    k = int(np.where(b["Type"].values == "Slack")[0][0])
    return dict(res=res, flows=flows, ok=ok, its=len(hist) - 1, hist=hist,
                method=method, tol=tol, b=b, l=l, cmp=cmp_df,
                n1=n1, pv=pv, loss=loss, load=load, vmin=vmin, vmax=vmax, base=base,
                qlog=qlog, b_lf=b_lf,
                slack_k=k + 1, slack_p=res["P_inj"].iloc[k] * base,
                summary=(f"Method: {method}, base {base} MVA\n"
                         + res.round(4).to_string(index=False)
                         + f"\nTotal load: {load:.2f} MW. "
                         + f"Total real loss: {loss:.2f} MW"
                         + (f" ({loss / load * 100:.1f}% of load)." if load
                            else ".")
                         + f" Voltage limits: {vmin}-{vmax} pu."
                         + (f"\nVoltage stability: loads can grow to "
                            f"{pv[1]:.2f}x the base case before the load flow "
                            f"stops solving.")
                         + "\nWorst N-1 line outages (worst first):\n"
                         + n1.head(3).to_string(index=False)))


def outage(b, l, k):
    """Re-solve the case with line k removed: (res, flows, ok, hist)."""
    return _outage(b, l, k)
