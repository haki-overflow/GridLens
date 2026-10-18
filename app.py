"""GridLens: N-bus power system analysis GUI (load flow, N-1, faults).

Run:    streamlit run app.py
AI:     LM Studio -> Developer tab -> load Gemma -> Start Server (port 1234)

The solver does all the math; a local Gemma model only explains the results.
Quantities are per unit unless a tooltip says otherwise.
"""
import io
import zipfile

import numpy as np
import pandas as pd
import streamlit as st

import ui_theme
from ai_report import ai_report, lm_models
from cases import CASES
from plotting import (convergence_history, draw_network, fault_voltages,
                      voltage_profile)
from solver import METHODS, solve_loadflow
from studies import contingency, fault_analysis

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
                tol=1e-8, taps=False, shunts=False)


def _bump(which):
    st.session_state[f"{which}_v"] += 1


def _pick_case():
    bus, lines = CASES[st.session_state["case"]]
    st.session_state["bus_tbl"] = bus.copy()
    st.session_state["lines_tbl"] = lines.copy()
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
        cols = BUS_COLS if which == "bus" else LINE_COLS
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


def _init():
    if "bus_tbl" not in st.session_state:
        name = next(iter(CASES))
        st.session_state["bus_tbl"] = CASES[name][0].copy()
        st.session_state["lines_tbl"] = CASES[name][1].copy()
    st.session_state.setdefault("bus_v", 0)
    st.session_state.setdefault("lines_v", 0)
    st.session_state.setdefault("problems", None)
    st.session_state.setdefault("notes", None)
    st.session_state.setdefault("sc", None)


def _cfg():
    mode = st.session_state.get("mode", "Quick")
    std = mode in ("Standard", "Advanced")
    adv = mode == "Advanced"
    cfg = dict(DEFAULTS)
    if std:
        cfg.update(method=st.session_state.get("method", DEFAULTS["method"]),
                   base=st.session_state.get("base", DEFAULTS["base"]),
                   vmin=st.session_state.get("vmin", DEFAULTS["vmin"]),
                   vmax=st.session_state.get("vmax", DEFAULTS["vmax"]))
    if adv:
        cfg.update(tol=st.session_state.get("tol", DEFAULTS["tol"]),
                   taps=st.session_state.get("taps", False),
                   shunts=st.session_state.get("shunts", False))
    cfg.update(mode=mode,
               run_n1=st.session_state.get("run_n1", True),
               run_cmp=st.session_state.get("run_cmp", True),
               run_sc=st.session_state.get("run_sc", False),
               run_ai=st.session_state.get("run_ai", False))
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

        st.header("Solver")
        if std:
            st.selectbox(
                "Method", METHODS, key="method",
                help="Newton-Raphson: quadratic, most robust. Fast "
                     "Decoupled: XB approximation, quadratic-ish. "
                     "Gauss-Seidel: linear convergence.")
            cl, cr = st.columns(2)
            cl.number_input("Min voltage (pu)", 0.5, 1.5, 0.95, step=0.01,
                            key="vmin",
                            help="Lower voltage limit for violation "
                                 "tracking (per unit).")
            cr.number_input("Max voltage (pu)", 0.5, 1.5, 1.10, step=0.01,
                            key="vmax",
                            help="Upper voltage limit for violation "
                                 "tracking (per unit).")
            st.number_input("Base MVA", 1.0, 10000.0, 100.0, step=1.0,
                            key="base",
                            help="System base power; per-unit results "
                                 "convert to MW/MVAr with this.")
        if adv:
            st.toggle("Transformer taps", key="taps",
                      help="Show the line Tap column (off-nominal ratio, "
                           "1 = none). When off, Tap = 1 is used.")
            st.toggle("Shunt elements", key="shunts",
                      help="Show the bus Bs column (shunt susceptance). "
                           "When off, Bs = 0 is used.")
            st.number_input("Solver tolerance", 1e-12, 1e-3, DEFAULTS["tol"],
                            format="%g",
                            key="tol",
                            help="Power-mismatch convergence threshold "
                                 "(per unit). Note: Gauss-Seidel uses its "
                                 "own default tolerance.")

        st.header("Studies")
        st.checkbox("N-1 contingency", key="run_n1", value=True,
                    help="Remove each line in turn, re-solve, rank by "
                         "severity and violations.")
        st.checkbox("Method comparison", key="run_cmp", value=True,
                    help="Solve with all three methods and compare "
                         "convergence, loss and minimum voltage.")
        st.checkbox("Short circuit", key="run_sc", value=False,
                    help="Three-phase fault at every bus via the Zbus "
                         "matrix (loads neglected, generators as Xd'').")
        st.checkbox("AI report", key="run_ai", value=False,
                    help="Local Gemma writes a plain-English summary; it "
                         "never computes numbers, needs LM Studio running.")

        st.header("Appearance")
        st.toggle("Dark theme", key="dark_theme",
                  help="Light is the default; this switches the app to the "
                       "dark palette.")
    return _cfg()


def _editors(cfg):
    if st.session_state.get("last_shunts") != bool(cfg["shunts"]):
        st.session_state["last_shunts"] = bool(cfg["shunts"])
        _bump("bus")
    if st.session_state.get("last_taps") != bool(cfg["taps"]):
        st.session_state["last_taps"] = bool(cfg["taps"])
        _bump("lines")
    st.subheader("Bus data")
    st.caption("Per unit. Loads Pd/Qd are positive demand; Pg/Qg are "
               "injections. V is the setpoint (Slack/PV) or start guess.")
    bus_view = st.session_state["bus_tbl"] if cfg["shunts"] else \
        st.session_state["bus_tbl"].drop(columns="Bs", errors="ignore")
    bus = st.data_editor(
        bus_view, num_rows="dynamic", hide_index=True,
        key=f"bus_ed_{st.session_state['bus_v']}",
        column_config={"Type": st.column_config.SelectboxColumn(
            "Type", options=["Slack", "PV", "PQ"],
            help="Slack: swing bus. PV: held |V|. PQ: load bus.")})
    st.session_state["bus_tbl"] = bus

    st.subheader("Line data")
    st.caption("From/To are 1-based bus numbers. B is total line-charging "
               "susceptance, split B/2 at each end.")
    line_view = st.session_state["lines_tbl"] if cfg["taps"] else \
        st.session_state["lines_tbl"].drop(columns="Tap", errors="ignore")
    lines = st.data_editor(
        line_view, num_rows="dynamic", hide_index=True,
        key=f"lines_ed_{st.session_state['lines_v']}",
        column_config={
            "From": st.column_config.NumberColumn("From", step=1),
            "To": st.column_config.NumberColumn("To", step=1)})
    st.session_state["lines_tbl"] = lines


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


def _solve(cfg):
    b, l, probs, notes = _prep(cfg)
    if probs:
        st.session_state["problems"] = probs
        st.session_state["notes"] = None
        st.session_state.pop("out", None)
        return
    st.session_state["problems"] = None
    st.session_state["notes"] = notes
    try:
        res, flows, ok, hist = solve_loadflow(b, l, cfg["method"], cfg["tol"])
    except Exception as e:
        st.session_state["problems"] = [f"Solver failed: {e}"]
        st.session_state["notes"] = None
        st.session_state.pop("out", None)
        return
    cmp_df, n1 = None, None
    if cfg["run_cmp"]:
        rows = []
        for m in METHODS:
            r2, f2, ok2, h2 = solve_loadflow(b, l, m)
            rows.append([m, ok2, len(h2) - 1,
                         round(f2["Loss_P"].sum() * cfg["base"], 4),
                         round(r2["V (pu)"].min(), 4)])
        cmp_df = pd.DataFrame(rows, columns=["Method", "Converged",
                                             "Iterations", "Loss (MW)",
                                             "Min V (pu)"])
    if cfg["run_n1"]:
        n1 = contingency(b, l, cfg["vmin"], cfg["vmax"])
    base, vmin, vmax = cfg["base"], cfg["vmin"], cfg["vmax"]
    loss = flows["Loss_P"].sum() * base
    load = b["Pd"].sum() * base
    k = int(np.where(b["Type"].values == "Slack")[0][0])
    out = dict(res=res, flows=flows, ok=ok, its=len(hist) - 1, hist=hist,
               method=cfg["method"], tol=cfg["tol"], b=b, l=l, cmp=cmp_df,
               n1=n1, loss=loss, load=load, vmin=vmin, vmax=vmax, base=base,
               sc_on=cfg["run_sc"], ai_on=cfg["run_ai"],
               slack_k=k + 1, slack_p=res["P_inj"].iloc[k] * base,
               summary=(f"Method: {cfg['method']}, base {base} MVA\n"
                        + res.round(4).to_string(index=False)
                        + f"\nTotal load: {load:.2f} MW. "
                        + f"Total real loss: {loss:.2f} MW"
                        + (f" ({loss / load * 100:.1f}% of load)." if load
                           else ".")
                        + f" Voltage limits: {vmin}-{vmax} pu."
                        + ("\nWorst N-1 line outages (worst first):\n"
                           + n1.head(3).to_string(index=False)
                           if n1 is not None else "")))
    st.session_state["sc"] = None
    st.session_state.pop("report", None)
    st.session_state["out"] = out


def _card(col, idx, tone, label, value, delta=None):
    with col:
        with st.container(key=f"kpi-{tone}-{idx}"):
            st.metric(label, value, delta, delta_color="off",
                      border=False)


def _strip(out):
    better = "ok" if out["ok"] else "bad"
    row = st.container(horizontal=True, vertical_alignment="center")
    with row:
        st.markdown(ui_theme.badge("Converged" if out["ok"] else "Diverged",
                                   better), unsafe_allow_html=True)
        n1 = out["n1"]
        if n1 is not None:
            viol = pd.to_numeric(n1["Violations"], errors="coerce").fillna(0)
            secure = n1["Status"].eq("FAILED").sum() == 0 and viol.sum() == 0
            st.markdown(ui_theme.badge("N-1 secure" if secure else
                                       "N-1 violations",
                                       "ok" if secure else "bad"),
                        unsafe_allow_html=True)
        cmp_ = out["cmp"]
        if cmp_ is not None and not cmp_["Converged"].all():
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


def _tab_loadflow(out):
    st.subheader("Bus results")
    st.dataframe(out["res"].round(4), hide_index=True)
    st.subheader("Voltage profile")
    st.pyplot(voltage_profile(out["res"], out["vmin"], out["vmax"]),
              alt="Bus voltage profile")
    st.subheader("Line flows (pu)")
    st.dataframe(out["flows"].round(4), hide_index=True)
    st.subheader("Convergence history")
    st.pyplot(convergence_history(out["hist"]),
              alt=f"Mismatch error per iteration, {out['method']}")


def _tab_network(out):
    st.caption("Bus circles show |V| (red outline = outside the limits); "
               "line width follows |P_ij|; the arrow marks flow direction.")
    st.pyplot(draw_network(out["res"], out["l"], out["vmin"], out["vmax"],
                           out["flows"], base=out["base"]),
              alt="Network diagram coloured by bus voltage")


def _tab_cmp(out):
    st.caption("Same case through all three methods. Gauss-Seidel uses its "
               "own default tolerance.")
    st.dataframe(out["cmp"], hide_index=True)


def _tab_n1(out):
    st.caption("Each line removed in turn, case re-solved (Newton-Raphson), "
               "ranked worst first.")
    st.dataframe(out["n1"], hide_index=True)


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
        sc, Z, V0, If = fault_analysis(out["b"], out["l"], out["res"], xd,
                                       zf, out["base"], kv)
    except Exception as e:
        st.session_state["sc"] = None
        st.error(f"Fault analysis failed: {e}")
        return
    st.session_state["sc"] = dict(tbl=sc, Z=Z, V0=V0, If=If)
    st.dataframe(sc.round(4), hide_index=True)
    fb = st.selectbox("Show post-fault voltages for a fault at bus",
                      sc["Bus"].astype(int))
    vp = abs(V0 - Z[:, fb - 1] * If[fb - 1])
    st.pyplot(fault_voltages(pd.Series(vp, index=sc["Bus"], dtype=float),
                             out["vmin"], out["vmax"]),
              alt=f"Post-fault voltages for a fault at bus {fb}")


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
                with st.spinner("Gemma is writing..."):
                    st.session_state["report"] = ai_report(out["summary"], model)
            except Exception as e:
                st.error(f"LM Studio request failed: {e} (is the server on? "
                         f"is the model loaded?)")
    report = st.session_state.get("report")
    if report:
        st.write(report)
        st.download_button("Download report (Markdown)", report.encode(),
                           "gridlens_report.md", "text/markdown",
                           key="dl_report")


def _fig_zip(out):
    figs = [("network.png",
             draw_network(out["res"], out["l"], out["vmin"], out["vmax"],
                          out["flows"], base=out["base"])),
            ("voltage_profile.png",
             voltage_profile(out["res"], out["vmin"], out["vmax"])),
            ("convergence.png", convergence_history(out["hist"]))]
    sc = st.session_state.get("sc") if out.get("sc_on") else None
    if sc is not None:
        tbl = sc["tbl"]
        vb = int(tbl.loc[tbl["Fault I (pu)"].idxmax(), "Bus"])
        vp = abs(sc["V0"] - sc["Z"][:, vb - 1] * sc["If"][vb - 1])
        figs.append((f"post_fault_voltages_bus_{vb}.png",
                     fault_voltages(pd.Series(vp, index=tbl["Bus"],
                                              dtype=float),
                                    out["vmin"], out["vmax"])))
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, fig in figs:
            bio = io.BytesIO()
            fig.savefig(bio, format="png", dpi=150, bbox_inches="tight")
            z.writestr(name, bio.getvalue())
            plt.close(fig)
    return buf.getvalue()


def _tab_export(out):
    st.subheader("Result tables")
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button("Bus results (CSV)", out["res"].round(6).to_csv(index=False).encode(),
                       "gridlens_bus_results.csv", "text/csv",
                       key="dl_res")
    c2.download_button("Line flows (CSV)",
                       out["flows"].round(6).to_csv(index=False).encode(),
                       "gridlens_line_flows.csv", "text/csv",
                       key="dl_flows")
    c3.download_button("N-1 contingency (CSV)", out["n1"].to_csv(index=False).encode()
                       if out["n1"] is not None else b"",
                       "gridlens_n1.csv", "text/csv", key="dl_n1",
                       disabled=out["n1"] is None,
                       help="Enable the N-1 study in the sidebar to fill "
                            "this table.")
    sc = st.session_state.get("sc") if out.get("sc_on") else None
    c4.download_button("Fault table (CSV)",
                       sc["tbl"].round(6).to_csv(index=False).encode()
                       if sc is not None else b"",
                       "gridlens_faults.csv", "text/csv", key="dl_sc",
                       disabled=sc is None,
                       help="Enable Short circuit in the sidebar and set "
                            "Xd'', Zf, base kV.")
    st.subheader("All figures (PNG bundle)")
    st.download_button("Download figures.zip", _fig_zip(out),
                       "gridlens_figures.zip", "application/zip",
                       key="dl_zip")
    st.subheader("Current input tables")
    c1, c2 = st.columns(2)
    c1.download_button("Current bus table (CSV)",
                       st.session_state["bus_tbl"].to_csv(index=False).encode(),
                       "gridlens_bus_input.csv", "text/csv", key="dl_bin",)
    c2.download_button("Current line table (CSV)",
                       st.session_state["lines_tbl"].to_csv(index=False).encode(),
                       "gridlens_lines_input.csv", "text/csv", key="dl_lout",)


def _tabs(out):
    tabs_def = [("Load flow", _tab_loadflow), ("Network diagram", _tab_network)]
    if out["cmp"] is not None:
        tabs_def.append(("Method comparison", _tab_cmp))
    if out["n1"] is not None:
        tabs_def.append(("N-1 contingency", _tab_n1))
    if out.get("sc_on"):
        tabs_def.append(("Short circuit", _tab_sc))
    if out.get("ai_on"):
        tabs_def.append(("AI report", _tab_ai))
    tabs_def.append(("Export", _tab_export))
    for tab, (_, fn) in zip(st.tabs([t[0] for t in tabs_def]), tabs_def):
        with tab:
            fn(out)


def main():
    st.set_page_config(page_title="GridLens - Power System Analysis",
                       layout="wide")
    _init()
    ui_theme.inject()
    st.html(ui_theme.banner_html())
    cfg = _sidebar()
    _editors(cfg)

    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("Solve", type="primary", key="solve"):
            _solve(cfg)
        st.button("Reset tables", key="reset_tables", width="content",
                  on_click=_pick_case)
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

    out = st.session_state.get("out")
    if out:
        _strip(out)
        _tabs(out)
    else:
        st.info(
            "Adjust the tables above (or load a preset / CSVs) and press "
            "**Solve**.", title="No results yet",)


if __name__ == "__main__":
    main()
