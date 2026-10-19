"""Textbook topic pages: unsymmetrical faults, symmetrical components,
economic dispatch and transmission line parameters. The math lives in
seqfaults.py, symcomp.py, dispatch.py and tline.py."""
import numpy as np
import pandas as pd
import streamlit as st

import dispatch as D
import seqfaults as SF
import symcomp as SC
import tline as TL
import ui_tables
import ui_theme
from working import cfmt, pfmt

CONN = ["Yg", "Y", "D"]


def _kpis(items):
    cols = st.columns(len(items))
    for k, (col, (label, value, delta)) in enumerate(zip(cols, items)):
        with col.container(key=f"kpi-plain-t{k}-{label[:6]}"):
            st.metric(label, value, delta, delta_color="off", delta_arrow="off")


# ------------------------------------------------------- unsymmetrical faults
def page_seqfault(out):
    bus, lines = out["b"], out["l"]
    n = len(bus)
    seed = (n, tuple(zip(lines["From"], lines["To"])))
    c = st.columns([1.6, 0.8, 0.7, 0.7, 1.6], vertical_alignment="bottom")
    kind = c[0].segmented_control("Fault type", SF.TYPES, default="SLG",
                                  key="sf_kind") or "SLG"
    k = c[1].selectbox("Fault bus", list(range(1, n + 1)), key="sf_bus")
    zr = c[2].number_input("Zf R (pu)", 0.0, 10.0, 0.0, key="sf_zr")
    zx = c[3].number_input("Zf X (pu)", 0.0, 10.0, 0.0, key="sf_zx")
    pre = c[4].segmented_control("Prefault voltage", ["1.0∠0°", "Load flow"],
                                 default="1.0∠0°", key="sf_pre") or "1.0∠0°"
    vf = np.ones(n, complex) if pre == "1.0∠0°" else \
        out["res"]["V (pu)"].to_numpy() * np.exp(
            1j * np.radians(out["res"]["Angle (deg)"].to_numpy()))
    zf = complex(zr, zx)

    g0, b0 = SF.seed_tables(bus, lines)
    kv0 = bus["kV"].astype(float) if "kV" in bus else pd.Series([33.0] * n)
    kv_default = lambda: pd.DataFrame({"Bus": np.arange(1, n + 1),
                                       "kV": kv0.values})
    if st.button("Edit sequence data", key="sf_edit"):
        _dlg_seqdata(g0, b0, kv_default, seed)
    gens = ui_tables.table("sf_gens", lambda: g0, seed)
    br = ui_tables.table("sf_br", lambda: b0, seed)
    kvt = ui_tables.table("sf_kv", kv_default, seed)
    try:
        kv = kvt["kV"].astype(float).to_numpy()
        tab = SF.fault_table(kind, gens, br, vf, zf, out["base"], kv)
        r = SF.solve_fault(kind, k, gens, br, vf, zf, out["base"], kv)
    except Exception as e:
        st.error(f"Cannot build the sequence networks: {e}")
        return
    I0, I1, I2 = r["I012"]
    _kpis([(f"{kind} fault at bus {k}", f"{abs(r['Iabc']).max():.4f} pu",
            f"{abs(r['kA']).max():.3f} kA at {kv[k - 1]:g} kV"),
           ("Z1 / Z2 / Z0 (Thevenin)", " / ".join(f"{abs(z):.4f}" for z in r["Zth"]),
            "pu at the fault bus"),
           ("I1 / I2 / I0", f"{abs(I1):.3f} / {abs(I2):.3f} / {abs(I0):.3f}", "pu")])
    t_lvl, t_cur, t_vol, t_br = st.tabs(["Fault levels", "Fault currents",
                                         "Bus voltages", "Branch currents"])
    with t_lvl:
        st.caption(f"{kind} fault level at every bus.")
        st.dataframe(tab.round(4), hide_index=True)
    with t_cur:
        st.caption(f"Currents at the fault (bus {k}).")
        st.dataframe(pd.DataFrame({
            "": ["Sequence 0 / 1 / 2", "Phase a / b / c (pu)",
                 "Phase a / b / c (kA)"],
            "0 / a": [pfmt(I0), pfmt(r["Iabc"][0]), f"{r['kA'][0]:.4f}"],
            "1 / b": [pfmt(I1), pfmt(r["Iabc"][1]), f"{r['kA'][1]:.4f}"],
            "2 / c": [pfmt(I2), pfmt(r["Iabc"][2]), f"{r['kA'][2]:.4f}"]}),
            hide_index=True)
    with t_vol:
        st.caption("Bus voltages during the fault (pu).")
        V, Vp = r["V012"], r["Vabc"]
        st.dataframe(pd.DataFrame({
            "Bus": np.arange(1, n + 1),
            "V0": [pfmt(v) for v in V[:, 0]], "V1": [pfmt(v) for v in V[:, 1]],
            "V2": [pfmt(v) for v in V[:, 2]], "Va": [pfmt(v) for v in Vp[:, 0]],
            "Vb": [pfmt(v) for v in Vp[:, 1]], "Vc": [pfmt(v) for v in Vp[:, 2]]}),
            hide_index=True)
    with t_br:
        st.caption("Branch currents during the fault (pu, From → To).")
        L = r["lines"]
        st.dataframe(L.assign(**{c_: [pfmt(v) for v in L[c_]]
                                 for c_ in ("I0", "I1", "I2", "Ia", "Ib", "Ic")}),
                     hide_index=True)


@st.dialog("Sequence network data", width="large")
def _dlg_seqdata(g0, b0, kv_default, seed):
    st.caption("Reactances in pu on the system base. Generators: Conn Yg = "
               "grounded (X0 + 3Xn to ground), Y / D = no zero-sequence "
               "path. Transformers: Yg-Yg passes zero sequence, Yg-D "
               "grounds the Yg side, other pairs block it. Δ-Y phase "
               "shifts are not modelled.")
    t1, t2, t3 = st.tabs(["Generators", "Lines and transformers", "Base kV"])
    with t1:
        ui_tables.editor(t1, "sf_gens", lambda: g0, seed, num_rows="dynamic",
                         column_config={"Conn": st.column_config.SelectboxColumn(options=CONN)})
    with t2:
        ui_tables.editor(t2, "sf_br", lambda: b0, seed, column_config={
            "Kind": st.column_config.SelectboxColumn(options=["line", "transformer"]),
            "Conn From": st.column_config.SelectboxColumn(options=CONN),
            "Conn To": st.column_config.SelectboxColumn(options=CONN)})
    with t3:
        ui_tables.editor(t3, "sf_kv", kv_default, seed, disabled=["Bus"])
    if st.button("Apply and recalculate", type="primary", key="sf_apply"):
        st.rerun()


# ------------------------------------------------------ symmetrical components
def _phasors(prefix, key, defaults):
    vals = []
    cols = st.columns(3)
    for col, (name, (m, d)) in zip(cols, zip(prefix, defaults)):
        mm = col.number_input(f"|{name}|", value=m, key=f"{key}_{name}_m", format="%.4f")
        dd = col.number_input(f"∠{name} (°)", value=d, key=f"{key}_{name}_a", format="%.2f")
        vals.append(SC.polar(mm, dd))
    return np.array(vals)


def page_symcomp(out=None):
    st.caption("a = 1∠120° = −0.5 + j0.866,  a² = 1∠240°,  1 + a + a² = 0.  "
               "[Va Vb Vc]ᵀ = A [V0 V1 V2]ᵀ,  [V0 V1 V2]ᵀ = A⁻¹ [Va Vb Vc]ᵀ.")
    left, right = st.columns(2, gap="large")
    with left:
        st.html(ui_theme.section("Phase → sequence"))
        abc = _phasors(["Va", "Vb", "Vc"], "sc_p",
                       [(1.0, 0.0), (0.8, -110.0), (1.1, 125.0)])
        s = SC.to_sequence(abc)
        st.dataframe(pd.DataFrame({"Component": ["V0 (zero)", "V1 (positive)",
                                                 "V2 (negative)"],
                                   "Polar": [pfmt(v) for v in s],
                                   "Rectangular": [cfmt(v) for v in s]}),
                     hide_index=True)
        st.caption(f"Unbalance V2/V1 = {abs(s[2]) / max(abs(s[1]), 1e-12) * 100:.2f} %")
    with right:
        st.html(ui_theme.section("Sequence → phase"))
        s2 = _phasors(["V0", "V1", "V2"], "sc_s",
                      [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0)])
        p = SC.to_phase(s2)
        st.dataframe(pd.DataFrame({"Phase": ["Va", "Vb", "Vc"],
                                   "Polar": [pfmt(v) for v in p],
                                   "Rectangular": [cfmt(v) for v in p]}),
                     hide_index=True)
    st.html(ui_theme.section("Operator matrices"))
    a_, b_ = st.columns(2, gap="large")
    lab = ["0", "1", "2"]
    a_.caption("A (sequence → phase)")
    a_.dataframe(pd.DataFrame([[pfmt(v, 3) for v in r] for r in SC.A],
                              index=["a", "b", "c"], columns=lab))
    b_.caption("A⁻¹ (phase → sequence)")
    b_.dataframe(pd.DataFrame([[pfmt(v, 4) for v in r] for r in SC.A_INV],
                              index=lab, columns=["a", "b", "c"]))


# --------------------------------------------------------- economic dispatch
def page_dispatch(out=None):
    e = D.EXAMPLE
    c = st.columns([0.9, 1.3, 1.3, 0.9, 1.6], vertical_alignment="bottom")
    PD = c[0].number_input("Demand PD (MW)", 0.0, 1e6, e["PD"], key="ed_pd")
    loss = c[1].segmented_control("Losses", ["None", "B-coefficients"],
                                  default="B-coefficients", key="ed_loss") or "None"
    lim = c[2].segmented_control("Unit limits", ["On", "Off"], default="On",
                                 key="ed_lim") == "On"
    st.caption("Cost C = a + bP + cP² ($/h), P in MW. Losses PL = PᵀBP + B0ᵀP + B00.")
    left, right = st.columns([1.1, 1], gap="medium")
    left.html(ui_theme.section("Units"))
    units = ui_tables.editor(left, "ed_units", lambda: e["units"].copy(),
                             num_rows="dynamic")
    n = len(units)
    B = B0 = None
    B00 = 0.0
    if loss == "B-coefficients":
        unit = c[3].selectbox("B units", ["pu", "per MW"], key="ed_bu")
        base = c[4].number_input("on base (MVA)", 1.0, 1e5, e["base"],
                                 key="ed_base", disabled=unit != "pu")
        right.html(ui_theme.section("B-coefficients"))

        def bdef():
            Bm = np.array(e["B"]) if n == 3 else np.zeros((n, n))
            return pd.DataFrame(Bm, columns=[f"B·{j + 1}" for j in range(n)])
        Bt = ui_tables.editor(right, "ed_B", bdef, n)
        b0t = ui_tables.editor(right, "ed_B0", lambda: pd.DataFrame(
            [e["B0"] if n == 3 else [0.0] * n],
            columns=[f"B0·{j + 1}" for j in range(n)]), n)
        B00 = right.number_input("B00", value=e["B00"], format="%.8f", key="ed_b00")
        B, B0 = Bt.to_numpy(float), b0t.to_numpy(float)[0]
        if unit == "pu":
            B, B0, B00 = D.b_from_pu(B, B0, B00, base)
    try:
        r = D.dispatch(units, PD, B, B0, B00, use_limits=lim, tol=1e-6)
    except Exception as ex:
        st.error(f"Cannot dispatch: {ex}")
        return
    if not r["ok"]:
        st.error("No solution: demand (plus losses) is outside the units' "
                 "combined limits, or the iteration did not converge.")
    _kpis([("λ (system incremental cost)", f"{r['lam']:.4f} $/MWh", None),
           ("Losses PL", f"{r['PL']:.4f} MW", None),
           ("Total cost", f"{r['cost']:.2f} $/h", None),
           ("Generation ΣP", f"{r['P'].sum():.3f} MW", f"PD + PL = {PD + r['PL']:.3f}")])
    a, b = st.columns([1.2, 1], gap="medium")
    a.html(ui_theme.section("Optimal dispatch"))
    a.dataframe(r["table"].round(4), hide_index=True)
    b.html(ui_theme.section("λ iterations"))
    b.dataframe(r["its"].round(5), hide_index=True, height=260)


# ------------------------------------------------------ transmission lines
def page_tline(out=None):
    c = st.columns(4, vertical_alignment="bottom")
    model = c[0].segmented_control("Model", TL.MODELS, default="medium (π)",
                                   key="tl_model") or "medium (π)"
    L = c[1].number_input("Length (km)", 0.1, 5000.0, 150.0, key="tl_len")
    lag = c[2].segmented_control("Power factor", ["lagging", "leading"],
                                 default="lagging", key="tl_lag") != "leading"
    pf = c[3].number_input("pf", 0.05, 1.0, 0.85, step=0.01, key="tl_pf")
    d = st.columns(5)
    R = d[0].number_input("R (Ω/km)", 0.0, 10.0, 0.1, format="%.4f", key="tl_r")
    X = d[1].number_input("X (Ω/km)", 0.0, 10.0, 0.5, format="%.4f", key="tl_x")
    B = d[2].number_input("B (µS/km)", 0.0, 100.0, 3.2, format="%.3f", key="tl_b")
    VR = d[3].number_input("V_R (kV, line)", 0.1, 2000.0, 220.0, key="tl_vr")
    PR = d[4].number_input("P_R (MW, 3-phase)", 0.0, 1e5, 150.0, key="tl_pr")
    try:
        r = TL.performance(model, R, X, B, L, VR, PR, pf, lag)
    except Exception as ex:
        st.error(f"Cannot compute: {ex}")
        return
    _kpis([("Sending-end voltage", f"{r['VS_LL']:.3f} kV",
            f"∠{np.degrees(np.angle(r['VS'])):.2f}° (phase)"),
           ("Sending-end current", f"{abs(r['IS']) * 1e3:.2f} A",
            f"∠{np.degrees(np.angle(r['IS'])):.2f}°"),
           ("Voltage regulation", f"{r['reg']:.3f} %", None),
           ("Efficiency", f"{r['eff']:.3f} %", f"loss {r['loss']:.3f} MW")])
    left, right = st.columns(2, gap="medium")
    left.html(ui_theme.section(f"ABCD constants ({model})"))
    left.dataframe(pd.DataFrame({
        "Constant": ["A", "B (Ω)", "C (S)", "D", "AD − BC"],
        "Polar": [pfmt(r["A"], 5), pfmt(r["B"], 4), f"{abs(r['C']):.4e}∠"
                  f"{np.degrees(np.angle(r['C'])):.2f}°", pfmt(r["D"], 5),
                  pfmt(r["check"], 6)]}), hide_index=True)
    rows = [["P_S (MW)", f"{r['SS'].real:.3f}"], ["Q_S (MVAr)", f"{r['SS'].imag:.3f}"],
            ["P_R (MW)", f"{r['SR'].real:.3f}"], ["Q_R (MVAr)", f"{r['SR'].imag:.3f}"]]
    if model == "long":
        rows += [["γ = α + jβ (per km)", cfmt(r["gamma"], 6)],
                 ["Zc (Ω)", pfmt(r["Zc"], 3)], ["SIL (MW)", f"{r['SIL']:.2f}"]]
    right.html(ui_theme.section("Power at both ends"))
    right.dataframe(pd.DataFrame(rows, columns=["Quantity", "Value"]),
                    hide_index=True)
    st.html(ui_theme.section("All three models for the same line"))
    cmp = []
    for m in TL.MODELS:
        q = TL.performance(m, R, X, B, L, VR, PR, pf, lag)
        cmp.append([m, q["VS_LL"], abs(q["IS"]) * 1e3, q["reg"], q["eff"]])
    st.dataframe(pd.DataFrame(cmp, columns=["Model", "V_S (kV)", "I_S (A)",
                                            "Regulation (%)", "Efficiency (%)"])
                 .round(4), hide_index=True)
