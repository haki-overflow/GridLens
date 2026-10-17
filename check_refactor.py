"""Refactor check: the split modules must reproduce power_flow_methods.py exactly.

Loads the original monolith next to the new modules and compares:
  1. the source text of every moved function (pure code move),
  2. CASES bus/line tables,
  3. build_ybus, solve_loadflow (all 3 methods on both cases),
  4. contingency() and fault_analysis().

Run:  venv/bin/python check_refactor.py
"""
import inspect

import numpy as np
import pandas as pd

import ai_report
import app
import cases
import plotting
import power_flow_methods as old
import solver
import studies
from cases import CASES as NEW_CASES
from power_flow_methods import CASES as OLD_CASES

SEP = "=" * 72


def same_frame(a, b, label):
    pd.testing.assert_frame_equal(a, b)
    print(f"  ok  {label}: identical ({len(a)} rows)")


def same_array(a, b, label):
    np.testing.assert_array_equal(a, b)
    print(f"  ok  {label}: identical")


def same_hist(a, b, label):
    assert np.array_equal(np.asarray(a, float), np.asarray(b, float),
                          equal_nan=True), f"{label}: convergence history differs"
    print(f"  ok  {label}: identical ({len(b) - 1} iterations)")


def check_function_sources():
    print("moved source text (inspect.getsource)")
    pairs = [("cases._bus", cases._bus), ("cases._lines", cases._lines),
             ("solver.build_ybus", solver.build_ybus),
             ("solver.injections", solver.injections),
             ("solver.newton_raphson", solver.newton_raphson),
             ("solver.fast_decoupled", solver.fast_decoupled),
             ("solver.gauss_seidel", solver.gauss_seidel),
             ("solver.solve_loadflow", solver.solve_loadflow),
             ("studies.contingency", studies.contingency),
             ("studies.fault_analysis", studies.fault_analysis),
             ("plotting.draw_network", plotting.draw_network),
             ("ai_report.lm_models", ai_report.lm_models),
             ("ai_report.ai_report", ai_report.ai_report),
             ("app.main", app.main)]
    for label, new_fn in pairs:
        name = label.split(".")[-1]
        assert inspect.getsource(getattr(old, name)) == inspect.getsource(new_fn), \
            f"{label}: source text differs from the original"
        print(f"  ok  {label}: source identical")
    assert ai_report.LMSTUDIO_URL == old.LMSTUDIO_URL, "LMSTUDIO_URL differs"
    print("  ok  ai_report.LMSTUDIO_URL: identical")


def check_cases():
    print("CASES")
    assert list(NEW_CASES) == list(OLD_CASES), "case names/order differ"
    for name in OLD_CASES:
        o_bus, o_lines = OLD_CASES[name]
        n_bus, n_lines = NEW_CASES[name]
        same_frame(o_bus, n_bus, f"[{name}] bus table")
        same_frame(o_lines, n_lines, f"[{name}] line table")


def check_ybus():
    print("build_ybus")
    for name in OLD_CASES:
        o_bus, o_lines = OLD_CASES[name]
        n_bus, n_lines = NEW_CASES[name]
        same_array(old.build_ybus(len(o_bus), o_lines, o_bus),
                   solver.build_ybus(len(n_bus), n_lines, n_bus),
                   f"[{name}] with bus shunts")
        same_array(old.build_ybus(len(o_bus), o_lines),
                   solver.build_ybus(len(n_bus), n_lines),
                   f"[{name}] without bus shunts")


def check_solver():
    print("solve_loadflow")
    assert solver.METHODS == old.METHODS, "METHODS list differs"
    for name in OLD_CASES:
        o_bus, o_lines = OLD_CASES[name]
        n_bus, n_lines = NEW_CASES[name]
        for method in old.METHODS:
            r_o, f_o, ok_o, h_o = old.solve_loadflow(o_bus, o_lines, method)
            r_n, f_n, ok_n, h_n = solver.solve_loadflow(n_bus, n_lines, method)
            assert ok_o == ok_n, f"[{name}] {method}: converged flag differs"
            same_hist(h_o, h_n, f"[{name}] {method} history")
            same_frame(r_o, r_n, f"[{name}] {method} bus results")
            same_frame(f_o, f_n, f"[{name}] {method} line flows")
            print(f"       converged={ok_n}, iterations={len(h_n) - 1}, "
                  f"loss={f_n['Loss_P'].sum():.6f} pu")


def check_contingency():
    print("contingency (N-1)")
    for name in OLD_CASES:
        o_bus, o_lines = OLD_CASES[name]
        n_bus, n_lines = NEW_CASES[name]
        df_o = old.contingency(o_bus, o_lines, 0.95, 1.10)
        df_n = studies.contingency(n_bus, n_lines, 0.95, 1.10)
        same_frame(df_o, df_n, f"[{name}] contingency table")
        worst = df_n.iloc[0]
        print(f"       {len(df_n)} outages checked; worst: {worst['Outage']} "
              f"({worst['Status']}, min V = {worst['Min V (pu)']})")


def check_fault():
    print("fault_analysis (3-phase, Xd''=0.2, Zf=0, 100 MVA, 33 kV)")
    for name in OLD_CASES:
        o_bus, o_lines = OLD_CASES[name]
        n_bus, n_lines = NEW_CASES[name]
        r_o, _, _, _ = old.solve_loadflow(o_bus, o_lines)
        r_n, _, _, _ = solver.solve_loadflow(n_bus, n_lines)
        df_o, Z_o, V0_o, If_o = old.fault_analysis(o_bus, o_lines, r_o, 0.2, 0.0, 100.0, 33.0)
        df_n, Z_n, V0_n, If_n = studies.fault_analysis(n_bus, n_lines, r_n, 0.2, 0.0, 100.0, 33.0)
        same_frame(df_o, df_n, f"[{name}] fault table")
        same_array(Z_o, Z_n, f"[{name}] Zbus")
        same_array(V0_o, V0_n, f"[{name}] prefault voltages")
        same_array(If_o, If_n, f"[{name}] fault currents")
        print(f"       max fault current = {df_n['Fault I (pu)'].max():.6f} pu")


def main():
    print(SEP)
    print("Refactor check: power_flow_methods.py vs cases/solver/studies/plotting/ai_report/app")
    print(SEP)
    check_function_sources()
    check_cases()
    check_ybus()
    check_solver()
    check_contingency()
    check_fault()
    print(SEP)
    print("PASS: every result is exactly identical to the original module.")


if __name__ == "__main__":
    main()
