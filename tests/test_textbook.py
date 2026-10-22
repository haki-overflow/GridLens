"""Textbook checks against closed forms that do not use the solver."""
import numpy as np
import pandas as pd
import pytest

from solver import dc_loadflow, solve_loadflow


@pytest.mark.parametrize("method", ["Newton-Raphson", "Fast Decoupled", "Gauss-Seidel"])
def test_two_bus_lossless_line_matches_closed_form(method):
    # Slack 1.0 pu feeds P + jQ through a lossless line of reactance X.
    # Receiving voltage: V2^4 + (2QX - V1^2) V2^2 + X^2 (P^2 + Q^2) = 0 (larger root);
    # angle: sin(d) = -P X / (V1 V2).
    P, Q, X = 0.8, 0.3, 0.2
    bus = pd.DataFrame({"Type": ["Slack", "PQ"], "V": [1.0, 1.0], "Pg": [0.0, 0.0],
                        "Qg": [0.0, 0.0], "Pd": [0.0, P], "Qd": [0.0, Q], "Bs": [0.0, 0.0]})
    lines = pd.DataFrame({"From": [1], "To": [2], "R": [0.0], "X": [X], "B": [0.0], "Tap": [1.0]})
    res, flows, ok, _ = solve_loadflow(bus, lines, method, 1e-10)
    assert ok
    b = 2 * Q * X - 1.0
    v2 = np.sqrt((-b + np.sqrt(b * b - 4 * X * X * (P * P + Q * Q))) / 2)
    delta = np.degrees(np.arcsin(-P * X / v2))
    assert res["V (pu)"].iloc[1] == pytest.approx(v2, abs=1e-4)
    assert res["Angle (deg)"].iloc[1] == pytest.approx(delta, abs=1e-3)
    assert flows["Loss_P"].iloc[0] == pytest.approx(0.0, abs=1e-6)


def test_dc_load_flow_three_bus_triangle():
    # DC load flow on three buses joined by lines of X = 0.1 (R and B are ignored):
    # the reduced B is [[20, -10], [-10, 20]], so θ2 = (20 P2 + 10 P3) / 300 and
    # θ3 = (10 P2 + 20 P3) / 300; each flow is (θi - θj) / X and nothing is lost.
    P2, P3 = -1.0, -0.5
    bus = pd.DataFrame({"Type": ["Slack", "PQ", "PQ"], "V": [1.0] * 3, "Pg": [0.0] * 3,
                        "Qg": [0.0] * 3, "Pd": [0.0, -P2, -P3], "Qd": [0.0, 0.2, 0.1]})
    lines = pd.DataFrame({"From": [1, 1, 2], "To": [2, 3, 3], "R": [0.01] * 3, "X": [0.1] * 3,
                          "B": [0.02] * 3, "Tap": [1.0] * 3})
    res, flows, ok, _ = dc_loadflow(bus, lines)
    th2, th3 = (20 * P2 + 10 * P3) / 300, (10 * P2 + 20 * P3) / 300
    assert ok
    assert np.allclose(np.radians(res["Angle (deg)"]), [0, th2, th3], atol=1e-12)
    assert np.allclose(flows["P_ij"], [-th2 / 0.1, -th3 / 0.1, (th2 - th3) / 0.1], atol=1e-12)
    assert res["P_inj"].iloc[0] == pytest.approx(1.5)
    assert (res["V (pu)"] == 1).all() and (flows[["Q_ij", "Q_ji", "Loss_P", "Loss_Q"]] == 0).all().all()


def test_dc_load_flow_tap_phase_shifter_and_shunt_g():
    # Slack -> load P through X with tap a and phase shift φ on the From side, and a
    # shunt conductance G at the load (G V^2 = G at V = 1): b = 1 / (X a) and the flow
    # b (θ1 - θ2 - φ) = P + G, so θ2 = -φ - (P + G) X a.
    P, G, X, a, phi = 0.5, 0.1, 0.2, 1.05, 5.0
    bus = pd.DataFrame({"Type": ["Slack", "PQ"], "V": [1.0, 1.0], "Pg": [0.0, 0.0],
                        "Qg": [0.0, 0.0], "Pd": [0.0, P], "Qd": [0.0, 0.2], "Gs": [0.0, G]})
    lines = pd.DataFrame({"From": [1], "To": [2], "R": [0.0], "X": [X], "B": [0.0],
                          "Tap": [a], "Shift": [phi]})
    res, flows, ok, _ = dc_loadflow(bus, lines)
    assert np.radians(res["Angle (deg)"].iloc[1]) == pytest.approx(
        -np.radians(phi) - (P + G) * X * a, abs=1e-12)
    assert flows["P_ij"].iloc[0] == pytest.approx(P + G, abs=1e-12)
    assert res["P_inj"].tolist() == pytest.approx([P + G, -P], abs=1e-12)
