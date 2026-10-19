"""Worked-solution traces (working.py) end on the solver's answers."""
import numpy as np
import pytest

import working as W
from gridcore import CASES
from solver import build_ybus, gauss_seidel, solve_loadflow

CASE_LIST = list(CASES)


def _case(name, taps=True):
    bus, lines = CASES[name]
    lines = lines.copy()
    if not taps:
        lines["Tap"] = 1.0
    return bus, lines


@pytest.mark.parametrize("name", CASE_LIST)
def test_ybus_parts_sum_to_build_ybus(name):
    bus, lines = _case(name)
    Y = build_ybus(len(bus), lines, bus)
    parts = W.ybus_parts(bus, lines)
    Z = np.zeros_like(Y)
    for i, j, v in zip(parts["i"], parts["j"], parts["Value"]):
        Z[i, j] += v
    assert np.allclose(Y, Z, atol=1e-12)


@pytest.mark.parametrize("name", CASE_LIST)
def test_ybus_is_symmetric(name):
    bus, lines = _case(name)
    Y = build_ybus(len(bus), lines, bus)
    assert np.allclose(Y, Y.T)


@pytest.mark.parametrize("name", CASE_LIST)
def test_newton_trace_matches_solver(name):
    bus, lines = _case(name)
    res, _, ok, _ = solve_loadflow(bus, lines, "Newton-Raphson", 1e-10)
    tr = W.newton_trace(bus, lines, 1e-10)
    last = tr["its"][-1]
    assert ok and tr["ok"]
    assert np.allclose(last["V"], res["V (pu)"], atol=1e-8)
    assert np.allclose(np.degrees(last["th"]), res["Angle (deg)"], atol=1e-6)


@pytest.mark.parametrize("name", CASE_LIST)
def test_analytical_jacobian_matches_numerical(name):
    bus, lines = _case(name)
    tr = W.newton_trace(bus, lines)
    it = tr["its"][0]
    Y, ang, mag = tr["Y"], tr["ang"], tr["mag"]
    t, V0, *_ = W._setup(bus)
    J = np.block([[it["J1"], it["J2"]], [it["J3"], it["J4"]]])

    def f(x):
        th, V = np.zeros(len(bus)), V0.copy()
        th[ang], V[mag] = x[:len(ang)], x[len(ang):]
        S = (V * np.exp(1j * th)) * np.conj(Y @ (V * np.exp(1j * th)))
        return np.r_[S.real[ang], S.imag[mag]]
    x0 = np.r_[np.zeros(len(ang)), V0[mag]]
    Jn = np.column_stack([(f(x0 + e) - f(x0 - e)) / 2e-6
                          for e in np.eye(len(x0)) * 1e-6])
    assert np.allclose(J, Jn, atol=1e-5)


@pytest.mark.parametrize("name", CASE_LIST)
def test_fast_decoupled_trace_matches_solver(name):
    bus, lines = _case(name)
    res, _, ok, _ = solve_loadflow(bus, lines, "Fast Decoupled", 1e-10)
    tr = W.fast_decoupled_trace(bus, lines, 1e-10)
    assert ok and tr["ok"]
    assert np.allclose(tr["its"][-1]["V"], res["V (pu)"], atol=1e-12)


@pytest.mark.parametrize("name", CASE_LIST)
def test_gauss_seidel_trace_alpha_1_is_the_solver(name):
    bus, lines = _case(name)
    Y = build_ybus(len(bus), lines, bus)
    t, V0, Psp, Qsp, _, _ = W._setup(bus)
    th, V, ok, hist = gauss_seidel(Y, V0, np.zeros(len(bus)), t, Psp, Qsp)
    tr = W.gauss_seidel_trace(bus, lines, alpha=1.0, tol=1e-6, max_iter=5000)
    assert ok and tr["ok"] and len(tr["dmax"]) == len(hist) - 1
    assert np.allclose(np.abs(tr["V"][-1]), V, atol=0)


def test_acceleration_converges_faster():
    bus, lines = _case("IEEE 14-bus")
    slow = W.gauss_seidel_trace(bus, lines, alpha=1.0, tol=1e-6, max_iter=5000)
    fast = W.gauss_seidel_trace(bus, lines, alpha=1.6, tol=1e-6, max_iter=5000)
    assert fast["ok"] and len(fast["dmax"]) < len(slow["dmax"])
    assert np.allclose(fast["V"][-1], slow["V"][-1], atol=1e-4)


@pytest.mark.parametrize("name", CASE_LIST)
def test_methods_agree_within_1e4(name):
    bus, lines = _case(name)
    V = [solve_loadflow(bus, lines, m)[0]["V (pu)"].to_numpy()
         for m in ("Newton-Raphson", "Fast Decoupled", "Gauss-Seidel")]
    assert np.allclose(V[0], V[1], atol=1e-4) and np.allclose(V[0], V[2], atol=1e-4)


def test_answer_text_has_all_sections():
    bus, lines = _case("5-bus (demo)")
    res, flows, ok, _ = solve_loadflow(bus, lines)
    txt = W.answer_text(bus, lines, res, flows, 100.0, "Newton-Raphson",
                        W.trace_lines("Newton-Raphson", bus, lines))
    for s in ("GIVEN DATA", "BUS ADMITTANCE MATRIX", "ITERATIONS", "Jacobian",
              "Slack bus 1 power", "Total losses"):
        assert s in txt
