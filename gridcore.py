"""GridLens core: case validation and the full study, with no Streamlit.

prep_case  bus / line tables + settings -> cleaned tables, problems, notes
run_study  load flow + method comparison + N-1 + P-V curve -> results dict
outage     load flow with one line removed

app.py (Streamlit) and api/server.py (FastAPI) both call these; the maths
itself lives in solver.py, studies.py and qlimits.py.
"""
import numpy as np
import pandas as pd

from solver import solve_with_qlimits
from solver import METHODS, solve_loadflow
from studies import contingency, pv_curve
from studies import outage as _outage


def prep_case(bus_df, lines_df, cfg):
    """Validate and clean the bus / line tables for the solver. Returns
    (bus, lines, problems, notes); problems non-empty = do not solve."""
    b = bus_df.copy()
    l = lines_df.copy()
    # an empty table (a drawing with no lines yet) has no columns at all
    for df, cols in ((b, ("Type",)), (l, ("From", "To"))):
        for c in cols:
            if c not in df:
                df[c] = pd.Series(dtype=object)
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
    if not len(l):
        probs.append("There are no lines: add at least one line between two "
                     "buses.")
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

# ============================================================================
# Preset cases
# ============================================================================

# ------------------------------------------------------------------ cases
def _bus(types, V, Pd, Qd, Pg=None, Bs=None):
    n = len(types)
    return pd.DataFrame({"Type": types, "V": V, "Pg": Pg or [0.0] * n, "Qg": [0.0] * n,
                         "Pd": Pd, "Qd": Qd, "Bs": Bs or [0.0] * n})


def _lines(rows):
    r = pd.DataFrame(rows, columns=["From", "To", "R", "X", "B", "Tap"])
    return r


CASES = {
    "5-bus (demo)": (
        _bus(["Slack", "PV", "PQ", "PQ", "PQ"], [1.06, 1.04, 1, 1, 1],
             [0, 0.2, 0.45, 0.4, 0.6], [0, 0.1, 0.15, 0.05, 0.1], Pg=[0, 0.4, 0, 0, 0]),
        _lines([[1, 2, .02, .06, .06, 1], [1, 3, .08, .24, .05, 1], [2, 3, .06, .18, .04, 1],
                [2, 4, .06, .18, .04, 1], [2, 5, .04, .12, .03, 1], [3, 4, .01, .03, .02, 1],
                [4, 5, .08, .24, .05, 1]])),
    "IEEE 14-bus": (
        _bus(["Slack", "PV", "PV", "PQ", "PQ", "PV", "PQ", "PV", "PQ", "PQ", "PQ", "PQ", "PQ", "PQ"],
             [1.06, 1.045, 1.01, 1, 1, 1.07, 1, 1.09, 1, 1, 1, 1, 1, 1],
             [0, .217, .942, .478, .076, .112, 0, 0, .295, .09, .035, .061, .135, .149],
             [0, .127, .19, -.039, .016, .075, 0, 0, .166, .058, .018, .016, .058, .05],
             Pg=[0, .4] + [0] * 12, Bs=[0] * 8 + [0.19] + [0] * 5),
        _lines([[1, 2, .01938, .05917, .0528, 1], [1, 5, .05403, .22304, .0492, 1],
                [2, 3, .04699, .19797, .0438, 1], [2, 4, .05811, .17632, .034, 1],
                [2, 5, .05695, .17388, .0346, 1], [3, 4, .06701, .17103, .0128, 1],
                [4, 5, .01335, .04211, 0, 1], [4, 7, 0, .20912, 0, .978],
                [4, 9, 0, .55618, 0, .969], [5, 6, 0, .25202, 0, .932],
                [6, 11, .09498, .1989, 0, 1], [6, 12, .12291, .25581, 0, 1],
                [6, 13, .06615, .13027, 0, 1], [7, 8, 0, .17615, 0, 1],
                [7, 9, 0, .11001, 0, 1], [9, 10, .03181, .0845, 0, 1],
                [9, 14, .12711, .27038, 0, 1], [10, 11, .08205, .19207, 0, 1],
                [12, 13, .22092, .19988, 0, 1], [13, 14, .17093, .34802, 0, 1]])),
}

# One-line diagram coordinates per preset (diagram units, y grows downward):
# hand-placed after the usual IEEE 14-bus drawing (generators on top, the
# 6/9 transformer area in the middle, the 13.8 kV buses below) so every
# branch is a straight drop or one elbow. Cases without an entry use the
# automatic layered layout.
COORDS = {
    "IEEE 14-bus": [(2.5, 0), (9, 0), (16.5, 0), (13.5, 5), (5, 5),
                    (1.5, 10), (12.5, 10), (7.2, 10), (19, 10), (20, 15),
                    (4, 15), (-5.5, 10), (-2, 15), (-1.5, 20)],
}


# ============================================================================
# Local model write-up (LM Studio)
# ============================================================================

LMSTUDIO_URL = "http://127.0.0.1:1234/v1"


# ------------------------------------------------------- local AI (Gemma)
def lm_models(url=LMSTUDIO_URL):
    import requests
    try:
        data = requests.get(f"{url}/models", timeout=3).json()["data"]
        return [m["id"] for m in data]
    except Exception:
        return []


def ai_report(summary, model, url=LMSTUDIO_URL):
    import requests
    prompt = ("You are a power systems engineer. Write a short plain-English "
              "load flow study summary: voltage problems, losses, and practical "
              "suggestions. Use ONLY the numbers given, do not invent any.\n\n"
              + summary)
    r = requests.post(f"{url}/chat/completions", timeout=300, json={
        "model": model, "temperature": 0.3, "max_tokens": 700,
        "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
