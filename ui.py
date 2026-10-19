"""GridLens Streamlit UI helpers and pages, in one file.

Sections (in this order): HTML helpers (banner, badge, section label, status
bar, stylesheet injection) -> editable tables that keep their edits ->
Problem input page -> textbook topic pages (unsymmetrical faults, symmetrical
components, economic dispatch, line parameters) -> worked-solution pages
(Ybus matrix, Iterations, Worked answer). The palette and the figures live in
figures.py; app.py only wires pages together.
"""
import numpy as np
import pandas as pd
import streamlit as st

import topics
import working as W
from figures import CSS_FILE, mpl_style, plotly_style
from solver import METHODS, build_ybus
from working import cfmt, pfmt



# ============================================================================
# HTML helpers
# GridLens Streamlit helpers: the stylesheet injection and the small HTML
# pieces (banner, badge, section label, status bar). The palette and the
# matplotlib / Plotly styles live in figures.py.
# ============================================================================

def banner_html(readouts=()):
    """Header band; readouts is a list of (label, value) or (label, value,
    css class) shown on the right (class "stale" turns the value amber)."""
    read = "".join(f'<div class="{r[2] if len(r) > 2 else ""}"><span>{r[0]}'
                   f"</span>{r[1]}</div>" for r in readouts)
    return ('<div class="gl-banner"><div><div class="gl-title">GRIDLENS</div>'
            '<div class="gl-sub">Steady-state network study &middot; load '
            'flow &middot; N-1 security &middot; voltage stability &middot; '
            f'fault levels</div></div><div class="gl-read">{read}</div></div>')


def section(text):
    """Small section label in a title strip, as in report printouts."""
    return f'<div class="gl-sec">{text}</div>'


def badge(text, tone="ok"):
    if tone not in ("ok", "bad", "warn", "gray"):
        raise ValueError(f"badge tone must be ok/bad/warn/gray, got {tone!r}")
    return f'<span class="gl-badge {tone}">{text}</span>'


def inspector_html(title, rows):
    """Key/value table for the diagram inspector; rows = [(label, value)]."""
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return (f'{section(title)}<div class="gl-insp"><table>{body}</table>'
            '</div>')


def statusbar_html(items):
    """Fixed bottom status bar; items is a list of (label, value) cells and
    the last cell stretches (use it for the message)."""
    cells = "".join(f"<div><b>{k}</b>{v}</div>" for k, v in items)
    return f'<div class="gl-status">{cells}</div>'


def inject():
    """Stylesheet plus the matplotlib / Plotly styles; call once per run."""
    import streamlit as st
    st.html(f"<style>{CSS_FILE.read_text()}</style>")
    mpl_style()
    plotly_style()


# ============================================================================
# Editable tables
# Editable tables whose edits survive leaving the page.
# 
# st.data_editor forgets its edits when its page is not rendered. Here the
# table lives in st.session_state[f"tbl_{name}"]; every edit is folded into
# it by an on_change callback and the editor restarts from the new table
# under a fresh key.
# ============================================================================

def apply_delta(df, delta):
    """Apply a data_editor delta (edited / added / deleted rows) to df."""
    df = df.copy()
    for r, cols in delta.get("edited_rows", {}).items():
        for c, v in cols.items():
            df.loc[df.index[int(r)], c] = v
    if delta.get("deleted_rows"):
        df = df.drop(df.index[delta["deleted_rows"]])
    if delta.get("added_rows"):
        df = pd.concat([df, pd.DataFrame(delta["added_rows"])],
                       ignore_index=True)
    return df.reset_index(drop=True)


def _commit(name, key):
    ss = st.session_state
    ss[f"tbl_{name}"] = apply_delta(ss[f"tbl_{name}"], ss[key])
    ss[f"tbl_v_{name}"] = ss.get(f"tbl_v_{name}", 0) + 1


def table(name, default, seed=None):
    """Current table `name`; (re)seeded from default() when the seed value
    changes (e.g. a different case)."""
    ss = st.session_state
    if f"tbl_{name}" not in ss or ss.get(f"tbl_seed_{name}") != seed:
        ss[f"tbl_{name}"] = default().reset_index(drop=True)
        ss[f"tbl_seed_{name}"] = seed
        ss[f"tbl_v_{name}"] = ss.get(f"tbl_v_{name}", 0) + 1
    return ss[f"tbl_{name}"]


def editor(where, name, default, seed=None, **kw):
    """Persistent data_editor; returns the current table."""
    df = table(name, default, seed)
    key = f"tbl_ed_{name}_{st.session_state.get(f'tbl_v_{name}', 0)}"
    kw.setdefault("hide_index", True)
    where.data_editor(df, key=key, on_change=_commit, args=(name, key), **kw)
    return st.session_state[f"tbl_{name}"]


# ============================================================================
# Problem input page
# Problem input page: textbook-style data in real units -> per unit.
# 
# The user types the data the way a textbook question gives it (MVA, kV,
# ohms, ohms/km, µS, MVAr, MW); topics.to_pu converts it and every converted
# value is listed so it can be checked against a hand calculation. "Load
# into study" hands the per-unit tables to the main case.
# ============================================================================

TABLES = ("buses", "lines", "trafos")


def _init():
    ss = st.session_state
    for k in ("sbase", "ref_bus", "ref_kv"):
        ss.setdefault(f"prob_{k}", topics.UNITS_EXAMPLE[k])


def _editor(where, name, column_config):
    editor(where, f"prob_{name}",
                     lambda: topics.UNITS_EXAMPLE[name].copy(), num_rows="dynamic",
                     column_config=column_config)


def page_problem(load):
    """load(bus_pu, lines_pu, sbase) puts the converted case into the study."""
    _init()
    ss = st.session_state
    st.caption("Enter the data as the question gives it. Buses are numbered "
               "by row. Lines join buses of one voltage zone; transformers "
               "start a new zone (base kV scales with their rated ratio).")
    c = st.columns([1, 1, 1, 1.4], vertical_alignment="bottom")
    ss["prob_sbase"] = c[0].number_input("System base (MVA)", 1.0, 1e5,
                                         float(ss["prob_sbase"]), key="pi_sb")
    ss["prob_ref_bus"] = int(c[1].number_input(
        "Reference bus", 1, 999, int(ss["prob_ref_bus"]), key="pi_rb",
        help="Bus whose base kV is given."))
    ss["prob_ref_kv"] = c[2].number_input("Its base kV", 0.1, 2000.0,
                                          float(ss["prob_ref_kv"]), key="pi_kv")

    tb, tl, tt = st.tabs(["Buses", "Lines", "Transformers"])
    _editor(tb, "buses", {
        "Type": st.column_config.SelectboxColumn(options=["Slack", "PV", "PQ"]),
        "V": st.column_config.NumberColumn("V (pu)", format="%.4f"),
        "Pg": st.column_config.NumberColumn("Pg (MW)"),
        "Qg": st.column_config.NumberColumn("Qg (MVAr)"),
        "Pd": st.column_config.NumberColumn("Pd (MW)"),
        "Qd": st.column_config.NumberColumn("Qd (MVAr)"),
        "Qmin": st.column_config.NumberColumn("Qmin (MVAr)"),
        "Qmax": st.column_config.NumberColumn("Qmax (MVAr)"),
        "Shunt": st.column_config.NumberColumn(
            "Shunt (MVAr)", help="At 1 pu voltage; + capacitive.")})
    _editor(tl, "lines", {
        "From": st.column_config.NumberColumn(step=1),
        "To": st.column_config.NumberColumn(step=1),
        "Z unit": st.column_config.SelectboxColumn(options=list(topics.Z_UNITS)),
        "B unit": st.column_config.SelectboxColumn(
            options=list(topics.B_UNITS),
            help="µS total, µS/km (× Length), or MVAr total charging."),
        "Length": st.column_config.NumberColumn("Length (km)")})
    _editor(tt, "trafos", {
        "From": st.column_config.NumberColumn(step=1, help="Tap side."),
        "To": st.column_config.NumberColumn(step=1),
        "R": st.column_config.NumberColumn("R (pu own)"),
        "X": st.column_config.NumberColumn("X (pu own)"),
        "Tap": st.column_config.NumberColumn(
            help="Off-nominal ratio at the From side, 1 = nominal.")})

    try:
        t = {k: ss[f"tbl_prob_{k}"] for k in TABLES}
        r = topics.to_pu(ss["prob_sbase"], ss["prob_ref_bus"], ss["prob_ref_kv"],
                        t["buses"], t["lines"], t["trafos"])
    except Exception as e:
        st.error(f"Cannot convert: {e}")
        return
    c[3].button("Load into study", type="primary", key="pi_load",
                on_click=load, args=(r["bus"], r["lines"], ss["prob_sbase"],
                                     dict(zones=r["zones"], table=r["table"])),
                help="Replace the Dashboard case with this per-unit data.")

    st.html(section("Check your conversion"))
    t_zone, t_pu, t_case = st.tabs(["Base values per zone", "Per-unit conversion",
                                    "Per-unit case (what the solver gets)"])
    with t_zone:
        st.dataframe(r["zones"].round(4), hide_index=True)
        if (r["lines"]["Tap"] - 1).abs().max() > 1e-9:
            st.caption("Off-nominal taps present: switch Mode to Advanced and "
                       "turn on Transformer taps so the study uses them.")
        if (r["bus"]["Qmax"] < 99).any() or (r["bus"]["Qmin"] > -99).any():
            st.caption("Q limits given: Advanced mode → Generator Q limits "
                       "enforces them.")
    with t_pu:
        st.dataframe(r["table"].round(6), hide_index=True)
    with t_case:
        a, b = st.columns([1.3, 1])
        a.dataframe(r["bus"].round(6), hide_index=True)
        b.dataframe(r["lines"].round(6), hide_index=True)


# ============================================================================
# Textbook topic pages
# Textbook topic pages: unsymmetrical faults, symmetrical components,
# economic dispatch and transmission line parameters. The math lives in
# seqfaults.py, symcomp.py, dispatch.py and tline.py.
# ============================================================================


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
    kind = c[0].segmented_control("Fault type", topics.TYPES, default="SLG",
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

    g0, b0 = topics.seed_tables(bus, lines)
    kv0 = bus["kV"].astype(float) if "kV" in bus else pd.Series([33.0] * n)
    kv_default = lambda: pd.DataFrame({"Bus": np.arange(1, n + 1),
                                       "kV": kv0.values})
    if st.button("Edit sequence data", key="sf_edit"):
        _dlg_seqdata(g0, b0, kv_default, seed)
    gens = table("sf_gens", lambda: g0, seed)
    br = table("sf_br", lambda: b0, seed)
    kvt = table("sf_kv", kv_default, seed)
    try:
        kv = kvt["kV"].astype(float).to_numpy()
        tab = topics.fault_table(kind, gens, br, vf, zf, out["base"], kv)
        r = topics.solve_fault(kind, k, gens, br, vf, zf, out["base"], kv)
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
        editor(t1, "sf_gens", lambda: g0, seed, num_rows="dynamic",
                         column_config={"Conn": st.column_config.SelectboxColumn(options=CONN)})
    with t2:
        editor(t2, "sf_br", lambda: b0, seed, column_config={
            "Kind": st.column_config.SelectboxColumn(options=["line", "transformer"]),
            "Conn From": st.column_config.SelectboxColumn(options=CONN),
            "Conn To": st.column_config.SelectboxColumn(options=CONN)})
    with t3:
        editor(t3, "sf_kv", kv_default, seed, disabled=["Bus"])
    if st.button("Apply and recalculate", type="primary", key="sf_apply"):
        st.rerun()


# ------------------------------------------------------ symmetrical components
def _phasors(prefix, key, defaults):
    vals = []
    cols = st.columns(3)
    for col, (name, (m, d)) in zip(cols, zip(prefix, defaults)):
        mm = col.number_input(f"|{name}|", value=m, key=f"{key}_{name}_m", format="%.4f")
        dd = col.number_input(f"∠{name} (°)", value=d, key=f"{key}_{name}_a", format="%.2f")
        vals.append(topics.polar(mm, dd))
    return np.array(vals)


def page_symcomp(out=None):
    st.caption("a = 1∠120° = −0.5 + j0.866,  a² = 1∠240°,  1 + a + a² = 0.  "
               "[Va Vb Vc]ᵀ = A [V0 V1 V2]ᵀ,  [V0 V1 V2]ᵀ = A⁻¹ [Va Vb Vc]ᵀ.")
    left, right = st.columns(2, gap="large")
    with left:
        st.html(section("Phase → sequence"))
        abc = _phasors(["Va", "Vb", "Vc"], "sc_p",
                       [(1.0, 0.0), (0.8, -110.0), (1.1, 125.0)])
        s = topics.to_sequence(abc)
        st.dataframe(pd.DataFrame({"Component": ["V0 (zero)", "V1 (positive)",
                                                 "V2 (negative)"],
                                   "Polar": [pfmt(v) for v in s],
                                   "Rectangular": [cfmt(v) for v in s]}),
                     hide_index=True)
        st.caption(f"Unbalance V2/V1 = {abs(s[2]) / max(abs(s[1]), 1e-12) * 100:.2f} %")
    with right:
        st.html(section("Sequence → phase"))
        s2 = _phasors(["V0", "V1", "V2"], "sc_s",
                      [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0)])
        p = topics.to_phase(s2)
        st.dataframe(pd.DataFrame({"Phase": ["Va", "Vb", "Vc"],
                                   "Polar": [pfmt(v) for v in p],
                                   "Rectangular": [cfmt(v) for v in p]}),
                     hide_index=True)
    st.html(section("Operator matrices"))
    a_, b_ = st.columns(2, gap="large")
    lab = ["0", "1", "2"]
    a_.caption("A (sequence → phase)")
    a_.dataframe(pd.DataFrame([[pfmt(v, 3) for v in r] for r in topics.A],
                              index=["a", "b", "c"], columns=lab))
    b_.caption("A⁻¹ (phase → sequence)")
    b_.dataframe(pd.DataFrame([[pfmt(v, 4) for v in r] for r in topics.A_INV],
                              index=lab, columns=["a", "b", "c"]))


# --------------------------------------------------------- economic dispatch
def page_dispatch(out=None):
    e = topics.DISPATCH_EXAMPLE
    c = st.columns([0.9, 1.3, 1.3, 0.9, 1.6], vertical_alignment="bottom")
    PD = c[0].number_input("Demand PD (MW)", 0.0, 1e6, e["PD"], key="ed_pd")
    loss = c[1].segmented_control("Losses", ["None", "B-coefficients"],
                                  default="B-coefficients", key="ed_loss") or "None"
    lim = c[2].segmented_control("Unit limits", ["On", "Off"], default="On",
                                 key="ed_lim") == "On"
    st.caption("Cost C = a + bP + cP² ($/h), P in MW. Losses PL = PᵀBP + B0ᵀP + B00.")
    left, right = st.columns([1.1, 1], gap="medium")
    left.html(section("Units"))
    units = editor(left, "ed_units", lambda: e["units"].copy(),
                             num_rows="dynamic")
    n = len(units)
    B = B0 = None
    B00 = 0.0
    if loss == "B-coefficients":
        unit = c[3].selectbox("B units", ["pu", "per MW"], key="ed_bu")
        base = c[4].number_input("on base (MVA)", 1.0, 1e5, e["base"],
                                 key="ed_base", disabled=unit != "pu")
        right.html(section("B-coefficients"))

        def bdef():
            Bm = np.array(e["B"]) if n == 3 else np.zeros((n, n))
            return pd.DataFrame(Bm, columns=[f"B·{j + 1}" for j in range(n)])
        Bt = editor(right, "ed_B", bdef, n)
        b0t = editor(right, "ed_B0", lambda: pd.DataFrame(
            [e["B0"] if n == 3 else [0.0] * n],
            columns=[f"B0·{j + 1}" for j in range(n)]), n)
        B00 = right.number_input("B00", value=e["B00"], format="%.8f", key="ed_b00")
        B, B0 = Bt.to_numpy(float), b0t.to_numpy(float)[0]
        if unit == "pu":
            B, B0, B00 = topics.b_from_pu(B, B0, B00, base)
    try:
        r = topics.dispatch(units, PD, B, B0, B00, use_limits=lim, tol=1e-6)
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
    a.html(section("Optimal dispatch"))
    a.dataframe(r["table"].round(4), hide_index=True)
    b.html(section("λ iterations"))
    b.dataframe(r["its"].round(5), hide_index=True, height=260)


# ------------------------------------------------------ transmission lines
def page_tline(out=None):
    c = st.columns(4, vertical_alignment="bottom")
    model = c[0].segmented_control("Model", topics.MODELS, default="medium (π)",
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
        r = topics.performance(model, R, X, B, L, VR, PR, pf, lag)
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
    left.html(section(f"ABCD constants ({model})"))
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
    right.html(section("Power at both ends"))
    right.dataframe(pd.DataFrame(rows, columns=["Quantity", "Value"]),
                    hide_index=True)
    st.html(section("All three models for the same line"))
    cmp = []
    for m in topics.MODELS:
        q = topics.performance(m, R, X, B, L, VR, PR, pf, lag)
        cmp.append([m, q["VS_LL"], abs(q["IS"]) * 1e3, q["reg"], q["eff"]])
    st.dataframe(pd.DataFrame(cmp, columns=["Model", "V_S (kV)", "I_S (A)",
                                            "Regulation (%)", "Efficiency (%)"])
                 .round(4), hide_index=True)


# ============================================================================
# Worked-solution pages
# Worked-solution pages: Ybus matrix, Iterations, Worked answer.
# 
# All values come from working.py (same formulas as the solver, with every
# intermediate step kept). The case is the one the last study solved
# (after any Q-limit bus switching).
# ============================================================================

def _case(out):
    return out.get("b_lf", out["b"]), out["l"]


def _note_qlim(out):
    if out.get("qlog"):
        st.caption("Generator Q limits switched bus types; the working uses "
                   "the final bus types.")


def page_ybus(out):
    bus, lines = _case(out)
    Y = build_ybus(len(bus), lines, bus)
    st.caption("Ybus = Σ of the series admittance y = 1/(R + jX) of every "
               "branch, its charging jB/2 at both ends and the bus shunts. An "
               "off-nominal tap a on the From side gives y/a² there and -y/a "
               "off the diagonal.")
    form = st.segmented_control("Form", ["Rectangular", "Polar"],
                                default="Rectangular", key="yb_form")
    left, right = st.columns([1.7, 1], gap="medium")
    left.html(section(f"Ybus ({form or 'Rectangular'}, pu)"))
    left.dataframe(W.matrix_text(Y, W.pfmt if form == "Polar" else W.cfmt),
                   width="stretch")
    parts = W.ybus_parts(bus, lines)
    elems = list(dict.fromkeys(parts["Element"]))
    right.html(section("How an element is formed"))
    el = right.selectbox("Element", elems, key="yb_el")
    p = parts[parts["Element"] == el]
    right.dataframe(pd.DataFrame({"Source": p["Source"],
                                  "Value": [W.cfmt(v, 5) for v in p["Value"]]}),
                    hide_index=True, width="stretch")
    i, j = int(p["i"].iloc[0]), int(p["j"].iloc[0])
    right.markdown(f"**{el} = {W.cfmt(Y[i, j], 5)} = {W.pfmt(Y[i, j], 5)}**")


def _vtable(V_hist, dmax):
    rows = []
    for k, V in enumerate(V_hist):
        r = {"Iter": k}
        r.update({f"V{i + 1}": W.pfmt(v) for i, v in enumerate(V)})
        r["max |ΔV|"] = f"{dmax[k - 1]:.2e}" if k else "-"
        rows.append(r)
    return pd.DataFrame(rows)


def _block(M, rows, cols):
    return pd.DataFrame(M, index=rows, columns=cols).round(5)


def page_iterations(out):
    bus, lines = _case(out)
    _note_qlim(out)
    c = st.columns([1.3, 1, 1, 2], vertical_alignment="bottom")
    method = c[0].selectbox("Method", METHODS, index=METHODS.index(out["method"]),
                            key="it_method")
    tol = c[1].number_input("Tolerance", 1e-12, 1e-2, 1e-6 if method ==
                            "Gauss-Seidel" else 1e-8, format="%g", key=f"it_tol_{method}")
    lab = [str(i + 1) for i in range(len(bus))]
    if method == "Gauss-Seidel":
        alpha = c[2].number_input("Acceleration α", 1.0, 2.0, 1.0, step=0.1,
                                  key="it_alpha",
                                  help="V ← V + α(Vcalc − V); 1.0 = plain GS.")
        tr = W.gauss_seidel_trace(bus, lines, alpha, tol, 2000)
        c[3].caption(f"{'Converged' if tr['ok'] else 'Not converged'} in "
                     f"{len(tr['dmax'])} iterations. PV buses: Q recomputed each "
                     "sweep, |V| held at the setpoint.")
        st.html(section("Bus voltages per iteration (|V|∠δ)"))
        st.dataframe(_vtable(tr["V"], tr["dmax"]), hide_index=True, height=360)
        pv = [i for i in range(len(bus)) if bus["Type"].iloc[i] == "PV"]
        if pv:
            st.html(section("Q at PV buses per iteration (pu)"))
            st.dataframe(pd.DataFrame({f"Q{i + 1}": [q[i] for q in tr["Q"][1:]]
                                       for i in pv}).round(5)
                         .rename_axis("Iter").reset_index()
                         .assign(Iter=lambda d: d["Iter"] + 1),
                         hide_index=True, height=200)
        return
    if method == "Fast Decoupled":
        tr = W.fast_decoupled_trace(bus, lines, tol)
        c[3].caption(f"{'Converged' if tr['ok'] else 'Not converged'} after "
                     f"{len(tr['its']) - 1} iterations.")
        a, b = st.columns(2, gap="medium")
        a.html(section("B′ (series X only)"))
        a.dataframe(_block(tr["B1"], [f"δ{lab[i]}" for i in tr["ang"]],
                           [f"δ{lab[i]}" for i in tr["ang"]]))
        b.html(section("B″ (−Im Ybus)"))
        b.dataframe(_block(tr["B2"], [f"V{lab[i]}" for i in tr["mag"]],
                           [f"V{lab[i]}" for i in tr["mag"]]))
        rows = []
        for it in tr["its"]:
            r = {"Iter": it["k"], "max mismatch": f"{it['err']:.2e}"}
            if not it["done"]:
                r.update({f"Δδ{lab[i]} (°)": round(np.degrees(d), 5)
                          for i, d in zip(tr["ang"], it["dth"])})
                r.update({f"ΔV{lab[i]}": round(d, 6)
                          for i, d in zip(tr["mag"], it["dV"])})
            rows.append(r)
        st.html(section("Corrections per iteration"))
        st.dataframe(pd.DataFrame(rows), hide_index=True, height=300)
        return
    tr = W.newton_trace(bus, lines, tol)
    n_it = len([i for i in tr["its"] if not i["done"]])
    c[3].caption(f"{'Converged' if tr['ok'] else 'Not converged'} after {n_it} "
                 "iterations. ΔP = Psp − Pcalc, J·[Δδ; Δ|V|] = [ΔP; ΔQ].")
    if not n_it:
        st.info("The start point already meets the tolerance.")
        return
    k = c[2].selectbox("Show iteration", list(range(1, n_it + 1)), key="it_k")
    it = tr["its"][k - 1]
    rP = [f"P{lab[i]}" for i in tr["ang"]]
    rQ = [f"Q{lab[i]}" for i in tr["mag"]]
    cd = [f"δ{lab[i]}" for i in tr["ang"]]
    cv = [f"|V{lab[i]}|" for i in tr["mag"]]
    a, b = st.columns([1, 2.4], gap="medium")
    a.html(section(f"Mismatch, iteration {k}"))
    a.dataframe(pd.DataFrame({"": rP + rQ, "Value": np.r_[it["dP"], it["dQ"]]})
                .round(6), hide_index=True)
    a.html(section("Corrections"))
    a.dataframe(pd.DataFrame({"": [f"Δ{x}" for x in cd + cv],
                              "Value": np.r_[np.degrees(it["dth"]), it["dV"]]})
                .round(6), hide_index=True)
    a.caption("Δδ in degrees, Δ|V| in pu.")
    with b:
        g = st.columns(2, gap="small")
        for (name, M, r_, c_), col in zip(
                (("J1 = ∂P/∂δ", it["J1"], rP, cd), ("J2 = ∂P/∂|V|", it["J2"], rP, cv),
                 ("J3 = ∂Q/∂δ", it["J3"], rQ, cd), ("J4 = ∂Q/∂|V|", it["J4"], rQ, cv)),
                (g[0], g[1], g[0], g[1])):
            col.html(section(name))
            col.dataframe(_block(M, r_, c_))
    st.html(section("Convergence"))
    st.caption("The last row is the convergence check: the mismatch is "
               "below tolerance, so no update is made.")
    st.dataframe(pd.DataFrame({"Iter": [("check" if i.get("done") else str(i["k"]))
                                        for i in tr["its"]],
                               "max mismatch": [f"{i['err']:.3e}" for i in tr["its"]]}),
                 hide_index=True, height=180)


def page_answer(out, conversion=None):
    bus, lines = _case(out)
    _note_qlim(out)
    base = out["base"]
    btab, ftab = W.results_tables(out["res"], out["flows"], bus, base)
    k = int(np.where(bus["Type"].values == "Slack")[0][0])
    sp = btab["Pg (MW)"].iloc[k], btab["Qg (MVAr)"].iloc[k]
    st.html(f'<div class="gl-ok">Slack bus {k + 1}: S = {sp[0]:.3f} + '
            f'j{sp[1]:.3f} MVA &nbsp;&middot;&nbsp; total losses '
            f'{out["flows"]["Loss_P"].sum() * base:.4f} MW, '
            f'{out["flows"]["Loss_Q"].sum() * base:.4f} MVAr</div>')
    srow = st.columns([3, 1], vertical_alignment="bottom")
    show = srow[0].slider("Iterations written out in full", 1, 5, 2,
                          key="ans_show")
    text = W.answer_text(bus, lines, out["res"], out["flows"], base, out["method"],
                         W.trace_lines(out["method"], bus, lines,
                                       tol=out["tol"], show=show),
                         conversion=conversion)
    srow[1].download_button("Download .txt", text.encode(),
                            "gridlens_answer.txt", "text/plain",
                            key="ans_dl", width="stretch")
    t_res, t_flow, t_text = st.tabs(["Bus results", "Line flows and losses",
                                     "Full written answer"])
    with t_res:
        st.dataframe(btab, hide_index=True)
    with t_flow:
        st.dataframe(ftab, hide_index=True)
    with t_text:
        st.caption("Copy with the icon at the top right of the box.")
        st.code(text, language=None, height=520)
