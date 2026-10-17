"""N-bus load flow solver: Newton-Raphson, Fast Decoupled, Gauss-Seidel.
Optional plain-English report written by a local model (Gemma) via LM Studio.

Run:   pip install streamlit numpy pandas requests
       streamlit run app.py
AI:    LM Studio -> Developer tab -> load Gemma -> Start Server (port 1234).

All quantities are per unit. Line B = total line charging susceptance.
The solver does all the math; the LLM only explains the results.
"""
import pandas as pd

from ai_report import ai_report, lm_models
from cases import CASES
from plotting import draw_network
from solver import METHODS, solve_loadflow
from studies import contingency, fault_analysis


# -------------------------------------------------------------------- GUI
def main():
    import streamlit as st
    st.set_page_config(page_title="Power System Analysis", layout="wide")
    st.title("Power System Analysis: Load Flow, N-1 and Fault Study")
    st.caption("Any number of buses. Edit tables or pick a preset. Per unit. "
               "Line Tap = off-nominal tap ratio (1 = none); Bus Bs = shunt susceptance.")

    with st.sidebar:
        st.header("Settings")
        case = st.selectbox("Case", list(CASES))
        method = st.selectbox("Method", METHODS)
        base = st.number_input("Base MVA", value=100.0)
        vmin = st.number_input("Min voltage (pu)", value=0.95)
        vmax = st.number_input("Max voltage (pu)", value=1.10)

    st.subheader("Bus data")
    bus = st.data_editor(CASES[case][0], num_rows="dynamic", key=f"bus_{case}",
                         column_config={"Type": st.column_config.SelectboxColumn(
                             options=["Slack", "PV", "PQ"])})
    st.subheader("Line data")
    lines = st.data_editor(CASES[case][1], num_rows="dynamic", key=f"lines_{case}")

    if st.button("Solve", type="primary"):
        try:
            b = bus.dropna(subset=["Type"]).fillna(0).reset_index(drop=True)
            l = lines.dropna(subset=["From", "To"]).fillna(0).reset_index(drop=True)
            res, flows, ok, hist = solve_loadflow(b, l, method)
            cmp = []
            for m in METHODS:
                r2, f2, ok2, h2 = solve_loadflow(b, l, m)
                cmp.append([m, ok2, len(h2) - 1, round(f2["Loss_P"].sum() * base, 4),
                            round(r2["V (pu)"].min(), 4)])
            n1 = contingency(b, l, vmin, vmax)
            loss = flows["Loss_P"].sum() * base
            st.session_state["out"] = dict(
                res=res, flows=flows, ok=ok, its=len(hist) - 1, method=method, b=b, l=l,
                cmp=pd.DataFrame(cmp, columns=["Method", "Converged", "Iterations",
                                               "Loss (MW)", "Min V (pu)"]),
                n1=n1, loss=loss, vmin=vmin, vmax=vmax, base=base,
                summary=(f"Method: {method}, base {base} MVA\n"
                         + res.round(4).to_string(index=False)
                         + f"\nTotal real loss: {loss:.2f} MW. Voltage limits: {vmin}-{vmax} pu."
                         + "\nWorst N-1 line outages (worst first):\n"
                         + n1.head(3).to_string(index=False)))
        except Exception as e:
            st.session_state.pop("out", None)
            st.error(f"Error: {e}")

    out = st.session_state.get("out")
    if not out:
        return
    res = out["res"]
    (st.success if out["ok"] else st.error)(
        f"{out['method']} " + (f"converged in {out['its']} iterations" if out["ok"]
                               else "did not converge"))
    c1, c2 = st.columns(2)
    c1.metric("Total real loss", f"{out['loss']:.2f} MW")
    bad = res[(res["V (pu)"] < out["vmin"]) | (res["V (pu)"] > out["vmax"])]
    if len(bad):
        c2.warning("Voltage violations at bus: " + ", ".join(map(str, bad["Bus"])))
    else:
        c2.success("All bus voltages within limits")

    t1, t2, t3, t4, t5 = st.tabs(["Load flow", "Network diagram", "N-1 contingency",
                                  "Short circuit", "AI report"])
    with t1:
        st.subheader("Bus results")
        st.dataframe(res.round(4), hide_index=True)
        st.subheader("Line flows (pu)")
        st.dataframe(out["flows"].round(4), hide_index=True)
        st.subheader("Voltage profile")
        st.bar_chart(res.set_index("Bus")["V (pu)"])
        st.subheader("Method comparison")
        st.dataframe(out["cmp"], hide_index=True)
    with t2:
        st.pyplot(draw_network(res, out["l"], out["vmin"], out["vmax"]))
    with t3:
        st.caption("Each line removed in turn and the case re-solved. Worst first.")
        st.dataframe(out["n1"], hide_index=True)
    with t4:
        st.caption("Symmetrical 3-phase fault. Loads neglected; generators modelled as Xd''.")
        k1, k2, k3 = st.columns(3)
        xd = k1.number_input("Generator Xd'' (pu)", value=0.2, min_value=0.001)
        zf = k2.number_input("Fault impedance Zf (pu)", value=0.0, min_value=0.0)
        kv = k3.number_input("Base kV (for kA)", value=33.0, min_value=0.1)
        try:
            sc, Z, V0, If = fault_analysis(out["b"], out["l"], res, xd, zf, out["base"], kv)
            st.dataframe(sc.round(4), hide_index=True)
            fb = st.selectbox("Show post-fault voltages for a fault at bus", sc["Bus"])
            vp = abs(V0 - Z[:, fb - 1] * If[fb - 1])
            st.bar_chart(pd.Series(vp, index=sc["Bus"], name="Post-fault |V| (pu)"))
        except Exception as e:
            st.error(f"Fault analysis failed: {e}")
    with t5:
        st.caption("Local Gemma via LM Studio explains the results; it does no math.")
        models = lm_models()
        if models:
            gi = next((i for i, m in enumerate(models) if "gemma" in m.lower()), 0)
            model = st.selectbox("Loaded model", models, index=gi)
        else:
            model = st.text_input("Model id (LM Studio server not detected)")
        if st.button("Generate report") and model:
            try:
                with st.spinner("Gemma is writing..."):
                    st.write(ai_report(out["summary"], model))
            except Exception as e:
                st.error(f"LM Studio not reachable: {e}")


if __name__ == "__main__":
    main()
