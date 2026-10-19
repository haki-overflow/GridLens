"""GridLens: N-bus power system analysis GUI (load flow, N-1, faults).

Run:    streamlit run app.py
AI:     LM Studio -> Developer tab -> load Gemma -> Start Server (port 1234)

The solver does all the math; a local Gemma model only explains the results.
Quantities are per unit unless a tooltip says otherwise.
"""
import numpy as np
import pandas as pd
import streamlit as st

import ui_problem
import ui_theme
from ai_report import ai_report, lm_models
import oneline
from cases import CASES, COORDS
from plotting import (convergence_history, fault_voltages,
                      pv_curves, voltage_profile)
from qlimits import solve_with_qlimits
from solver import METHODS, solve_loadflow
from studies import contingency, fault_analysis, outage, pv_curve

BUS_COLS = ["Type", "V", "Pg", "Qg", "Pd", "Qd", "Bs"]
LINE_COLS = ["From", "To", "R", "X", "B", "Tap"]
TEMPLATES = {
    "blank_bus.csv": ("Type,V,Pg,Qg,Pd,Qd,Bs\n"
                      "Slack,1.06,0,0,0,0,0\nPV,1.04,0.4,0,0.2,0.1,0\n"
                      "PQ,1,0,0,0.45,0.15,0\n"),
    "blank_lines.csv": ("From,To,R,X,B,Tap\n"
                        "1,2,0.02,0.06,0.06,1\n1,3,0.08,0.24,0.05,1\n"
                        "2,3,0.06,0.18,0.04,1\n"),
}
DEFAULTS = dict(method="Newton-Raphson", base=100.0, vmin=0.95, vmax=1.10,
                tol=1e-8, taps=False, shunts=False, qlim=False)
EXTRA_BUS_COLS = ("Qmin", "Qmax", "kV", "x", "y")   # optional, kept if present


def _bump(which):
    st.session_state[f"{which}_v"] += 1


def _set_base(base):
    """Base MVA lives in `_base`; the sidebar widget is rebuilt from it."""
    st.session_state["_base"] = float(base)
    st.session_state.pop("base", None)


def _pick_case():
    bus, lines = CASES[st.session_state["case"]]
    st.session_state["bus_tbl"] = bus.copy()
    st.session_state["lines_tbl"] = lines.copy()
    st.session_state["case_src"] = None
    _set_base(DEFAULTS["base"])
    st.session_state["problems"] = None
    st.session_state["notes"] = None
    _bump("bus")
    _bump("lines")


def _pick_uploads():
    errors, replaced = [], []
    for which, required in (("bus", BUS_COLS[:-1]), ("lines", LINE_COLS[:-1])):
        f = st.session_state.get(f"up_{which}")
        if not f:
            continue
        try:
            df = pd.read_csv(f)
        except Exception as e:
            errors.append(f"{which} CSV could not be read: {e}")
            continue
        missing = [c for c in required if c not in df.columns]
        if missing:
            errors.append(f"{which} CSV is missing columns: {', '.join(missing)}")
            continue
        df = df.copy()
        if which == "bus" and "Bs" not in df.columns:
            df["Bs"] = 0.0
        if which == "lines" and "Tap" not in df.columns:
            df["Tap"] = 1.0
        cols = LINE_COLS if which == "lines" else BUS_COLS + [
            c for c in EXTRA_BUS_COLS if c in df.columns]
        st.session_state[f"{which}_tbl"] = df[cols].copy()
        _bump(which)
        replaced.append(which)
    if errors:
        st.session_state["upload_errs"] = errors
    else:
        st.session_state.pop("upload_errs", None)
    if replaced:
        st.session_state["problems"] = None
        st.session_state["notes"] = None
        st.session_state["case_src"] = None


@st.cache_resource
def _shared():
    """Server-wide store: last solved study and its report, so a page opened
    in a new browser tab (a new session) shows the results without a re-run."""
    return {}


def _init():
    if "bus_tbl" not in st.session_state:
        last = _shared().get("last")
        if last:
            st.session_state["bus_tbl"] = last["bus"].copy()
            st.session_state["lines_tbl"] = last["lines"].copy()
            st.session_state["case_label"] = last["label"]
            if last["label"] in CASES:
                st.session_state["case"] = last["label"]
            st.session_state["out"] = _study(*last["args"])
            st.session_state["run_sig"] = last["sig"]
            rep_ = _shared().get("report")
            if rep_ and rep_[0] == st.session_state["out"]["summary"]:
                st.session_state["report"] = rep_[1]
        else:
            name = next(iter(CASES))
            st.session_state["bus_tbl"] = CASES[name][0].copy()
            st.session_state["lines_tbl"] = CASES[name][1].copy()
    st.session_state.setdefault("bus_v", 0)
    st.session_state.setdefault("lines_v", 0)
    st.session_state.setdefault("problems", None)
    st.session_state.setdefault("notes", None)
    st.session_state.setdefault("sc", None)
    st.session_state.setdefault("_base", DEFAULTS["base"])


def _cfg():
    mode = st.session_state.get("mode", "Quick")
    std = mode in ("Standard", "Advanced")
    adv = mode == "Advanced"
    cfg = dict(DEFAULTS)
    cfg.update(base=st.session_state.get("_base", DEFAULTS["base"]))
    if std:
        cfg.update(method=st.session_state.get("method", DEFAULTS["method"]),
                   vmin=st.session_state.get("vmin", DEFAULTS["vmin"]),
                   vmax=st.session_state.get("vmax", DEFAULTS["vmax"]))
    if adv:
        cfg.update(tol=st.session_state.get("tol", DEFAULTS["tol"]),
                   taps=st.session_state.get("taps", False),
                   shunts=st.session_state.get("shunts", False),
                   qlim=st.session_state.get("qlim", False))
    cfg.update(mode=mode)
    return cfg


def _sidebar():
    with st.sidebar:
        st.header("Mode")
        mode = st.segmented_control(
            "Mode", ["Quick", "Standard", "Advanced"], key="mode",
            default="Quick", wrap=False,
            help="Quick: preset or CSV + Solve, everything else default. "
                 "Standard adds method and limits. Advanced adds taps, "
                 "shunts and solver tolerance.")
        std = mode in ("Standard", "Advanced")
        adv = mode == "Advanced"

        st.header("Case data")
        src = st.segmented_control("Load grid data", ["Preset", "Upload CSV"],
                                   key="source", default="Preset")
        if src == "Upload CSV":
            st.file_uploader("Bus CSV", type="csv", key="up_bus",
                             on_change=_pick_uploads,
                             help="Columns Type (Slack/PV/PQ), V, Pg, Qg, Pd, "
                                  "Qd in per unit; optional Bs. Loads are "
                                  "positive. See templates below.")
            st.file_uploader("Line CSV", type="csv", key="up_lines",
                             on_change=_pick_uploads,
                             help="Columns From, To (1-based bus numbers), "
                                  "R, X, B in per unit; optional Tap "
                                  "(1 = no transformer). See templates.")
        else:
            st.selectbox("Preset case", list(CASES), key="case",
                         on_change=_pick_case,
                         help="Built-in demo and IEEE cases; switching "
                              "resets both tables to the preset.")
        with st.popover("CSV templates"):
            st.caption("Blank templates with every accepted column.")
            for name, body in TEMPLATES.items():
                st.download_button(name, data=body.encode(), file_name=name,
                                   mime="text/csv", key=f"tpl_{name}")

        if std:
            st.header("Solver")
            st.selectbox(
                "Method", METHODS, key="method",
                help="Newton-Raphson: quadratic, most robust. Fast "
                     "Decoupled: XB approximation, quadratic-ish. "
                     "Gauss-Seidel: linear convergence.")
            cl, cr = st.columns(2)
            cl.number_input("Vmin (pu)", 0.5, 1.5, 0.95, step=0.01,
                            key="vmin",
                            help="Lower voltage limit for violation "
                                 "tracking (per unit).")
            cr.number_input("Vmax (pu)", 0.5, 1.5, 1.10, step=0.01,
                            key="vmax",
                            help="Upper voltage limit for violation "
                                 "tracking (per unit).")
            st.number_input("Base MVA", 1.0, 10000.0,
                            float(st.session_state["_base"]), step=1.0,
                            key="base", on_change=lambda: st.session_state.update(
                                _base=st.session_state["base"]),
                            help="System base power; per-unit results "
                                 "convert to MW/MVAr with this.")
        if adv:
            st.toggle("Transformer taps", key="taps",
                      help="Show the line Tap column (off-nominal ratio, "
                           "1 = none). When off, Tap = 1 is used.")
            st.toggle("Shunt elements", key="shunts",
                      help="Show the bus Bs column (shunt susceptance). "
                           "When off, Bs = 0 is used.")
            st.toggle("Generator Q limits", key="qlim",
                      help="Show bus Qmin/Qmax (pu generation limits). A PV "
                           "bus that needs more Q than its limit becomes PQ "
                           "at the limit. Off: no limits (results as before).")
            st.number_input("Solver tolerance", 1e-12, 1e-3, DEFAULTS["tol"],
                            format="%g",
                            key="tol",
                            help="Power-mismatch convergence threshold "
                                 "(per unit). Note: Gauss-Seidel uses its "
                                 "own default tolerance.")
    return _cfg()


def _edit_table(where, df, hide, key, **kw):
    """data_editor over df without the `hide` columns; the hidden columns are
    put back afterwards (row-aligned) so turning a toggle off loses no data."""
    hide = [c for c in hide if c in df]
    edited = where.data_editor(df.drop(columns=hide), key=key, **kw)
    for c in hide:
        vals = list(df[c])[:len(edited)]
        edited[c] = vals + [np.nan] * (len(edited) - len(vals))
    return edited[[c for c in df.columns if c in edited] +
                  [c for c in edited.columns if c not in df.columns]]


def _editors(cfg):
    if st.session_state.get("last_shunts") != bool(cfg["shunts"]):
        st.session_state["last_shunts"] = bool(cfg["shunts"])
        _bump("bus")
    if st.session_state.get("last_qlim") != bool(cfg["qlim"]):
        st.session_state["last_qlim"] = bool(cfg["qlim"])
        _bump("bus")
    if st.session_state.get("last_taps") != bool(cfg["taps"]):
        st.session_state["last_taps"] = bool(cfg["taps"])
        _bump("lines")
    nb, nl = len(st.session_state["bus_tbl"]), len(st.session_state["lines_tbl"])
    box = st.expander(f"Case data · {nb} buses, {nl} lines",
                      expanded="out" not in st.session_state)
    left, right = box.columns([1.15, 1], gap="medium")
    left.html(ui_theme.section("Bus data"))
    left.caption("Per unit. Row n is bus n. Pd/Qd are positive demand, "
                 "Pg/Qg injections; V is the setpoint (Slack/PV) or start."
                 + (" Qmin/Qmax: generator Q limits." if cfg["qlim"] else ""))
    bus_tbl = st.session_state["bus_tbl"]
    if cfg["qlim"]:
        for c, v in (("Qmin", -9999.0), ("Qmax", 9999.0)):
            if c not in bus_tbl:
                bus_tbl = bus_tbl.assign(**{c: v})
    hide = ([] if cfg["shunts"] else ["Bs"]) + \
        ([] if cfg["qlim"] else ["Qmin", "Qmax"])
    st.session_state["bus_tbl"] = _edit_table(
        left, bus_tbl, hide, f"bus_ed_{st.session_state['bus_v']}",
        num_rows="dynamic", hide_index=True,
        column_config={"Type": st.column_config.SelectboxColumn(
            "Type", options=["Slack", "PV", "PQ"],
            help="Slack: swing bus. PV: held |V|. PQ: load bus.")})

    right.html(ui_theme.section("Branch data"))
    right.caption("From/To are bus numbers. B is total line-charging "
                  "susceptance, split B/2 at each end.")
    st.session_state["lines_tbl"] = _edit_table(
        right, st.session_state["lines_tbl"], [] if cfg["taps"] else ["Tap"],
        f"lines_ed_{st.session_state['lines_v']}",
        num_rows="dynamic", hide_index=True,
        column_config={
            "From": st.column_config.NumberColumn("From", step=1),
            "To": st.column_config.NumberColumn("To", step=1)})


def _prep(cfg):
    b = st.session_state["bus_tbl"].copy()
    l = st.session_state["lines_tbl"].copy()
    l = l.dropna(subset=["From", "To"]).reset_index(drop=True)
    b = b.dropna(subset=["Type"]).reset_index(drop=True)
    probs, notes = [], []
    if len(l) < len(st.session_state["lines_tbl"]):
        notes.append("Line rows without From/To were ignored.")
    if len(b) < len(st.session_state["bus_tbl"]):
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
        if "Bs" in st.session_state["bus_tbl"] and \
                pd.to_numeric(st.session_state["bus_tbl"]["Bs"],
                              errors="coerce").fillna(0).abs().max() > 0:
            notes.append("Bus shunts exist in the data but 'Shunt elements' "
                         "is off; Bs = 0 was used. Turn it on to include them.")
        b["Bs"] = 0.0
    if "Tap" in l and not cfg["taps"]:
        if "Tap" in st.session_state["lines_tbl"] and \
                pd.to_numeric(st.session_state["lines_tbl"]["Tap"],
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


@st.cache_data(show_spinner="Running studies...", max_entries=32)
def _study(b, l, method, tol, base, vmin, vmax, qlim=False):
    """Load flow plus every study, cached on the case and settings so any
    page or browser tab gets the same results without re-solving. With
    qlim the main load flow enforces generator Q limits (PV -> PQ)."""
    qlog = []
    if qlim:
        res, flows, ok, hist, _, qlog = solve_with_qlimits(b, l, method, tol)
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
                qlog=qlog,
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


@st.cache_data(show_spinner=False, max_entries=64)
def _outage(b, l, k):
    return outage(b, l, k)


@st.cache_data(show_spinner=False, max_entries=32)
def _faults(b, l, res, xd, zf, base, kv):
    return fault_analysis(b, l, res, xd, zf, base, kv)


def _inputs_sig(cfg):
    """Fingerprint of the inputs a run depends on (tables + settings)."""
    h = [int(pd.util.hash_pandas_object(st.session_state[k]).sum())
         for k in ("bus_tbl", "lines_tbl")]
    return tuple(h) + tuple(cfg[k] for k in ("method", "tol", "base", "vmin",
                                              "vmax", "taps", "shunts", "qlim"))


def _case_label():
    if st.session_state.get("case_src") == "problem":
        return "Problem input"
    if st.session_state.get("source", "Preset") != "Preset":
        return "User CSV"
    return st.session_state.get("case", next(iter(CASES)))


def _solve(cfg):
    b, l, probs, notes = _prep(cfg)
    if probs:
        st.session_state["problems"] = probs
        st.session_state["notes"] = None
        st.session_state.pop("out", None)
        return
    st.session_state["problems"] = None
    st.session_state["notes"] = notes
    args = (b, l, cfg["method"], cfg["tol"], cfg["base"], cfg["vmin"],
            cfg["vmax"], cfg["qlim"])
    try:
        out = _study(*args)
    except Exception as e:
        st.session_state["problems"] = [f"Solver failed: {e}"]
        st.session_state["notes"] = None
        st.session_state.pop("out", None)
        return
    st.session_state["sc"] = None
    st.session_state.pop("report", None)
    st.session_state.pop("net_sel", None)
    st.session_state["out"] = out
    st.session_state["case_label"] = _case_label()
    st.session_state["run_sig"] = _inputs_sig(cfg)
    _shared()["last"] = dict(sig=st.session_state["run_sig"],
        bus=st.session_state["bus_tbl"].copy(),
        lines=st.session_state["lines_tbl"].copy(),
        label=st.session_state["case_label"], args=args)


def _card(col, idx, tone, label, value, delta=None):
    with col:
        with st.container(key=f"kpi-{tone}-{idx}"):
            st.metric(label, value, delta, delta_color="off", delta_arrow="off",
                      border=False)


def _strip(out):
    better = "ok" if out["ok"] else "bad"
    row = st.container(horizontal=True, vertical_alignment="center")
    with row:
        st.markdown(ui_theme.badge("Converged" if out["ok"] else "Diverged",
                                   better), unsafe_allow_html=True)
        n1 = out["n1"]
        viol = pd.to_numeric(n1["Violations"], errors="coerce").fillna(0)
        bad = int((n1["Status"].eq("FAILED") | (viol > 0)).sum())
        st.markdown(ui_theme.badge("N-1 secure" if not bad else
                                   f"N-1: {bad} of {len(n1)} outages "
                                   "insecure", "bad" if bad else "ok"),
                    unsafe_allow_html=True)
        lam = out["pv"][1]
        tone = "ok" if lam >= 1.5 else "warn" if lam >= 1.15 else "bad"
        st.markdown(ui_theme.badge(f"Loadability {lam:.2f}x", tone),
                    unsafe_allow_html=True)
        if not out["cmp"]["Converged"].all():
            st.markdown(ui_theme.badge("Method mismatch", "warn"),
                        unsafe_allow_html=True)
        st.caption(f"{out['method']} · {out['its']} iterations · "
                   f"tol {out['tol']:g} · base {out['base']:g} MVA")
    cols = st.columns(6)
    vmin_ok = out["res"]["V (pu)"].min() >= out["vmin"]
    vmax_ok = out["res"]["V (pu)"].max() <= out["vmax"]
    loss = out["loss"]
    loss_pct = (loss / out["load"] * 100) if out["load"] else None
    _card(cols[0], 0, "plain", f"Slack P · bus {out['slack_k']}",
          f"{out['slack_p']:.1f} MW")
    _card(cols[1], 1, "plain", "Total generation",
          f"{out['load'] + out['loss']:.1f} MW")
    _card(cols[2], 2, "plain", "Total load", f"{out['load']:.1f} MW")
    _card(cols[3], 3, "plain", "Losses", f"{loss:.1f} MW",
          delta=f"{loss_pct:.1f}% of load" if loss_pct is not None else None)
    _card(cols[4], 4, "ok" if vmin_ok else "bad", "Min |V| · bus "
          f"{int(out['res'].loc[out['res']['V (pu)'].idxmin(), 'Bus'])}",
          f"{out['res']['V (pu)'].min():.3f} pu")
    _card(cols[5], 5, "ok" if vmax_ok else "bad", "Max |V| · bus "
          f"{int(out['res'].loc[out['res']['V (pu)'].idxmax(), 'Bus'])}",
          f"{out['res']['V (pu)'].max():.3f} pu")


def _plot(fig, alt, where=st):
    import matplotlib.pyplot as plt
    where.pyplot(fig, alt=alt, width="stretch")
    plt.close(fig)


def _tab_loadflow(out):
    b, res, base = out["b"], out["res"], out["base"]
    rep = pd.DataFrame({
        "Bus": res["Bus"], "Type": b["Type"].values,
        "V (pu)": res["V (pu)"], "Angle (deg)": res["Angle (deg)"],
        "P gen (MW)": (res["P_inj"] + b["Pd"].values) * base,
        "Q gen (MVAr)": (res["Q_inj"] + b["Qd"].values) * base,
        "P load (MW)": b["Pd"].values * base,
        "Q load (MVAr)": b["Qd"].values * base})
    gen = rep["Type"].ne("PQ")
    rep.loc[~gen, ["P gen (MW)", "Q gen (MVAr)"]] = 0.0
    rep["Status"] = np.where(rep["V (pu)"] < out["vmin"], "LOW V",
                             np.where(rep["V (pu)"] > out["vmax"], "HIGH V",
                                      "ok"))
    left, right = st.columns([1.35, 1], gap="large")
    left.html(ui_theme.section("Bus report"))
    left.dataframe(rep.round({"V (pu)": 4, "Angle (deg)": 2, "P gen (MW)": 1,
                              "Q gen (MVAr)": 1, "P load (MW)": 1,
                              "Q load (MVAr)": 1}), hide_index=True)
    right.html(ui_theme.section("Voltage profile"))
    _plot(voltage_profile(res, out["vmin"], out["vmax"]),
          "Bus voltage profile", right)
    fl = out["flows"]
    br = pd.DataFrame({
        "From": fl["From"], "To": fl["To"],
        "P from (MW)": fl["P_ij"] * base, "Q from (MVAr)": fl["Q_ij"] * base,
        "P to (MW)": fl["P_ji"] * base, "Q to (MVAr)": fl["Q_ji"] * base,
        "Loss (MW)": fl["Loss_P"] * base, "Loss (MVAr)": fl["Loss_Q"] * base})
    left, right = st.columns([1.35, 1], gap="large")
    left.html(ui_theme.section("Branch report"))
    left.dataframe(br.round(2), hide_index=True)
    right.html(ui_theme.section(f"Mismatch convergence · {out['method']}"))
    _plot(convergence_history(out["hist"]),
          f"Mismatch error per iteration, {out['method']}", right)


LAYERS = (("Flows (MW)", "flows", False), ("Angles", "angles", False),
          ("Loads", "loads", True), ("Generators", "gens", True),
          ("Breakers", "breakers", False))
CHART_CFG = {"scrollZoom": True, "displaylogo": False,
             "modeBarButtons": [["zoom2d", "pan2d", "resetScale2d"]]}


def _diagram(out, key, height, tripped=None, flows=None, res=None,
             show=None, selected=None, on_select="ignore"):
    """Plotly one-line diagram of the solved case (or an outage case)."""
    label = st.session_state.get("case_label")
    fig = oneline.figure(res if res is not None else out["res"], out["l"],
                         out["vmin"], out["vmax"],
                         out["flows"] if flows is None else flows,
                         base=out["base"], bus=out["b"],
                         coords=COORDS.get(label), show=show, tripped=tripped,
                         selected=selected, height=height)
    return st.plotly_chart(fig, key=key, theme=None, config=CHART_CFG,
                           on_select=on_select, selection_mode="points")


def _tab_network(out):
    with st.container(horizontal=True, vertical_alignment="center"):
        show = {k for name, k, on in LAYERS
                if st.checkbox(name, value=on, key=f"layer_{k}")}
        st.caption("Wheel = zoom, drag = pan, double-click = reset. Hover a "
                   "bus or line for its values; click to inspect it.")
    sel = st.session_state.get("net_sel")
    left, right = st.columns([4, 1], gap="small")
    with left:
        ev = _diagram(out, "net_chart", 760, show=show, selected=sel,
                      on_select="rerun")
    pts = (ev or {}).get("selection", {}).get("points", []) if ev else []
    if pts and pts[0].get("customdata"):
        kind, j = pts[0]["customdata"]
        if (kind, j) != sel:
            st.session_state["net_sel"] = (kind, int(j))
            st.rerun()
    with right:
        if sel is None:
            st.html(ui_theme.inspector_html("Inspector", [
                ("Selection", "none"), ("", "click a bus or line")]))
        else:
            title, rows = oneline.inspect(out["res"], out["l"], out["flows"],
                                          out["base"], out["b"], sel)
            st.html(ui_theme.inspector_html(title, rows))
            if st.button("Clear selection", key="net_clear"):
                st.session_state.pop("net_sel", None)
                st.rerun()


def _tab_cmp(out):
    st.caption("Same case through all three methods. Gauss-Seidel uses its "
               "own default tolerance.")
    st.dataframe(out["cmp"], hide_index=True, column_config={
        "Converged": st.column_config.CheckboxColumn("Converged")})


def _tab_n1(out):
    st.caption("Each line removed in turn, case re-solved (Newton-Raphson), "
               "ranked worst first.")
    st.html(ui_theme.section("Contingency ranking"))
    st.dataframe(out["n1"], hide_index=True)
    rows = []
    l = out["l"]
    for _, c in out["n1"].iterrows():
        if c["Status"] != "OK" or not c["Violations"]:
            if c["Status"] != "OK":
                rows.append([c["Outage"], "-", None, "-", "Islanding / no "
                             "solution"])
            continue
        k = [f"{int(f)}-{int(t)}" for f, t in
             zip(l["From"], l["To"])].index(c["Outage"])
        r, _, _, _ = _outage(out["b"], l, k)
        for bb in str(c["Buses violating"]).split(", "):
            vv = float(r.loc[int(bb) - 1, "V (pu)"])
            lim = out["vmin"] if vv < out["vmin"] else out["vmax"]
            rows.append([c["Outage"], f"Bus {bb}", round(vv, 4),
                         f"{lim:.2f}", "Low voltage" if vv < lim else
                         "High voltage"])
    st.html(ui_theme.section("Limit violation report"))
    if rows:
        st.dataframe(pd.DataFrame(rows, columns=[
            "Contingency", "Monitored element", "Value (pu)", "Limit (pu)",
            "Violation"]), hide_index=True)
    else:
        st.caption("No post-contingency limit violations.")
    st.html(ui_theme.section("Contingency explorer"))
    l = out["l"]
    names = [f"{int(f)}-{int(t)}" for f, t in zip(l["From"], l["To"])]
    k = st.selectbox("Trip line", range(len(l)), format_func=lambda i: names[i],
                     index=names.index(next(
                         (o for o, s in zip(out["n1"]["Outage"],
                                            out["n1"]["Status"]) if s == "OK"),
                         names[0])),
                     help="Defaults to the worst outage. The diagram and "
                          "table show the case with this line out.")
    try:
        r, fl, ok, _ = _outage(out["b"], l, k)
        ok = ok and np.isfinite(r["V (pu)"]).all()
    except Exception:
        ok = False
    if not ok:
        st.error(f"With line {names[k]} out the case does not solve "
                 "(islanded or diverged).")
        return
    left, right = st.columns([1.3, 1], gap="large")
    with left:
        _diagram(out, f"n1_chart_{k}", 400, tripped=k, flows=fl, res=r)
    keep = [i for i in range(len(l)) if i != k]
    pre = out["flows"].iloc[keep].reset_index(drop=True)
    d = pd.DataFrame({"Line": [names[i] for i in keep],
                      "Before (MW)": pre["P_ij"] * out["base"],
                      "After (MW)": fl["P_ij"] * out["base"]})
    d["Change (MW)"] = d["After (MW)"] - d["Before (MW)"]
    d = d.reindex(d["Change (MW)"].abs().sort_values(ascending=False).index)
    dv = r["V (pu)"] - out["res"]["V (pu)"]
    right.metric("Lowest voltage after outage",
                 f"{r['V (pu)'].min():.3f} pu",
                 f"{dv.min():+.3f} pu at bus "
                 f"{int(r.loc[dv.idxmin(), 'Bus'])}", delta_color="normal")
    right.caption("Flow redistribution, largest change first. Positive P "
                  "flows From → To.")
    right.dataframe(d.round(1), hide_index=True)


def _tab_pv(out):
    pv, lam = out["pv"]
    st.caption("Every load and generator is scaled by λ and re-solved "
               "(Newton-Raphson) until the case stops solving. The last "
               "solvable λ is a lower bound on the nose point; there are no "
               "generator Q limits, so real margins are smaller.")
    V = pv.drop(columns="lambda")
    weak = V.iloc[-1].nsmallest(3)
    under = pv[(V < out["vmin"]).any(axis=1)]
    lam_v = float(under["lambda"].iloc[0]) if len(under) else None
    c = st.columns(3)
    with c[0].container(key="kpi-plain-pv0"):
        st.metric("Loadability margin", f"{lam:.2f}x base",
                  f"{(lam - 1) * out['load']:.0f} MW extra load",
                  delta_color="off", delta_arrow="off")
    with c[1].container(key="kpi-plain-pv1"):
        st.metric("Weakest bus", weak.index[0],
                  f"{weak.iloc[0]:.3f} pu at the nose", delta_color="off",
                  delta_arrow="off")
    with c[2].container(key="kpi-plain-pv2"):
        st.metric("First Vmin violation",
                  f"λ = {lam_v:.2f}" if lam_v is not None else "none",
                  "before the nose" if lam_v is not None else
                  "all buses stay above Vmin", delta_color="off",
                  delta_arrow="off")
    _, mid, _ = st.columns([1, 5, 1])
    _plot(pv_curves(pv, lam, out["vmin"]), "P-V curves for every bus", mid)


def _tab_sc(out):
    with st.container(horizontal=True):
        xd = st.number_input("Generator Xd'' (pu)", 0.001, 10.0, 0.2,
                             help="Subtransient reactance of every unit, in "
                                  "per unit on the case base.")
        zf = st.number_input("Fault impedance Zf (pu)", 0.0, 10.0, 0.0,
                             help="External impedance at the fault point.")
        kv = st.number_input("Base kV (for kA)", 0.1, 800.0, 33.0,
                             help="Nominal bus voltage; kA = pu · "
                                  "S_base / (sqrt(3) · kV). One value for "
                                  "all buses (known limitation).")
    try:
        sc, Z, V0, If = _faults(out["b"], out["l"], out["res"], xd,
                                zf, out["base"], kv)
    except Exception as e:
        st.session_state["sc"] = None
        st.error(f"Fault analysis failed: {e}")
        return
    st.session_state["sc"] = dict(tbl=sc, Z=Z, V0=V0, If=If)
    left, right = st.columns([1, 1], gap="medium")
    left.html(ui_theme.section("Fault levels per bus"))
    left.dataframe(sc.round(4), hide_index=True)
    right.html(ui_theme.section("Post-fault voltages"))
    fb = right.selectbox("Fault at bus", sc["Bus"].astype(int))
    vp = abs(V0 - Z[:, fb - 1] * If[fb - 1])
    _plot(fault_voltages(pd.Series(vp, index=sc["Bus"], dtype=float),
                         out["vmin"], out["vmax"]),
          f"Post-fault voltages for a fault at bus {fb}", right)


def _tab_ai(out):
    st.caption("Local Gemma via LM Studio rephrases the numbers; it does no "
               "math. Start the server and load a model first.")
    models = lm_models()
    if models:
        gi = next((i for i, m in enumerate(models) if "gemma" in m.lower()), 0)
        model = st.selectbox("Loaded model in LM Studio", models, index=gi,
                             help="Models loaded in LM Studio on port 1234.")
    else:
        model = st.text_input("Model id (LM Studio server not detected)",
                              help="LM Studio not reachable at "
                                   "http://127.0.0.1:1234 - start the server "
                                   "and load a model, or type its model id.")
    if st.button("Generate report", key="generate", type="primary",):
        if not model:
            st.warning("Pick or type a model id first.")
        else:
            try:
                with st.spinner("Generating report..."):
                    st.session_state["report"] = ai_report(out["summary"], model)
                    _shared()["report"] = (out["summary"],
                                           st.session_state["report"])
            except Exception as e:
                st.error(f"LM Studio request failed: {e} (is the server on? "
                         f"is the model loaded?)")
    report = st.session_state.get("report")
    st.download_button("Download study report",
                       report.encode() if report else b"",
                       "gridlens_report.md", "text/markdown", key="dl_report",
                       disabled=not report)
    if report:
        st.write(report)
    else:
        st.caption("No report yet: generate it above.")


def _load_problem(bus, lines, sbase):
    """Problem input -> study case (on_click, runs before the widgets)."""
    st.session_state["bus_tbl"] = bus.copy()
    st.session_state["lines_tbl"] = lines.copy()
    st.session_state["case_src"] = "problem"
    st.session_state["case_label"] = "Problem input"
    st.session_state["problems"] = None
    st.session_state["notes"] = None
    _set_base(sbase)
    _bump("bus")
    _bump("lines")


def _tab_problem(out):
    ui_problem.page(_load_problem)


def _tab_dashboard(out):
    _strip(out)
    if out.get("qlog"):
        st.html(ui_theme.section("Generator Q limits: bus type switching"))
        st.dataframe(pd.DataFrame(out["qlog"]), hide_index=True)
    _tab_loadflow(out)


PAGES = (("Dashboard", "dashboard", _tab_dashboard),
         ("Problem input", "problem", _tab_problem),
         ("Network diagram", "network", _tab_network),
         ("Solver check", "solver-check", _tab_cmp),
         ("Contingency N-1", "contingency", _tab_n1),
         ("PV analysis", "pv-analysis", _tab_pv),
         ("Fault levels", "fault-levels", _tab_sc),
         ("Study report", "study-report", _tab_ai))


STANDALONE = {"problem"}


def _page(title, path, body):
    """One study page: header strip with an open-in-new-tab link, then the
    page body (the Dashboard also holds the case editors)."""
    def run():
        with st.container(horizontal=True, vertical_alignment="center",
                          horizontal_alignment="distribute"):
            st.html(f'<div class="gl-page">{title}</div>')
            st.link_button("Open in new tab",       # default page lives at /
                           "./" if path == "dashboard" else f"./{path}",
                           width="content")
        cfg = st.session_state["cfg"]
        out = st.session_state.get("out")
        if path in STANDALONE:          # tools that need no solved case
            body(out)
            return
        if path == "dashboard":
            _editors(cfg)
            _, right = st.columns([4, 1.4])
            with right.container(horizontal=True,
                                 horizontal_alignment="right"):
                run = st.button("Run study", type="primary", key="solve",
                                help="Solve the load flow and run all studies.")
                st.button("Reset tables", key="reset_tables",
                          on_click=_pick_case)
            if run:
                _solve(cfg)
                st.rerun()
        elif out is None or st.session_state.get("run_sig") != _inputs_sig(cfg):
            st.caption("Results out of date. Run study on the Dashboard.")
        if out:
            body(out)
    run.__name__ = f"page_{path.replace('-', '_')}"
    return st.Page(run, title=title, url_path=path,
                   default=path == "dashboard")


def main():
    st.set_page_config(page_title="GridLens - Power System Analysis",
                       layout="wide")
    pg = st.navigation({"Pages": [_page(*p) for p in PAGES]},
                       position="sidebar")
    _init()
    ui_theme.inject()
    cfg = _sidebar()
    st.session_state["cfg"] = cfg

    out = st.session_state.get("out")
    st.html(ui_theme.banner_html([
        ("Case", st.session_state.get("case_label") or _case_label()),
        ("Buses / branches", f"{len(st.session_state['bus_tbl'])} / "
                             f"{len(st.session_state['lines_tbl'])}"),
        ("Base", f"{(out or cfg)['base']:g} MVA"),
        ("Limits", f"{(out or cfg)['vmin']:.2f}-{(out or cfg)['vmax']:.2f} pu"),
        ("Solution", ("SOLVED" if out["ok"] else "NOT SOLVED") if out
         else "—")]))
    st.html(ui_theme.statusbar_html(
        [("Solver", out["method"] if out else "-"),
         ("Iterations", out["its"] if out else "-"),
         ("Tolerance", f"{out['tol']:g}" if out else "-"),
         ("Status", ("Converged" if out["ok"] else "Not converged")
          if out else "Ready")]))
    problems = st.session_state.get("problems")
    if problems:
        st.error("Fix the data before solving:",)
        for p in problems:
            st.markdown(f"- {p}")
    notes = st.session_state.get("notes")
    if notes:
        st.info(". ".join(notes))
    errs = st.session_state.get("upload_errs")
    if errs:
        st.sidebar.error(". ".join(errs))

    pg.run()


if __name__ == "__main__":
    main()
