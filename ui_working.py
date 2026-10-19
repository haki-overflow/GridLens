"""Worked-solution pages: Ybus matrix, Iterations, Worked answer.

All values come from working.py (same formulas as the solver, with every
intermediate step kept). The case is the one the last study solved
(after any Q-limit bus switching).
"""
import numpy as np
import pandas as pd
import streamlit as st

import ui_theme
import working as W
from solver import METHODS, build_ybus


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
    left.html(ui_theme.section(f"Ybus ({form or 'Rectangular'}, pu)"))
    left.dataframe(W.matrix_text(Y, W.pfmt if form == "Polar" else W.cfmt),
                   width="stretch")
    parts = W.ybus_parts(bus, lines)
    elems = list(dict.fromkeys(parts["Element"]))
    right.html(ui_theme.section("How an element is formed"))
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
        st.html(ui_theme.section("Bus voltages per iteration (|V|∠δ)"))
        st.dataframe(_vtable(tr["V"], tr["dmax"]), hide_index=True, height=360)
        pv = [i for i in range(len(bus)) if bus["Type"].iloc[i] == "PV"]
        if pv:
            st.html(ui_theme.section("Q at PV buses per iteration (pu)"))
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
        a.html(ui_theme.section("B′ (series X only)"))
        a.dataframe(_block(tr["B1"], [f"δ{lab[i]}" for i in tr["ang"]],
                           [f"δ{lab[i]}" for i in tr["ang"]]))
        b.html(ui_theme.section("B″ (−Im Ybus)"))
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
        st.html(ui_theme.section("Corrections per iteration"))
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
    a.html(ui_theme.section(f"Mismatch, iteration {k}"))
    a.dataframe(pd.DataFrame({"": rP + rQ, "Value": np.r_[it["dP"], it["dQ"]]})
                .round(6), hide_index=True)
    a.html(ui_theme.section("Corrections"))
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
            col.html(ui_theme.section(name))
            col.dataframe(_block(M, r_, c_))
    st.html(ui_theme.section("Convergence"))
    st.dataframe(pd.DataFrame({"Iter": [i["k"] for i in tr["its"]],
                               "max mismatch": [f"{i['err']:.3e}" for i in tr["its"]]}),
                 hide_index=True, height=180)


def page_answer(out, conversion=None):
    bus, lines = _case(out)
    _note_qlim(out)
    base = out["base"]
    btab, ftab = W.results_tables(out["res"], out["flows"], bus, base)
    k = int(np.where(bus["Type"].values == "Slack")[0][0])
    sp = btab["Pg (MW)"].iloc[k], btab["Qg (MVAr)"].iloc[k]
    left, right = st.columns([1.25, 1], gap="medium")
    left.html(ui_theme.section("Bus results"))
    left.dataframe(btab, hide_index=True)
    left.markdown(f"**Slack bus {k + 1}:** S = {sp[0]:.3f} + j{sp[1]:.3f} MVA")
    right.html(ui_theme.section("Line flows and losses"))
    right.dataframe(ftab, hide_index=True)
    right.markdown(f"**Total losses:** {out['flows']['Loss_P'].sum() * base:.4f} MW, "
                   f"{out['flows']['Loss_Q'].sum() * base:.4f} MVAr")
    show = st.slider("Iterations written out in full", 1, 5, 2, key="ans_show")
    text = W.answer_text(bus, lines, out["res"], out["flows"], base, out["method"],
                         W.trace_lines(out["method"], bus, lines,
                                       tol=out["tol"], show=show),
                         conversion=conversion)
    st.html(ui_theme.section("Copy as answer"))
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption("Plain text: given data → per unit → Ybus → iterations → "
                   "results. Copy with the icon at the top right of the box.")
        st.download_button("Download .txt", text.encode(), "gridlens_answer.txt",
                           "text/plain", key="ans_dl")
    st.code(text, language=None, height=420)
