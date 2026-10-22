"""GridLens core: case validation and the full study, with no Streamlit.

prep_case  bus / line tables + settings -> cleaned tables, problems, notes
run_study  load flow + method comparison + N-1 + P-V curve -> results dict
outage     load flow with one line removed

app.py (Streamlit) and api/server.py (FastAPI) both call these; the maths
itself lives in solver.py, studies.py and qlimits.py.
"""
import numpy as np
import pandas as pd

import model
from solver import islands as _islands
from solver import solve_with_qlimits
from solver import METHODS, solve_loadflow
from studies import branch_names, contingency, pv_curve
from topics import case_to_pu
from working import TEACH_MAX
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
    notes = []
    if cfg.get("units", "pu") == "actual" and len(b):
        base = float(cfg.get("base", 100.0) or 0)
        if base <= 0:
            return b, l, ["System base MVA must be greater than 0."], []
        b, l, _, conv_probs, notes = case_to_pu(b, l, base)
        if conv_probs:
            return b, l, conv_probs, notes
    l = l.dropna(subset=["From", "To"]).reset_index(drop=True)
    b = b.dropna(subset=["Type"]).reset_index(drop=True)
    probs = []
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

    for c in ("V", "Pg", "Qg", "Pd", "Qd", "Bs", "Gs"):
        b[c] = _num(b, c, probs, 1.0 if c == "V" else 0.0)
    _labels(b, probs)
    if "kV" in b:
        kv = pd.to_numeric(b["kV"], errors="coerce")
        bad_kv = [i + 1 for i, v in enumerate(kv) if pd.notna(v) and v <= 0]
        if bad_kv:
            probs.append("Base kV must be greater than 0 (bus rows "
                         + ", ".join(map(str, bad_kv)) + ").")
    if float(cfg.get("base", 100.0) or 0) <= 0:
        probs.append("System base MVA must be greater than 0.")
    if cfg["qlim"]:
        b["Qmin"] = _num(b, "Qmin", probs, -9999.0)
        b["Qmax"] = _num(b, "Qmax", probs, 9999.0)

    for c in ("From", "To", "R", "X", "B", "Tap", "Shift", "Rate"):
        l[c] = _num_l(l, c, probs, 1.0 if c == "Tap" else 0.0)
    l["InService"] = [1.0 if _on(v) else 0.0 for v in l["InService"]] \
        if "InService" in l else 1.0
    off = int((l["InService"] == 0).sum())
    if off:
        notes.append(f"{off} branch(es) are out of service and carry no flow.")

    if not cfg["shunts"]:
        has = [c for c in ("Bs", "Gs") if c in bus_df and pd.to_numeric(
            bus_df[c], errors="coerce").fillna(0).abs().max() > 0]
        if has:
            notes.append("Bus shunts exist in the data but 'Shunt elements' "
                         f"is off; {' = '.join(has)} = 0 was used. Turn it on to include them.")
        b["Bs"] = 0.0
        b["Gs"] = 0.0
    if "Tap" in l and not cfg["taps"]:
        if "Tap" in lines_df and \
                pd.to_numeric(lines_df["Tap"],
                              errors="coerce").fillna(1).sub(1).abs().max() \
                > 1e-9:
            notes.append("Transformer taps exist in the data but "
                         "'Transformer taps' is off; Tap = 1 was used. Turn "
                         "it on to include them.")
        l["Tap"] = 1.0
    if not cfg["taps"]:
        if "Shift" in lines_df and pd.to_numeric(lines_df["Shift"], errors="coerce") \
                .fillna(0).abs().max() > 1e-9:
            notes.append("Phase shifts exist in the data but 'Transformer taps' "
                         "is off; shift = 0 was used. Turn it on to include them.")
        l["Shift"] = 0.0

    n = len(b)
    for c in ("From", "To"):
        frac = l[c].to_numpy(dtype=float)
        nonint = np.flatnonzero(np.abs(frac % 1) > 1e-9)
        if len(nonint):
            probs.append(f"Line {c} must be whole bus numbers (rows "
                         f"{', '.join(str(x + 1) for x in nonint)}).")
    l["From"] = l["From"].round().astype(int)
    l["To"] = l["To"].round().astype(int)

    islands = _islands(n, l)
    slacks = [i + 1 for i, t in enumerate(b["Type"]) if t == "Slack"]
    if not slacks:
        probs.append("No Slack bus: set exactly one bus Type to Slack.")
    elif len(islands) == 1 and len(slacks) > 1:
        probs.append("More than one Slack bus (buses " +
                     ", ".join(map(str, slacks)) + "); exactly one required.")
    for isl in islands if len(islands) > 1 else []:
        sl = [i + 1 for i in isl if b["Type"].iloc[i] == "Slack"]
        if len(sl) > 1:
            probs.append(f"Island with buses {_list(isl)} has more than one Slack bus "
                         f"({', '.join(map(str, sl))}); exactly one per island.")
    out_of_range = []
    for c in ("From", "To"):
        out_of_range.extend(
            (i + 1, int(v), c) for i, v in enumerate(l[c]) if not 1 <= v <= n)
    if out_of_range:
        probs.append("Lines reference buses that do not exist (buses run "
                     "from 1 to N in row order): " + "; ".join(
            f"row {r}: {c} = {v}" for r, v, c in sorted(out_of_range)))
    zero_z = [f"{int(l['From'][i])}-{int(l['To'][i])}" for i in range(len(l))
              if l["InService"][i] and l["R"][i] == 0 and l["X"][i] == 0]
    if zero_z:   # X < 0 (series capacitor) and X = 0 with R > 0 are fine
        probs.append("Series impedance must not be zero: R = X = 0 on lines " +
                     ", ".join(zero_z) + ". Give X a small value (such as 0.0001) or "
                     "join the two buses.")

    if slacks and len(islands) > 1:
        dead = [isl for isl in islands if not any(b["Type"].iloc[i] == "Slack" for i in isl)]
        for isl in dead:
            probs.append(f"Network is disconnected: buses {_list(isl)} have no path to a "
                         "Slack bus. Connect them, or make one of them the Slack bus "
                         "of its own island.")
        if not dead:
            notes.append(f"The network has {len(islands)} islands ("
                         + "; ".join(f"buses {_list(isl)}" for isl in islands)
                         + "); each is solved with its own Slack bus.")
    if not len(l):
        probs.append("There are no lines: add at least one line between two "
                     "buses.")
    return b, l, probs, notes


def _list(isl):
    return ", ".join(str(i + 1) for i in isl)


def _on(v):
    """In-service flag: blank, 1, true, yes, on = in service."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return True
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "no", "off", "out")
    return bool(v)


def _labels(b, probs):
    """Optional bus Num (the user's bus number, a label; lines refer to rows)
    and Name. Numbers must be whole and unique."""
    if "Num" not in b:
        return
    num = pd.to_numeric(b["Num"], errors="coerce")
    if num.isna().any() or (num % 1 != 0).any():
        probs.append("Bus numbers must be whole numbers.")
        return
    dup = sorted({int(v) for v in num[num.duplicated()]})
    if dup:
        probs.append("Duplicate bus numbers: " + ", ".join(map(str, dup)) + ".")


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


# ------------------------------------------------- robust main load flow
ATTEMPTS = [  # tried in order after the chosen method fails (fallback on)
    ("Newton-Raphson", "flat", 1.0), ("Newton-Raphson", "setpoint", 1.0),
    ("Newton-Raphson", "flat", 0.5), ("Fast Decoupled", "flat", 1.0),
    ("Gauss-Seidel", "flat", 1.0)]


def _try(b, l, method, tol, qlim, init, damp):
    kw = {} if (init, damp) == ("flat", 1.0) else dict(
        init=init, damp=damp, max_iter=100 if damp < 1 else None)
    try:
        if qlim:
            res, flows, ok, hist, b_lf, qlog = solve_with_qlimits(b, l, method, tol, **kw)
        else:
            (res, flows, ok, hist), b_lf, qlog = solve_loadflow(b, l, method, tol, **kw), b, []
        ok = bool(ok) and np.isfinite(res["V (pu)"]).all()
    except np.linalg.LinAlgError:
        return None
    return res, flows, ok, hist, b_lf, qlog


def loadflow(b, l, method, tol, qlim=False, init="flat", fallback=True):
    """The main load flow. The chosen method and start are tried first (so a
    case that converges gives exactly what solve_loadflow gives); if it does
    not converge and fallback is on, ATTEMPTS are tried in turn. Returns
    (res, flows, ok, hist, b_lf, qlog, attempts, hint); attempts lists every
    try, hint explains a failure in plain words."""
    plan = [(method, init, 1.0)] + ([a for a in ATTEMPTS if a != (method, init, 1.0)]
                                    if fallback else [])
    attempts, first = [], None
    for m, start, damp in plan:
        out = _try(b, l, m, tol, qlim, start, damp)
        attempts.append(dict(Method=m, Start=start + (", damped" if damp < 1 else ""),
                             Converged=bool(out and out[2]),
                             Iterations=len(out[3]) - 1 if out else None))
        first = first or out
        if out and out[2]:
            return (*out, attempts, "")
    if first is None:
        raise ValueError("the network equations are singular: " + _singular_hint(b, l))
    return (*first, attempts, failure_hint(b, l, first[0], first[4]))


def _singular_hint(b, l):
    return ("check for lines with zero or tiny impedance, buses with no "
            "connection and the Slack bus")


def failure_hint(b, l, res, b_lf):
    """Plain-language reason for a load flow that did not converge, from the
    bus with the largest power mismatch in the last iterate."""
    p = (b_lf["Pg"] - b_lf["Pd"]).astype(float).to_numpy()
    q = (b_lf["Qg"] - b_lf["Qd"]).astype(float).to_numpy()
    t = b_lf["Type"].to_numpy()
    dp = np.where(t != "Slack", np.abs(res["P_inj"].to_numpy(float) - p), 0)
    dq = np.where(t == "PQ", np.abs(res["Q_inj"].to_numpy(float) - q), 0)
    mis = np.nan_to_num(np.maximum(dp, dq), nan=np.inf)
    k = int(np.argmax(mis))
    v = res["V (pu)"].to_numpy(float)
    blew = not np.isfinite(mis[k]) or mis[k] > 1e3 or not np.isfinite(v).all()
    where = (f"The iterations blew up, worst near bus {k + 1}." if blew
             else f"Worst mismatch at bus {k + 1} ({mis[k]:.3g} pu).")
    big = np.abs(np.r_[p, q]).max(initial=0)
    if big > 20:
        return (f"{where} Some powers are above 20 pu: they look like MW / MVAr, not per "
                "unit. Divide by the base MVA, or set the case units to actual values.")
    half = b.copy()
    half[["Pg", "Qg", "Pd", "Qd"]] = half[["Pg", "Qg", "Pd", "Qd"]] * 0.5
    try:
        ok_half = solve_loadflow(half, l)[2]
    except Exception:
        ok_half = False
    if ok_half:
        return (f"{where} The case solves at half load, so the load is probably too "
                "high for this network (past the nose of the PV curve). Reduce the load, "
                "add generation or reactive support near that bus, or strengthen the lines.")
    if not blew and v[k] < 0.7:
        return (f"{where} The voltage there collapses ({v[k]:.2f} pu): check the line data "
                "to that bus (R and X in per unit) and the load at it.")
    return (f"{where} Check the data at that bus and its lines (signs of P and Q, per "
            "unit values), and that the Slack bus is a strong source.")


def line_loading(flows, l, base):
    """MVA through each branch (larger end) and % of its Rate (MVA, 0 = none)."""
    s = np.maximum(np.hypot(flows["P_ij"], flows["Q_ij"]),
                   np.hypot(flows["P_ji"], flows["Q_ji"])).to_numpy(float) * base
    rate = pd.to_numeric(l["Rate"], errors="coerce").fillna(0).to_numpy(float) \
        if "Rate" in l else np.zeros(len(l))
    pct = np.where(rate > 0, s / np.where(rate > 0, rate, 1) * 100, np.nan)
    return pd.DataFrame({"Branch": branch_names(l), "S (MVA)": s, "Rate (MVA)": rate,
                         "Loading (%)": pct})


def run_study(b, l, method, tol, base, vmin, vmax, qlim=False, init="flat",
              fallback=True):
    """Load flow plus every study (method comparison, N-1, P-V). With qlim
    the main load flow enforces generator Q limits (PV -> PQ). The main load
    flow falls back to other methods/starts when it does not converge."""
    res, flows, ok, hist, b_lf, qlog, attempts, hint = loadflow(
        b, l, method, tol, qlim, init, fallback)
    used = next((a for a in attempts if a["Converged"]), attempts[0])
    rows, notes = [], []
    for m in METHODS:
        if m == "Gauss-Seidel" and len(b) > TEACH_MAX:
            rows.append([m, None, None, None, None])
            notes.append(f"not run: a teaching method, used up to {TEACH_MAX} buses")
            continue
        try:
            r2, f2, ok2, h2 = solve_loadflow(b, l, m)
        except np.linalg.LinAlgError as e:   # e.g. Fast Decoupled with a line of X = 0
            rows.append([m, False, None, None, None])
            notes.append(str(e))
            continue
        rows.append([m, ok2, len(h2) - 1,
                     round(f2["Loss_P"].sum() * base, 4),
                     round(r2["V (pu)"].min(), 4)])
        notes.append("")
    cmp_df = pd.DataFrame(rows, columns=["Method", "Converged", "Iterations",
                                         "Loss (MW)", "Min V (pu)"])
    if any(notes):
        cmp_df["Note"] = notes
    n1 = contingency(b, l, vmin, vmax, base, qlim)
    loading = line_loading(flows, l, base)
    n1_text = n1 if (n1["Overloads"].fillna(0) > 0).any() else \
        n1.drop(columns=["Overloads", "Lines overloaded"])
    if not (n1["Status"] == "ISLANDED").any():
        n1_text = n1_text.drop(columns=["Lost load (MW)", "Buses cut off"])
    pv = pv_curve(b, l, qlim=qlim)
    loss = flows["Loss_P"].sum() * base
    load = b["Pd"].sum() * base
    k = int(np.where(b["Type"].values == "Slack")[0][0])
    return dict(res=res, flows=flows, ok=ok, its=len(hist) - 1, hist=hist,
                method=method, tol=tol, b=b, l=l, cmp=cmp_df,
                n1=n1, pv=pv, loss=loss, load=load, vmin=vmin, vmax=vmax, base=base,
                qlog=qlog, b_lf=b_lf, attempts=attempts, hint=hint,
                solved_with=f"{used['Method']} ({used['Start']} start)",
                loading=loading,
                slack_k=k + 1, slack_p=res["P_inj"].iloc[k] * base,
                summary=(f"Method: {method}, base {base} MVA\n"
                         + (f"({method} did not converge; solved with "
                            f"{used['Method']}, {used['Start']} start.)\n"
                            if len(attempts) > 1 and ok else "")
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
                         + n1_text.head(3).to_string(index=False)))


def solve_case(case, method="Newton-Raphson", tol=1e-8, qlim=False, init="flat",
               fallback=True):
    """Load flow on an element-model case (model.Case): its v1 tables are
    validated (prep_case; taps and shunts are data, always on) and solved by
    loadflow (fallback chain). Returns model.results (bus, branch, gen, load,
    shunt keyed by element ID) plus ok, iterations, hist, attempts, hint, notes
    and qlog; raises ValueError with the problems when the data cannot be solved."""
    probs = model.check_ids(case)
    if probs:
        raise ValueError(" ".join(probs))
    bus, lines = model.to_tables(case)
    b, l, probs, notes = prep_case(bus, lines, dict(base=case.base, qlim=qlim, taps=True,
                                                     shunts=True))
    if probs:
        raise ValueError(" ".join(probs))
    res, flows, ok, hist, b_lf, qlog, attempts, hint = loadflow(b, l, method, tol, qlim, init,
                                                                fallback)
    return dict(model.results(case, res, flows, b_lf), ok=ok, iterations=len(hist) - 1,
                hist=hist, attempts=attempts, hint=hint, notes=notes, qlog=qlog)


def outage(b, l, k, qlim=False):
    """Re-solve the case with line k removed: (res, flows, ok, hist, cut) as
    studies.outage (buses cut off from every Slack get V = 0 and no flow)."""
    return _outage(b, l, k, qlim)

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

# The IEEE 14-bus preset carries its one-line positions as ordinary bus
# columns x, y (diagram units, y down), hand-placed after the usual drawing:
# generators on top, the 6/9 transformer area in the middle, the 13.8 kV
# buses below. Any case may carry x, y; cases without them get the automatic
# layered layout. Nothing looks up a case by name.
CASES["IEEE 14-bus"][0]["x"] = [2.5, 9, 16.5, 13.5, 5, 1.5, 12.5, 7.2, 19, 20, 4, -5.5, -2, -1.5]
CASES["IEEE 14-bus"][0]["y"] = [0, 0, 0, 5, 5, 10, 10, 10, 10, 15, 15, 10, 15, 20]


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
