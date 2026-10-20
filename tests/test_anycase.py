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


# ------------------------------------------------------------------ step 2: islands
def _two_islands():
    """5-bus demo plus a separate 2-bus island (buses 6-7) with its own slack."""
    extra_b = pd.DataFrame({"Type": ["Slack", "PQ"], "V": [1.02, 1.0], "Pg": [0.0, 0.0],
                            "Qg": [0.0, 0.0], "Pd": [0.0, 0.3], "Qd": [0.0, 0.1], "Bs": [0.0, 0.0]})
    extra_l = pd.DataFrame([dict(From=6, To=7, R=0.02, X=0.08, B=0.02, Tap=1.0)])
    return (pd.concat([B5, extra_b], ignore_index=True),
            pd.concat([L5, extra_l], ignore_index=True), extra_b, extra_l)


def test_each_island_with_a_slack_is_solved_on_its_own():
    bus, lines, eb, el = _two_islands()
    b, l, probs, notes = _prep(bus, lines)
    assert probs == []
    assert any("2 islands" in n for n in notes)
    out = gridcore.run_study(b, l, "Newton-Raphson", 1e-8, 100.0, 0.95, 1.1)
    assert out["ok"]
    main, *_ = solve_loadflow(B5, L5)
    small, *_ = solve_loadflow(eb, el.assign(From=1, To=2))
    assert np.allclose(out["res"]["V (pu)"].iloc[:5], main["V (pu)"], atol=1e-8)
    assert np.allclose(out["res"]["V (pu)"].iloc[5:], small["V (pu)"], atol=1e-8)
    assert np.allclose(out["res"]["Angle (deg)"].iloc[5:], small["Angle (deg)"], atol=1e-6)


def test_island_without_a_slack_is_reported_by_name():
    bus, lines, *_ = _two_islands()
    bus.loc[5, "Type"] = "PQ"
    probs = _prep(bus, lines)[2]
    assert probs == ["Network is disconnected: buses 6, 7 have no path to a Slack bus. "
                     "Connect them, or make one of them the Slack bus of its own island."]


def test_two_slacks_in_one_island_are_still_a_problem():
    bus, lines, *_ = _two_islands()
    bus.loc[1, "Type"] = "Slack"
    assert _prep(bus, lines)[2] == ["Island with buses 1, 2, 3, 4, 5 has more than one "
                                    "Slack bus (1, 2); exactly one per island."]


def test_out_of_service_line_can_split_the_network():
    lines = L5.assign(InService=[1, 1, 1, 1, 0, 1, 0])   # 2-5 and 4-5 out: bus 5 alone
    probs = _prep(B5, lines)[2]
    assert probs and probs[0].startswith("Network is disconnected: buses 5 ")


# ------------------------------------------------- step 4: fallback, hints, ratings
def test_fallback_solves_when_the_chosen_method_gives_up(monkeypatch):
    real = gridcore.solve_loadflow

    def gs_never_converges(bus, lines, method="Newton-Raphson", *a, **kw):
        res, flows, ok, hist = real(bus, lines, method, *a, **kw)
        return res, flows, ok and method != "Gauss-Seidel", hist
    monkeypatch.setattr(gridcore, "solve_loadflow", gs_never_converges)
    b, l, *_ = _prep(*CASES["IEEE 14-bus"])
    res, flows, ok, hist, b_lf, qlog, attempts, hint = gridcore.loadflow(b, l, "Gauss-Seidel", 1e-8)
    assert ok and hint == ""
    assert [a["Converged"] for a in attempts] == [False, True]
    assert attempts[1]["Method"] == "Newton-Raphson"
    nr, *_ = real(b, l)
    assert np.allclose(res["V (pu)"], nr["V (pu)"], atol=1e-12)
    *_, attempts, hint = gridcore.loadflow(b, l, "Gauss-Seidel", 1e-8, fallback=False)
    assert len(attempts) == 1 and hint.startswith("Worst mismatch at bus")


def test_hint_says_load_too_high():
    bus = B5.assign(Pd=B5["Pd"] * 8, Qd=B5["Qd"] * 8, Pg=B5["Pg"] * 8)
    b, l, *_ = _prep(bus, L5)
    *_, ok, hist, b_lf, qlog, attempts, hint = gridcore.loadflow(b, l, "Newton-Raphson", 1e-8)[:8]
    assert not ok and len(attempts) == 5
    assert "solves at half load" in hint


def test_hint_spots_megawatts_typed_as_per_unit():
    bus = B5.assign(Pd=B5["Pd"] * 100, Qd=B5["Qd"] * 100, Pg=B5["Pg"] * 100)
    b, l, *_ = _prep(bus, L5)
    hint = gridcore.loadflow(b, l, "Newton-Raphson", 1e-8)[-1]
    assert "look like MW" in hint


def test_line_loading_and_n1_overloads_from_ratings():
    lines = L5.assign(Rate=[120, 0, 40, 40, 60, 40, 30])
    b, l, *_ = _prep(B5, lines)
    out = gridcore.run_study(b, l, "Newton-Raphson", 1e-8, 100.0, 0.95, 1.1)
    ld = out["loading"]
    s12 = np.hypot(out["flows"]["P_ij"][0], out["flows"]["Q_ij"][0]) * 100
    assert ld["S (MVA)"][0] >= s12 - 1e-9 and np.isnan(ld["Loading (%)"][1])
    assert ld["Loading (%)"][0] == pytest.approx(ld["S (MVA)"][0] / 120 * 100)
    assert (out["n1"]["Overloads"].fillna(0) > 0).any()
    assert "Overloads" in out["summary"]


def test_parallel_branches_get_unique_names():
    from studies import branch_names
    lines = pd.concat([L5, L5.iloc[[0]]], ignore_index=True)
    assert branch_names(lines)[-1] == "1-2 (2)"
    res, *_ = solve_loadflow(B5, lines)   # parallel lines simply add in Ybus
    assert res["V (pu)"].notna().all()


# ------------------------------------------------------- step 5: actual units
SAADAT_67_PU = (
    pd.DataFrame({"Type": ["Slack", "PQ", "PQ"], "V": [1.05, 1.0, 1.0], "Pg": [0.0] * 3,
                  "Qg": [0.0] * 3, "Pd": [0.0, 2.566, 1.386], "Qd": [0.0, 1.102, 0.452]}),
    pd.DataFrame({"From": [1, 1, 2], "To": [2, 3, 3], "R": [0.02, 0.01, 0.0125],
                  "X": [0.04, 0.03, 0.025], "B": [0.0] * 3}))
Z230 = 230.0 ** 2 / 100.0          # 529 ohm
SAADAT_67_ACTUAL = (
    pd.DataFrame({"Type": ["Slack", "PQ", "PQ"], "V": [1.05, 1.0, 1.0], "kV": [230.0] * 3,
                  "Pg": [0.0] * 3, "Qg": [0.0] * 3, "Pd": [0.0, 256.6, 138.6],
                  "Qd": [0.0, 110.2, 45.2]}),
    pd.DataFrame({"From": [1, 1, 2], "To": [2, 3, 3], "R": [10.58, 5.29, 6.6125],
                  "X": [21.16, 15.87, 13.225], "B": [0.0] * 3}))


def test_actual_units_case_equals_the_per_unit_case():
    pb, pl, probs, _ = _prep(*SAADAT_67_PU)
    ab, al, aprobs, _ = _prep(*SAADAT_67_ACTUAL, units="actual")
    assert probs == [] and aprobs == []
    assert np.allclose(al[["R", "X"]].to_numpy(), pl[["R", "X"]].to_numpy(), atol=1e-12)
    assert np.allclose(ab["Pd"], pb["Pd"]) and np.allclose(ab["Qd"], pb["Qd"])


def test_saadat_example_6_7_from_ohms_and_megawatts():
    # Saadat, Power System Analysis, Example 6.7: V2 = 0.98 - j0.06, V3 = 1.0 - j0.05,
    # slack S1 = 409.5 + j189 MVA, so total loss = 409.5 - (256.6 + 138.6) = 14.3 MW.
    b, l, probs, _ = _prep(*SAADAT_67_ACTUAL, units="actual")
    assert probs == []
    out = gridcore.run_study(b, l, "Newton-Raphson", 1e-10, 100.0, 0.95, 1.1)
    V = out["res"]["V (pu)"].to_numpy() * np.exp(1j * np.radians(out["res"]["Angle (deg)"].to_numpy()))
    assert V[1] == pytest.approx(0.98 - 0.06j, abs=1e-5)
    assert V[2] == pytest.approx(1.00 - 0.05j, abs=1e-5)
    assert out["slack_p"] == pytest.approx(409.5, abs=0.05)
    assert out["res"]["Q_inj"].iloc[0] * 100 == pytest.approx(189.0, abs=0.05)
    assert out["loss"] == pytest.approx(14.3, abs=0.05)


def test_actual_units_need_kv():
    bus, lines = SAADAT_67_ACTUAL
    probs = _prep(bus.drop(columns="kV"), lines, units="actual")[2]
    assert probs[0].startswith("Actual units need the base kV of every bus")


def test_line_between_voltage_levels_is_flagged():
    bus, lines = SAADAT_67_ACTUAL
    notes = _prep(bus.assign(kV=[230.0, 230.0, 132.0]), lines, units="actual")[3]
    assert any("not marked as a transformer" in n for n in notes)


# ------------------------------------------------- acceptance: tap and Q limits
def _v2(v1, p, q, x):
    """Receiving voltage of a lossless line: V2^4 + (2QX - V1^2) V2^2 + X^2 (P^2 + Q^2) = 0."""
    b = 2 * q * x - v1 ** 2
    return np.sqrt((-b + np.sqrt(b * b - 4 * x * x * (p * p + q * q))) / 2)


@pytest.mark.parametrize("tap", [0.95, 1.0, 1.05])
def test_tap_transformer_matches_closed_form(tap):
    # ideal a:1 transformer at the From side, then X: bus 1 sees V1 / a behind X
    bus, lines = _two_bus(Tap=tap, Kind="trafo")
    b, l, probs, _ = _prep(bus, lines)
    assert probs == []
    res, *_ = solve_loadflow(b, l)
    assert res["V (pu)"].iloc[1] == pytest.approx(_v2(1.0 / tap, 0.6, 0.2, 0.2), abs=1e-9)
    no_load, *_ = solve_loadflow(b.assign(Pd=0.0, Qd=0.0), l)
    assert no_load["V (pu)"].iloc[1] == pytest.approx(1.0 / tap, abs=1e-9)


def test_q_limited_generator_holds_qmax_and_lets_v_drop():
    # bus 2: generator set to 1.05 pu, Qmax 0.2 pu, load 0.6 + j0.5: it cannot hold 1.05
    bus = pd.DataFrame({"Type": ["Slack", "PV"], "V": [1.0, 1.05], "Pg": [0.0, 0.0], "Qg": [0.0, 0.0],
                        "Pd": [0.0, 0.6], "Qd": [0.0, 0.5], "Bs": [0.0, 0.0], "Qmin": [None, -0.5],
                        "Qmax": [None, 0.2]})
    lines = pd.DataFrame([dict(From=1, To=2, R=0.0, X=0.2, B=0.0, Tap=1.0)])
    b, l, probs, _ = _prep(bus, lines, qlim=True)
    out = gridcore.run_study(b, l, "Newton-Raphson", 1e-10, 100.0, 0.95, 1.1, qlim=True)
    assert out["ok"] and out["qlog"] and out["qlog"][0]["Action"] == "PV → PQ"
    v2 = out["res"]["V (pu)"].iloc[1]
    assert v2 < 1.05
    qg = out["res"]["Q_inj"].iloc[1] + 0.5
    assert qg == pytest.approx(0.2, abs=1e-9)
    assert v2 == pytest.approx(_v2(1.0, 0.6, 0.5 - 0.2, 0.2), abs=1e-9)
