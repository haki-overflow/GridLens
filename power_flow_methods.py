# """N-bus load flow solver: Newton-Raphson, Fast Decoupled, Gauss-Seidel.
# Optional plain-English report written by a local model (Gemma) via LM Studio.

# Run:   pip install streamlit numpy pandas requests
#        streamlit run loadflow_app.py
# AI:    LM Studio -> Developer tab -> load Gemma -> Start Server (port 1234).

# All quantities are per unit. Line B = total line charging susceptance.
# The solver does all the math; the LLM only explains the results.
# """
# import numpy as np
# import pandas as pd

# METHODS = ["Newton-Raphson", "Fast Decoupled", "Gauss-Seidel"]
# LMSTUDIO_URL = "http://127.0.0.1:1234/v1"


# # ----------------------------------------------------------------- solver
# def build_ybus(n, lines, bus=None):
#     """Ybus with optional off-nominal taps (line col 'Tap') and bus shunts (bus col 'Bs')."""
#     Y = np.zeros((n, n), complex)
#     for _, l in lines.iterrows():
#         i, j = int(l["From"]) - 1, int(l["To"]) - 1
#         a = l["Tap"] if "Tap" in l and l["Tap"] > 0 else 1.0
#         y, b = 1 / complex(l["R"], l["X"]), 1j * l["B"] / 2
#         Y[i, i] += y / a**2 + b
#         Y[j, j] += y + b
#         Y[i, j] -= y / a
#         Y[j, i] -= y / a
#     if bus is not None and "Bs" in bus:
#         Y[np.diag_indices(n)] += 1j * bus["Bs"].fillna(0).values
#     return Y


# def injections(Y, V, th):
#     Vc = V * np.exp(1j * th)
#     return Vc * np.conj(Y @ Vc)


# def newton_raphson(Y, V0, th0, Psp, Qsp, ang, mag, tol, max_iter=30):
#     def unpack(x):
#         th, V = th0.copy(), V0.copy()
#         th[ang] = x[: len(ang)]
#         V[mag] = x[len(ang):]
#         return th, V

#     def mismatch(x):
#         S = injections(Y, *unpack(x)[::-1])
#         return np.r_[(S.real - Psp)[ang], (S.imag - Qsp)[mag]]

#     x = np.r_[th0[ang], V0[mag]]
#     hist = []
#     for _ in range(max_iter):
#         f = mismatch(x)
#         hist.append(abs(f).max())
#         if hist[-1] < tol:
#             return *unpack(x), True, hist
#         J = np.zeros((len(x), len(x)))
#         for c in range(len(x)):  # central-difference Jacobian
#             d = np.zeros(len(x))
#             d[c] = 1e-6
#             J[:, c] = (mismatch(x + d) - mismatch(x - d)) / 2e-6
#         x = x - np.linalg.solve(J, f)
#     return *unpack(x), False, hist


# def fast_decoupled(Y, lines, V0, th0, Psp, Qsp, ang, mag, tol, max_iter=200):
#     """XB version: B' from series X only, B'' from the full Ybus."""
#     n = len(V0)
#     Bp = np.zeros((n, n))
#     for _, l in lines.iterrows():
#         i, j = int(l["From"]) - 1, int(l["To"]) - 1
#         b = 1 / l["X"]
#         Bp[i, i] += b
#         Bp[j, j] += b
#         Bp[i, j] -= b
#         Bp[j, i] -= b
#     B1 = Bp[np.ix_(ang, ang)]
#     B2 = -Y.imag[np.ix_(mag, mag)]
#     th, V = th0.copy(), V0.copy()
#     hist = []
#     for _ in range(max_iter):
#         S = injections(Y, V, th)
#         dP, dQ = (Psp - S.real)[ang], (Qsp - S.imag)[mag]
#         err = max(abs(dP).max(initial=0), abs(dQ).max(initial=0))
#         hist.append(err)
#         if err < tol:
#             return th, V, True, hist
#         th[ang] += np.linalg.solve(B1, dP / V[ang])
#         if len(mag):
#             dQ = (Qsp - injections(Y, V, th).imag)[mag]
#             V[mag] += np.linalg.solve(B2, dQ / V[mag])
#     return th, V, False, hist


# def gauss_seidel(Y, V0, th0, t, Psp, Qsp, tol=1e-6, max_iter=5000):
#     """PV buses: Q is recomputed each sweep and |V| is held at the setpoint."""
#     V = V0 * np.exp(1j * th0)
#     hist = [float("nan")]  # so len(hist) - 1 = number of sweeps
#     for _ in range(max_iter):
#         dmax = 0.0
#         for i in range(len(V)):
#             if t[i] == "Slack":
#                 continue
#             s = Y[i] @ V - Y[i, i] * V[i]
#             Qc = -(np.conj(V[i]) * (Y[i] @ V)).imag if t[i] == "PV" else Qsp[i]
#             new = ((Psp[i] - 1j * Qc) / np.conj(V[i]) - s) / Y[i, i]
#             if t[i] == "PV":
#                 new = V0[i] * new / abs(new)
#             dmax = max(dmax, abs(new - V[i]))
#             V[i] = new
#         hist.append(dmax)
#         if dmax < tol:
#             return np.angle(V), np.abs(V), True, hist
#     return np.angle(V), np.abs(V), False, hist


# def solve_loadflow(bus, lines, method="Newton-Raphson", tol=1e-8):
#     n = len(bus)
#     t = bus["Type"].values
#     if (t == "Slack").sum() != 1:
#         raise ValueError("Exactly one Slack bus is required.")
#     if not lines[["From", "To"]].isin(range(1, n + 1)).all().all():
#         raise ValueError("Line From/To must be bus numbers 1..N.")
#     Y = build_ybus(n, lines, bus)
#     V0 = bus["V"].astype(float).values.copy()
#     V0[t == "PQ"] = 1.0  # flat start
#     th0 = np.zeros(n)
#     Psp = (bus["Pg"] - bus["Pd"]).astype(float).values
#     Qsp = (bus["Qg"] - bus["Qd"]).astype(float).values
#     ang = np.where(t != "Slack")[0]
#     mag = np.where(t == "PQ")[0]

#     if method == "Fast Decoupled":
#         th, V, ok, hist = fast_decoupled(Y, lines, V0, th0, Psp, Qsp, ang, mag, tol)
#     elif method == "Gauss-Seidel":
#         th, V, ok, hist = gauss_seidel(Y, V0, th0, t, Psp, Qsp)
#     else:
#         th, V, ok, hist = newton_raphson(Y, V0, th0, Psp, Qsp, ang, mag, tol)

#     Vc = V * np.exp(1j * th)
#     S = Vc * np.conj(Y @ Vc)
#     rows = []
#     for _, l in lines.iterrows():
#         i, j = int(l["From"]) - 1, int(l["To"]) - 1
#         y, b = 1 / complex(l["R"], l["X"]), 1j * l["B"] / 2
#         a = l["Tap"] if "Tap" in l and l["Tap"] > 0 else 1.0
#         Sij = Vc[i] * np.conj((Vc[i] / a**2 - Vc[j] / a) * y + Vc[i] * b)
#         Sji = Vc[j] * np.conj((Vc[j] - Vc[i] / a) * y + Vc[j] * b)
#         L = Sij + Sji
#         rows.append([i + 1, j + 1, Sij.real, Sij.imag, Sji.real, Sji.imag,
#                      L.real, L.imag])
#     flows = pd.DataFrame(rows, columns=["From", "To", "P_ij", "Q_ij", "P_ji",
#                                         "Q_ji", "Loss_P", "Loss_Q"])
#     res = pd.DataFrame({"Bus": np.arange(1, n + 1), "V (pu)": V,
#                         "Angle (deg)": np.degrees(th),
#                         "P_inj": S.real, "Q_inj": S.imag})
#     return res, flows, ok, hist


# # ------------------------------------------------------- local AI (Gemma)
# def lm_models(url=LMSTUDIO_URL):
#     import requests
#     try:
#         data = requests.get(f"{url}/models", timeout=3).json()["data"]
#         return [m["id"] for m in data]
#     except Exception:
#         return []


# def ai_report(summary, model, url=LMSTUDIO_URL):
#     import requests
#     prompt = ("You are a power systems engineer. Write a short plain-English "
#               "load flow study summary: voltage problems, losses, and practical "
#               "suggestions. Use ONLY the numbers given, do not invent any.\n\n"
#               + summary)
#     r = requests.post(f"{url}/chat/completions", timeout=300, json={
#         "model": model, "temperature": 0.3, "max_tokens": 700,
#         "messages": [{"role": "user", "content": prompt}]})
#     return r.json()["choices"][0]["message"]["content"]


# # ------------------------------------------------------ study extras
# def contingency(bus, lines, vmin, vmax):
#     """N-1: remove each line, re-solve (Newton-Raphson), rank by severity."""
#     rows = []
#     for k in range(len(lines)):
#         name = f"{int(lines.iloc[k]['From'])}-{int(lines.iloc[k]['To'])}"
#         try:
#             r, fl, ok, _ = solve_loadflow(bus, lines.drop(lines.index[k]).reset_index(drop=True))
#             if not ok or not np.isfinite(r["V (pu)"]).all():
#                 raise ValueError("no convergence")
#             v = r["V (pu)"]
#             bad = r[(v < vmin) | (v > vmax)]["Bus"].tolist()
#             rows.append([name, "OK", len(bad), round(v.min(), 4),
#                          int(r.loc[v.idxmin(), "Bus"]), round(fl["Loss_P"].sum(), 4),
#                          ", ".join(map(str, bad)) or "-"])
#         except Exception:
#             rows.append([name, "FAILED", None, None, None, None, "islanded/diverged"])
#     df = pd.DataFrame(rows, columns=["Outage", "Status", "Violations", "Min V (pu)",
#                                      "At bus", "Loss (pu)", "Buses violating"])
#     return df.sort_values(["Status", "Violations", "Min V (pu)"],
#                           ascending=[True, False, True]).reset_index(drop=True)


# def fault_analysis(bus, lines, res, xd, zf, base, kv):
#     """3-phase fault at every bus via Zbus (loads neglected, generators = Xd'')."""
#     n = len(bus)
#     Y = build_ybus(n, lines)
#     for i in np.where(bus["Type"].values != "PQ")[0]:
#         Y[i, i] += 1 / (1j * xd)
#     Z = np.linalg.inv(Y)
#     V0 = res["V (pu)"].values * np.exp(1j * np.radians(res["Angle (deg)"].values))
#     If = V0 / (np.diag(Z) + zf)
#     ib = base / (np.sqrt(3) * kv)
#     df = pd.DataFrame({"Bus": np.arange(1, n + 1), "Fault I (pu)": abs(If),
#                        "Fault I (kA)": abs(If) * ib, "Fault MVA": abs(If) * base})
#     return df, Z, V0, If


# def draw_network(res, lines, vmin, vmax):
#     import matplotlib
#     matplotlib.use("Agg")
#     import matplotlib.pyplot as plt
#     n = len(res)
#     edges = [(int(a) - 1, int(b) - 1) for a, b in zip(lines["From"], lines["To"])]
#     pos = np.random.default_rng(1).random((n, 2))
#     k = 1 / np.sqrt(n)
#     for it in range(250):  # Fruchterman-Reingold layout
#         d = pos[:, None] - pos[None]
#         dist = np.linalg.norm(d, axis=2) + 1e-9
#         disp = (d / dist[..., None] * (k**2 / dist)[..., None]).sum(1)
#         for i, j in edges:
#             dv = pos[i] - pos[j]
#             dd = np.linalg.norm(dv) + 1e-9
#             disp[i] -= dv / dd * dd**2 / k
#             disp[j] += dv / dd * dd**2 / k
#         L = np.linalg.norm(disp, axis=1)[:, None] + 1e-9
#         pos += disp / L * np.minimum(L, 0.1 * (1 - it / 250))
#     v = res["V (pu)"].values
#     fig, ax = plt.subplots(figsize=(7, 5))
#     for i, j in edges:
#         ax.plot(*zip(pos[i], pos[j]), c="gray", lw=1.5, zorder=1)
#     sc = ax.scatter(pos[:, 0], pos[:, 1], c=v, cmap="RdYlGn", s=650, zorder=2,
#                     vmin=vmin - 0.03, vmax=vmax + 0.03, linewidths=2.5,
#                     edgecolors=["red" if (x < vmin or x > vmax) else "black" for x in v])
#     for i in range(n):
#         ax.text(*pos[i], str(i + 1), ha="center", va="center", fontweight="bold", zorder=3)
#     fig.colorbar(sc, label="Voltage (pu), red outline = violation")
#     ax.axis("off")
#     return fig


# # ------------------------------------------------------------------ cases
# def _bus(types, V, Pd, Qd, Pg=None, Bs=None):
#     n = len(types)
#     return pd.DataFrame({"Type": types, "V": V, "Pg": Pg or [0.0] * n, "Qg": [0.0] * n,
#                          "Pd": Pd, "Qd": Qd, "Bs": Bs or [0.0] * n})


# def _lines(rows):
#     r = pd.DataFrame(rows, columns=["From", "To", "R", "X", "B", "Tap"])
#     return r


# CASES = {
#     "5-bus (demo)": (
#         _bus(["Slack", "PV", "PQ", "PQ", "PQ"], [1.06, 1.04, 1, 1, 1],
#              [0, 0.2, 0.45, 0.4, 0.6], [0, 0.1, 0.15, 0.05, 0.1], Pg=[0, 0.4, 0, 0, 0]),
#         _lines([[1, 2, .02, .06, .06, 1], [1, 3, .08, .24, .05, 1], [2, 3, .06, .18, .04, 1],
#                 [2, 4, .06, .18, .04, 1], [2, 5, .04, .12, .03, 1], [3, 4, .01, .03, .02, 1],
#                 [4, 5, .08, .24, .05, 1]])),
#     "IEEE 14-bus": (
#         _bus(["Slack", "PV", "PV", "PQ", "PQ", "PV", "PQ", "PV", "PQ", "PQ", "PQ", "PQ", "PQ", "PQ"],
#              [1.06, 1.045, 1.01, 1, 1, 1.07, 1, 1.09, 1, 1, 1, 1, 1, 1],
#              [0, .217, .942, .478, .076, .112, 0, 0, .295, .09, .035, .061, .135, .149],
#              [0, .127, .19, -.039, .016, .075, 0, 0, .166, .058, .018, .016, .058, .05],
#              Pg=[0, .4] + [0] * 12, Bs=[0] * 8 + [0.19] + [0] * 5),
#         _lines([[1, 2, .01938, .05917, .0528, 1], [1, 5, .05403, .22304, .0492, 1],
#                 [2, 3, .04699, .19797, .0438, 1], [2, 4, .05811, .17632, .034, 1],
#                 [2, 5, .05695, .17388, .0346, 1], [3, 4, .06701, .17103, .0128, 1],
#                 [4, 5, .01335, .04211, 0, 1], [4, 7, 0, .20912, 0, .978],
#                 [4, 9, 0, .55618, 0, .969], [5, 6, 0, .25202, 0, .932],
#                 [6, 11, .09498, .1989, 0, 1], [6, 12, .12291, .25581, 0, 1],
#                 [6, 13, .06615, .13027, 0, 1], [7, 8, 0, .17615, 0, 1],
#                 [7, 9, 0, .11001, 0, 1], [9, 10, .03181, .0845, 0, 1],
#                 [9, 14, .12711, .27038, 0, 1], [10, 11, .08205, .19207, 0, 1],
#                 [12, 13, .22092, .19988, 0, 1], [13, 14, .17093, .34802, 0, 1]])),
# }


# # -------------------------------------------------------------------- GUI
# def main():
#     import streamlit as st
#     st.set_page_config(page_title="Power System Analysis", layout="wide")
#     st.title("Power System Analysis: Load Flow, N-1 and Fault Study")
#     st.caption("Any number of buses. Edit tables or pick a preset. Per unit. "
#                "Line Tap = off-nominal tap ratio (1 = none); Bus Bs = shunt susceptance.")

#     with st.sidebar:
#         st.header("Settings")
#         case = st.selectbox("Case", list(CASES))
#         method = st.selectbox("Method", METHODS)
#         base = st.number_input("Base MVA", value=100.0)
#         vmin = st.number_input("Min voltage (pu)", value=0.95)
#         vmax = st.number_input("Max voltage (pu)", value=1.10)

#     st.subheader("Bus data")
#     bus = st.data_editor(CASES[case][0], num_rows="dynamic", key=f"bus_{case}",
#                          column_config={"Type": st.column_config.SelectboxColumn(
#                              options=["Slack", "PV", "PQ"])})
#     st.subheader("Line data")
#     lines = st.data_editor(CASES[case][1], num_rows="dynamic", key=f"lines_{case}")

#     if st.button("Solve", type="primary"):
#         try:
#             b = bus.dropna(subset=["Type"]).fillna(0).reset_index(drop=True)
#             l = lines.dropna(subset=["From", "To"]).fillna(0).reset_index(drop=True)
#             res, flows, ok, hist = solve_loadflow(b, l, method)
#             cmp = []
#             for m in METHODS:
#                 r2, f2, ok2, h2 = solve_loadflow(b, l, m)
#                 cmp.append([m, ok2, len(h2) - 1, round(f2["Loss_P"].sum() * base, 4),
#                             round(r2["V (pu)"].min(), 4)])
#             n1 = contingency(b, l, vmin, vmax)
#             loss = flows["Loss_P"].sum() * base
#             st.session_state["out"] = dict(
#                 res=res, flows=flows, ok=ok, its=len(hist) - 1, method=method, b=b, l=l,
#                 cmp=pd.DataFrame(cmp, columns=["Method", "Converged", "Iterations",
#                                                "Loss (MW)", "Min V (pu)"]),
#                 n1=n1, loss=loss, vmin=vmin, vmax=vmax, base=base,
#                 summary=(f"Method: {method}, base {base} MVA\n"
#                          + res.round(4).to_string(index=False)
#                          + f"\nTotal real loss: {loss:.2f} MW. Voltage limits: {vmin}-{vmax} pu."
#                          + "\nWorst N-1 line outages (worst first):\n"
#                          + n1.head(3).to_string(index=False)))
#         except Exception as e:
#             st.session_state.pop("out", None)
#             st.error(f"Error: {e}")

#     out = st.session_state.get("out")
#     if not out:
#         return
#     res = out["res"]
#     (st.success if out["ok"] else st.error)(
#         f"{out['method']} " + (f"converged in {out['its']} iterations" if out["ok"]
#                                else "did not converge"))
#     c1, c2 = st.columns(2)
#     c1.metric("Total real loss", f"{out['loss']:.2f} MW")
#     bad = res[(res["V (pu)"] < out["vmin"]) | (res["V (pu)"] > out["vmax"])]
#     if len(bad):
#         c2.warning("Voltage violations at bus: " + ", ".join(map(str, bad["Bus"])))
#     else:
#         c2.success("All bus voltages within limits")

#     t1, t2, t3, t4, t5 = st.tabs(["Load flow", "Network diagram", "N-1 contingency",
#                                   "Short circuit", "AI report"])
#     with t1:
#         st.subheader("Bus results")
#         st.dataframe(res.round(4), hide_index=True)
#         st.subheader("Line flows (pu)")
#         st.dataframe(out["flows"].round(4), hide_index=True)
#         st.subheader("Voltage profile")
#         st.bar_chart(res.set_index("Bus")["V (pu)"])
#         st.subheader("Method comparison")
#         st.dataframe(out["cmp"], hide_index=True)
#     with t2:
#         st.pyplot(draw_network(res, out["l"], out["vmin"], out["vmax"]))
#     with t3:
#         st.caption("Each line removed in turn and the case re-solved. Worst first.")
#         st.dataframe(out["n1"], hide_index=True)
#     with t4:
#         st.caption("Symmetrical 3-phase fault. Loads neglected; generators modelled as Xd''.")
#         k1, k2, k3 = st.columns(3)
#         xd = k1.number_input("Generator Xd'' (pu)", value=0.2, min_value=0.001)
#         zf = k2.number_input("Fault impedance Zf (pu)", value=0.0, min_value=0.0)
#         kv = k3.number_input("Base kV (for kA)", value=33.0, min_value=0.1)
#         try:
#             sc, Z, V0, If = fault_analysis(out["b"], out["l"], res, xd, zf, out["base"], kv)
#             st.dataframe(sc.round(4), hide_index=True)
#             fb = st.selectbox("Show post-fault voltages for a fault at bus", sc["Bus"])
#             vp = abs(V0 - Z[:, fb - 1] * If[fb - 1])
#             st.bar_chart(pd.Series(vp, index=sc["Bus"], name="Post-fault |V| (pu)"))
#         except Exception as e:
#             st.error(f"Fault analysis failed: {e}")
#     with t5:
#         st.caption("Local Gemma via LM Studio explains the results; it does no math.")
#         models = lm_models()
#         if models:
#             gi = next((i for i, m in enumerate(models) if "gemma" in m.lower()), 0)
#             model = st.selectbox("Loaded model", models, index=gi)
#         else:
#             model = st.text_input("Model id (LM Studio server not detected)")
#         if st.button("Generate report") and model:
#             try:
#                 with st.spinner("Gemma is writing..."):
#                     st.write(ai_report(out["summary"], model))
#             except Exception as e:
#                 st.error(f"LM Studio not reachable: {e}")


# if __name__ == "__main__":
#     main()