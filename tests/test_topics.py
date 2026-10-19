"""Sequence faults, symmetrical components, economic dispatch, line ABCD."""
import numpy as np
import pandas as pd
import pytest

import dispatch as D
import seqfaults as SF
import symcomp as SC
import tline as TL
from cases import CASES


# ------------------------------------------------------------ sequence faults
def _seq_case(name="IEEE 14-bus"):
    bus, lines = CASES[name]
    gens, br = SF.seed_tables(bus, lines)
    return len(bus), gens, br


@pytest.mark.parametrize("zf", [0j, 0.05j, 0.1 + 0.02j])
def test_slg_current_is_3v_over_sum_of_impedances(zf):
    n, gens, br = _seq_case()
    Z0, Z1, Z2 = SF.seq_zbus(n, gens, br)
    vf = np.ones(n, complex)
    for k in (1, 4, 9):
        r = SF.solve_fault("SLG", k, gens, br, vf, zf)
        i = k - 1
        want = 3 * vf[i] / (Z1[i, i] + Z2[i, i] + Z0[i, i] + 3 * zf)
        assert r["Iabc"][0] == pytest.approx(want, rel=1e-12)
        assert abs(r["Iabc"][1]) < 1e-12 and abs(r["Iabc"][2]) < 1e-12
        # the faulted phase voltage equals Ia * Zf
        assert r["Vabc"][i, 0] == pytest.approx(r["Iabc"][0] * zf, abs=1e-12)


def test_three_phase_fault_is_v_over_z1():
    n, gens, br = _seq_case()
    Z0, Z1, Z2 = SF.seq_zbus(n, gens, br)
    r = SF.solve_fault("3-phase", 3, gens, br, np.ones(n, complex))
    assert abs(r["Iabc"][0]) == pytest.approx(1 / abs(Z1[2, 2]))
    assert np.allclose(abs(r["Iabc"]), abs(r["Iabc"][0]))   # balanced


def test_ll_and_dlg_boundary_conditions():
    n, gens, br = _seq_case()
    vf = np.ones(n, complex)
    ll = SF.solve_fault("LL", 5, gens, br, vf)
    assert abs(ll["Iabc"][0]) < 1e-12                         # Ia = 0
    assert ll["Iabc"][1] == pytest.approx(-ll["Iabc"][2])     # Ib = -Ic
    assert ll["Vabc"][4, 1] == pytest.approx(ll["Vabc"][4, 2])  # Vb = Vc
    dlg = SF.solve_fault("DLG", 5, gens, br, vf)
    assert abs(dlg["Iabc"][0]) < 1e-12                        # Ia = 0
    assert abs(dlg["Vabc"][4, 1]) < 1e-12 and abs(dlg["Vabc"][4, 2]) < 1e-12


def test_kA_uses_the_faulted_bus_base_kv():
    n, gens, br = _seq_case("5-bus (demo)")
    kv = np.array([132.0, 132.0, 33.0, 33.0, 33.0])
    vf = np.ones(n, complex)
    t = SF.fault_table("3-phase", gens, br, vf, base=100.0, kv=kv)
    assert t["If (kA)"].iloc[0] == pytest.approx(t["If (pu)"].iloc[0] * 100 / (3**0.5 * 132))
    assert t["If (kA)"].iloc[3] == pytest.approx(t["If (pu)"].iloc[3] * 100 / (3**0.5 * 33))


def test_delta_wye_transformer_blocks_zero_sequence():
    gens = pd.DataFrame({"Bus": [1], "X1": [0.2], "X2": [0.2], "X0": [0.05],
                         "Xn": [0.0], "Conn": ["Yg"]})
    br = pd.DataFrame({"From": [1], "To": [2], "Kind": ["transformer"],
                       "X1": [0.1], "X2": [0.1], "X0": [0.1],
                       "Conn From": ["D"], "Conn To": ["Yg"]})
    Z0, Z1, _ = SF.seq_zbus(2, gens, br)
    assert Z0[1, 1] == pytest.approx(0.1j, rel=1e-6)   # Yg side: X0 to ground
    assert abs(Z0[0, 1]) < 1e-6                         # no zero-seq transfer
    assert Z1[1, 1] == pytest.approx(0.3j, rel=1e-6)


# -------------------------------------------------------- symmetrical comps
def test_sequence_roundtrip_and_balanced_set():
    abc = [SC.polar(1, 0), SC.polar(1, -120), SC.polar(1, 120)]
    s = SC.to_sequence(abc)
    assert s == pytest.approx([0, 1, 0], abs=1e-12)
    rnd = np.array([1 + 2j, -0.5 + 0.3j, 0.7 - 1.1j])
    assert SC.to_phase(SC.to_sequence(rnd)) == pytest.approx(rnd)
    assert SC.a**3 == pytest.approx(1) and 1 + SC.a + SC.a**2 == pytest.approx(0)


# ---------------------------------------------------------- economic dispatch
def test_lossless_dispatch_matches_closed_form():
    u = pd.DataFrame({"a": [500.0, 400.0, 200.0], "b": [5.3, 5.5, 5.8],
                      "c": [0.004, 0.006, 0.009]})
    r = D.dispatch(u, 800.0, use_limits=False)
    assert r["ok"] and r["lam"] == pytest.approx(8.5)
    assert r["P"] == pytest.approx([400.0, 250.0, 150.0])


def test_dispatch_respects_limits():
    u = pd.DataFrame({"a": [500.0, 400.0, 200.0], "b": [5.3, 5.5, 5.8],
                      "c": [0.004, 0.006, 0.009], "Pmin": [200.0, 150.0, 100.0],
                      "Pmax": [450.0, 350.0, 225.0]})
    r = D.dispatch(u, 975.0)
    assert r["ok"] and r["P"].sum() == pytest.approx(975.0, abs=1e-5)
    # unit 1 would take 482.9 MW at λ = 9.163, so it is pinned at Pmax and
    # the other two share the rest at λ = 9.4
    assert r["P"] == pytest.approx([450.0, 325.0, 200.0], abs=1e-5)
    assert r["lam"] == pytest.approx(9.4)
    free = r["table"]["At limit"] == ""
    assert np.allclose(r["table"]["IC = b + 2cP"][free], r["lam"], atol=1e-6)


def test_infeasible_demand_is_reported():
    u = pd.DataFrame({"a": [1.0, 1.0], "b": [5.0, 6.0], "c": [0.01, 0.01],
                      "Pmin": [0.0, 0.0], "Pmax": [100.0, 100.0]})
    assert not D.dispatch(u, 250.0)["ok"]


def test_dispatch_with_losses_meets_coordination_equations():
    e = D.EXAMPLE
    B, B0, B00 = D.b_from_pu(e["B"], e["B0"], e["B00"], e["base"])
    r = D.dispatch(e["units"], e["PD"], B, B0, B00, use_limits=False, tol=1e-9)
    assert r["ok"]
    assert r["P"].sum() == pytest.approx(e["PD"] + r["PL"], abs=1e-6)
    assert np.allclose(r["table"]["L·IC"], r["lam"], rtol=1e-6)


# --------------------------------------------------------------- line ABCD
@pytest.mark.parametrize("model", TL.MODELS)
def test_abcd_reciprocity(model):
    A, B, C, Dd = TL.abcd(model, 0.05, 0.45, 3.4, 300)
    assert A * Dd - B * C == pytest.approx(1, abs=1e-12)


def test_long_line_tends_to_pi_model_when_short():
    pi = np.array(TL.abcd("medium (π)", 0.05, 0.45, 3.4, 20))
    lo = np.array(TL.abcd("long", 0.05, 0.45, 3.4, 20))
    assert np.allclose(pi, lo, rtol=1e-3)     # differ at O((γl)²)


def test_short_line_regulation_and_efficiency():
    r = TL.performance("short", 0.1, 0.3, 0.0, 50, 66.0, 20.0, 0.8, True)
    assert r["IS"] == pytest.approx(r["IR"])
    assert r["reg"] > 0 and 0 < r["eff"] < 100
    assert r["loss"] == pytest.approx(3 * abs(r["IR"]) ** 2 * 0.1 * 50, rel=1e-9)
