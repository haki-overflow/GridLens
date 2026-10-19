"""GridLens: N-bus power system analysis GUI (load flow, N-1, faults).

Run:    streamlit run app.py
AI:     LM Studio -> Developer tab -> load Gemma -> Start Server (port 1234)

The solver does all the math; a local Gemma model only explains the results.
Quantities are per unit unless a tooltip says otherwise.
"""
import numpy as np
import pandas as pd
import streamlit as st

import gridcore
import ui_problem
import ui_theme
import ui_topics
import ui_working
from ai_report import ai_report, lm_models
import figures
from cases import CASES, COORDS
from figures import (convergence_history, fault_voltages,
                      pv_curves, voltage_profile)
from solver import METHODS
from studies import fault_analysis

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


def _settings(adv):
    """Method, limits, base (Standard) plus taps / shunts / Q limits /
    tolerance (Advanced), inside the sidebar's Study settings group."""
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

        st.link_button("Open workspace (new UI)", "http://localhost:8000",
                       help="The PSCAD-style workspace. Start it with "
                            "./run_workspace.sh.", width="stretch")
        if std:
            with st.expander("Study settings", expanded=False):
                _settings(adv)
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
    box = st.expander(f"Edit case data · {nb} buses, {nl} lines",
                      expanded=False)
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
    return gridcore.prep_case(st.session_state["bus_tbl"],
                              st.session_state["lines_tbl"], cfg)


@st.cache_data(show_spinner="Running studies...", max_entries=32)
def _study(b, l, method, tol, base, vmin, vmax, qlim=False):
    """gridcore.run_study, cached on the case and settings so any page or
    browser tab gets the same results without re-solving."""
    return gridcore.run_study(b, l, method, tol, base, vmin, vmax, qlim)


@st.cache_data(show_spinner=False, max_entries=64)
def _outage(b, l, k):
    return gridcore.outage(b, l, k)


@st.cache_data(show_spinner=False, max_entries=32)
def _faults(b, l, res, xd, zf, base, kv):
    return fault_analysis(b, l, res, xd, zf, base, kv)


def _inputs_sig(cfg):
    """Fingerprint of the inputs a run depends on (tables + settings)."""
    h = [int(pd.util.hash_pandas_object(st.session_state[k]).sum())
         for k in ("bus_tbl", "lines_tbl")]
    return tuple(h) + tuple(cfg[k] for k in ("method", "tol", "base", "vmin",
                                              "vmax", "taps", "shunts", "qlim"))


def _stale(cfg):
    out = st.session_state.get("out")
    return out is not None and st.session_state.get("run_sig") != _inputs_sig(cfg)


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
    cols = st.columns(4)
    vmin_ok = out["res"]["V (pu)"].min() >= out["vmin"]
    vmax_ok = out["res"]["V (pu)"].max() <= out["vmax"]
    loss = out["loss"]
    loss_pct = (loss / out["load"] * 100) if out["load"] else None
    _card(cols[0], 0, "plain", f"Slack P · bus {out['slack_k']}",
          f"{out['slack_p']:.1f} MW",
          delta=f"load {out['load']:.1f} MW")
    _card(cols[1], 1, "plain", "Losses", f"{loss:.1f} MW",
          delta=f"{loss_pct:.1f}% of load" if loss_pct is not None else None)
    _card(cols[2], 2, "ok" if vmin_ok else "bad", "Min |V| · bus "
          f"{int(out['res'].loc[out['res']['V (pu)'].idxmin(), 'Bus'])}",
          f"{out['res']['V (pu)'].min():.3f} pu")
    _card(cols[3], 3, "ok" if vmax_ok else "bad", "Max |V| · bus "
          f"{int(out['res'].loc[out['res']['V (pu)'].idxmax(), 'Bus'])}",
          f"{out['res']['V (pu)'].max():.3f} pu")


def _plot(fig, alt, where=st):
    import matplotlib.pyplot as plt
    where.pyplot(fig, alt=alt, width="stretch")
    plt.close(fig)


def _bus_report(out):
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
    return rep.round({"V (pu)": 4, "Angle (deg)": 2, "P gen (MW)": 1,
                      "Q gen (MVAr)": 1, "P load (MW)": 1, "Q load (MVAr)": 1})


def _branch_report(out):
    base, fl = out["base"], out["flows"]
    br = pd.DataFrame({
        "From": fl["From"], "To": fl["To"],
        "P from (MW)": fl["P_ij"] * base, "Q from (MVAr)": fl["Q_ij"] * base,
        "P to (MW)": fl["P_ji"] * base, "Q to (MVAr)": fl["Q_ji"] * base,
        "Loss (MW)": fl["Loss_P"] * base, "Loss (MVAr)": fl["Loss_Q"] * base})
    return br.round(2)


@st.dialog("Bus report", width="large")
def _dlg_bus(out):
    st.dataframe(_bus_report(out), hide_index=True)


@st.dialog("Branch report", width="large")
def _dlg_branch(out):
    st.dataframe(_branch_report(out), hide_index=True)


@st.dialog("Voltage profile", width="large")
def _dlg_voltage(out):
    _plot(voltage_profile(out["res"], out["vmin"], out["vmax"]),
          "Bus voltage profile")


@st.dialog("Convergence", width="large")
def _dlg_conv(out):
    st.caption(f"Max power mismatch per iteration, {out['method']}.")
    _plot(convergence_history(out["hist"]),
          f"Mismatch error per iteration, {out['method']}")


def _violations(out):
    """Short list of voltage limit violations in the base case."""
    res = out["res"]
    v = res["V (pu)"]
    bad = res[(v < out["vmin"]) | (v > out["vmax"])]
    if bad.empty:
        st.html('<div class="gl-ok">No voltage violations in the base case '
                f'({out["vmin"]:.2f}\u2013{out["vmax"]:.2f} pu).</div>')
        return
    st.html(ui_theme.section("Base-case violations"))
    for _, r in bad.iterrows():
        lim = out["vmin"] if r["V (pu)"] < out["vmin"] else out["vmax"]
        st.html(f'<div class="gl-bad">Bus {int(r["Bus"])}: '
                f'{r["V (pu)"]:.4f} pu '
                f'({"below" if r["V (pu)"] < lim else "above"} {lim:.2f})</div>')


def _tab_loadflow(out):
    """Dashboard body: verdict first, details one click away."""
    _violations(out)
    st.html(ui_theme.section("Details"))
    c = st.columns(4)
    if c[0].button("Bus report", width="stretch", key="d_bus"):
        _dlg_bus(out)
    if c[1].button("Branch report", width="stretch", key="d_br"):
        _dlg_branch(out)
    if c[2].button("Voltage profile", width="stretch", key="d_v"):
        _dlg_voltage(out)
    if c[3].button("Convergence", width="stretch", key="d_c"):
        _dlg_conv(out)


LAYERS = (("Flows (MW)", "flows", False), ("Angles", "angles", False),
          ("Loads", "loads", True), ("Generators", "gens", True),
          ("Breakers", "breakers", False))
CHART_CFG = {"scrollZoom": True, "displaylogo": False,
             "modeBarButtons": [["zoom2d", "pan2d", "resetScale2d"]]}


def _diagram(out, key, height, tripped=None, flows=None, res=None,
             show=None, selected=None, on_select="ignore"):
    """Plotly one-line diagram of the solved case (or an outage case)."""
    label = st.session_state.get("case_label")
    fig = figures.figure(res if res is not None else out["res"], out["l"],
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
        ev = _diagram(out, "net_chart", 460, show=show, selected=sel,
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
            title, rows = figures.inspect(out["res"], out["l"], out["flows"],
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
    n1 = out["n1"]
    bad = int((n1["Status"].eq("FAILED")
               | (pd.to_numeric(n1["Violations"], errors="coerce")
                  .fillna(0) > 0)).sum())
    worst = n1.iloc[0]
    st.html(f'<div class="{"gl-bad" if bad else "gl-ok"}">'
            + (f"{bad} of {len(n1)} single-line outages are insecure; worst: "
               f"line {worst['Outage']}, minimum {worst['Min V (pu)']} pu at "
               f"bus {worst['At bus']}." if bad else
               f"All {len(n1)} single-line outages are secure.") + "</div>")
    t_rank, t_viol, t_expl = st.tabs(["Ranking", "Limit violations",
                                      "Explorer"])
    with t_rank:
        st.dataframe(n1, hide_index=True)
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
    with t_viol:
        if rows:
            st.dataframe(pd.DataFrame(rows, columns=[
                "Contingency", "Monitored element", "Value (pu)",
                "Limit (pu)", "Violation"]), hide_index=True)
        else:
            st.caption("No post-contingency limit violations.")
    with t_expl:
        _n1_explorer(out)


def _n1_explorer(out):
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


def _load_problem(bus, lines, sbase, conversion=None):
    """Problem input -> study case (on_click, runs before the widgets)."""
    st.session_state["prob_conv"] = conversion
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


def _tab_answer(out):
    conv = st.session_state.get("prob_conv") \
        if st.session_state.get("case_src") == "problem" else None
    ui_working.page_answer(out, conv)


def _tab_dashboard(out):
    _strip(out)
    if out.get("qlog"):
        st.html(ui_theme.section("Generator Q limits: bus type switching"))
        st.dataframe(pd.DataFrame(out["qlog"]), hide_index=True)
    _tab_loadflow(out)


PAGES = {
    "Load flow": (("Dashboard", "dashboard", _tab_dashboard),
                  ("Problem input", "problem", _tab_problem),
                  ("Network diagram", "network", _tab_network),
                  ("Solver check", "solver-check", _tab_cmp)),
    "Worked solution": (("Ybus matrix", "ybus", ui_working.page_ybus),
                        ("Iterations", "iterations", ui_working.page_iterations),
                        ("Worked answer", "answer", _tab_answer)),
    "Studies": (("Contingency N-1", "contingency", _tab_n1),
                ("PV analysis", "pv-analysis", _tab_pv),
                ("Fault levels", "fault-levels", _tab_sc),
                ("Unsymmetrical faults", "faults", ui_topics.page_seqfault),
                ("Economic dispatch", "dispatch", ui_topics.page_dispatch)),
    "Calculators": (("Symmetrical components", "symmetrical", ui_topics.page_symcomp),
                    ("Line parameters", "line", ui_topics.page_tline)),
    "Report": (("Study report", "study-report", _tab_ai),),
}


STANDALONE = {"problem", "dispatch", "symmetrical", "line"}


def _page(title, path, body):
    """One study page: header strip with an open-in-new-tab link, then the
    page body (the Dashboard also holds the case editors)."""
    def run():
        cfg = st.session_state["cfg"]
        out = st.session_state.get("out")
        results = path not in STANDALONE and path != "dashboard"
        with st.container(horizontal=True, vertical_alignment="center"):
            st.html(f'<div class="gl-page">{title}</div>')
            st.space("stretch")
            rerun = st.button("Re-run study", type="primary",
                              key=f"rerun_{path}", width="content",
                              help="Solve the current case again and refresh "
                                   "every page.") if results else False
            st.link_button("Open in new tab",       # default page lives at /
                           "./" if path == "dashboard" else f"./{path}",
                           width="content")
        if rerun:
            _solve(cfg)
            st.rerun()
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
        elif out is None:
            st.html('<div class="gl-stale">No results yet: press Re-run study '
                    '(or Run study on the Dashboard).</div>')
        elif _stale(cfg):
            st.html('<div class="gl-stale">STALE: the case or settings changed '
                    'since the last run. Re-run study to update this page.</div>')
        if out:
            body(out)
    run.__name__ = f"page_{path.replace('-', '_')}"
    return st.Page(run, title=title, url_path=path,
                   default=path == "dashboard")


def main():
    st.set_page_config(page_title="GridLens - Power System Analysis",
                       layout="wide")
    pg = st.navigation({group: [_page(*p) for p in pages]
                        for group, pages in PAGES.items()},
                       position="top")
    _init()
    ui_theme.inject()
    cfg = _sidebar()
    st.session_state["cfg"] = cfg

    out = st.session_state.get("out")
    head = st.empty()       # filled after the page ran (its edits count)
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
    out = st.session_state.get("out")
    sol = ("—", "") if out is None else ("STALE", "stale") if _stale(cfg) \
        else ("SOLVED" if out["ok"] else "NOT SOLVED", "")
    head.html(ui_theme.banner_html([
        ("Case", st.session_state.get("case_label") or _case_label()),
        ("Buses / branches", f"{len(st.session_state['bus_tbl'])} / "
                             f"{len(st.session_state['lines_tbl'])}"),
        ("Base", f"{cfg['base']:g} MVA"),
        ("Limits", f"{cfg['vmin']:.2f}-{cfg['vmax']:.2f} pu"),
        ("Solution", *sol)]))


if __name__ == "__main__":
    main()
