"""v1.6: any user-defined case. Validation of the wider case model, islands,
the solver additions and the fallback chain."""
import pandas as pd

import gridcore
from gridcore import CASES

CFG = dict(method="Newton-Raphson", base=100.0, vmin=0.95, vmax=1.10,
           tol=1e-8, taps=True, shunts=True, qlim=False)
B5, L5 = CASES["5-bus (demo)"]


def _prep(bus, lines, **cfg):
    return gridcore.prep_case(bus, lines, dict(CFG, **cfg))


# ------------------------------------------------------------ step 1: case model
def test_duplicate_bus_numbers_are_a_problem():
    bus = B5.assign(Num=[1, 2, 3, 3, 5])
    assert "Duplicate bus numbers: 3." in _prep(bus, L5)[2]


def test_bus_numbers_with_gaps_are_fine():
    bus = B5.assign(Num=[101, 102, 205, 206, 300], Name=list("ABCDE"))
    assert _prep(bus, L5)[2] == []


def test_base_mva_and_kv_must_be_positive():
    assert "System base MVA must be greater than 0." in _prep(B5, L5, base=0)[2]
    bus = B5.assign(kV=[132, 132, 0, 33, 33])
    assert "Base kV must be greater than 0 (bus rows 3)." in _prep(bus, L5)[2]


def test_in_service_flag_is_normalised():
    lines = L5.assign(InService=[1, "no", True, "0", None, "yes", 0])
    b, l, probs, notes = _prep(B5, lines)
    assert list(l["InService"]) == [1, 0, 1, 0, 1, 1, 0]
    assert "3 branch(es) are out of service and carry no flow." in notes


def test_new_columns_default_when_missing():
    b, l, probs, _ = _prep(B5, L5)
    assert probs == [] and (b["Gs"] == 0).all()
    assert (l["Shift"] == 0).all() and (l["Rate"] == 0).all() and (l["InService"] == 1).all()


# --------------------------------------------------------- step 3: solver additions
import numpy as np
import pytest
from pandas.testing import assert_frame_equal

from solver import build_ybus, solve_loadflow


def _two_bus(**line):
    bus = pd.DataFrame({"Type": ["Slack", "PQ"], "V": [1.0, 1.0], "Pg": [0.0, 0.0], "Qg": [0.0, 0.0],
                        "Pd": [0.0, 0.6], "Qd": [0.0, 0.2], "Bs": [0.0, 0.0]})
    lines = pd.DataFrame([dict(dict(From=1, To=2, R=0.0, X=0.2, B=0.0, Tap=1.0), **line)])
    return bus, lines


def test_zero_shift_and_in_service_columns_change_nothing():
    lines = L5.assign(Shift=0.0, InService=1)
    a = solve_loadflow(B5, L5)
    b = solve_loadflow(B5, lines)
    assert_frame_equal(a[0], b[0], check_exact=True)
    assert_frame_equal(a[1], b[1], check_exact=True)


def test_out_of_service_line_equals_removing_it():
    lines = L5.assign(InService=[1, 1, 1, 1, 0, 1, 1])
    res, flows, ok, _ = solve_loadflow(B5, lines)
    ref, rflows, rok, _ = solve_loadflow(B5, L5.drop(index=4).reset_index(drop=True))
    assert ok and rok
    assert_frame_equal(res, ref, check_exact=True)
    assert (flows.iloc[4, 2:] == 0).all() and len(flows) == 7


def test_phase_shifter_moves_power_by_the_shift_angle():
    # lossless branch, shift phi on the From side: P_from = V1 V2 / X * sin(th1 - th2 - phi)
    for phi in (0.0, 10.0, -5.0):
        bus, lines = _two_bus(Shift=phi)
        res, flows, ok, _ = solve_loadflow(bus, lines)
        assert ok
        V, th = res["V (pu)"].to_numpy(), np.radians(res["Angle (deg)"].to_numpy())
        p = V[0] * V[1] / 0.2 * np.sin(th[0] - th[1] - np.radians(phi))
        assert flows["P_ij"].iloc[0] == pytest.approx(p, abs=1e-9)
        assert flows["P_ji"].iloc[0] == pytest.approx(-0.6, abs=1e-8)   # load is met


def test_phase_shifter_ybus_is_not_symmetric():
    bus, lines = _two_bus(Shift=30.0)
    Y = build_ybus(2, lines, bus)
    t = np.exp(1j * np.radians(30))
    y = 1 / 0.2j
    assert Y[0, 1] == pytest.approx(-y / np.conj(t)) and Y[1, 0] == pytest.approx(-y / t)


def test_shunt_conductance_acts_like_a_constant_impedance_load():
    bus, lines = _two_bus()
    with_g = bus.assign(Gs=[0.0, 0.1])
    res, *_ = solve_loadflow(with_g, lines)
    v2 = res["V (pu)"].iloc[1]
    as_load = bus.assign(Pd=[0.0, 0.6 + 0.1 * v2 ** 2])
    ref, *_ = solve_loadflow(as_load, lines)
    assert ref["V (pu)"].iloc[1] == pytest.approx(v2, abs=1e-9)


@pytest.mark.parametrize("kw", [dict(init="setpoint"), dict(damp=0.6, max_iter=80)])
def test_setpoint_start_and_damped_newton_reach_the_same_answer(kw):
    a, _, ok, _ = solve_loadflow(*CASES["IEEE 14-bus"])
    b, _, ok2, _ = solve_loadflow(*CASES["IEEE 14-bus"], **kw)
    assert ok and ok2
    assert np.allclose(a["V (pu)"], b["V (pu)"], atol=1e-8)
    assert np.allclose(a["Angle (deg)"], b["Angle (deg)"], atol=1e-6)


def test_gauss_seidel_honours_tol():
    loose = solve_loadflow(B5, L5, "Gauss-Seidel", 1e-4)[3]
    tight = solve_loadflow(B5, L5, "Gauss-Seidel", 1e-9)[3]
    assert len(tight) > len(loose)
    nr = solve_loadflow(B5, L5)[0]
    gs = solve_loadflow(B5, L5, "Gauss-Seidel", 1e-10)[0]
    assert np.allclose(nr["V (pu)"], gs["V (pu)"], atol=1e-8)
