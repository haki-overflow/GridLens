"""Textbook checks against closed forms that do not use the solver."""
import numpy as np
import pandas as pd
import pytest

from solver import solve_loadflow


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
