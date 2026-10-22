"""v2 engine: the sparse Ybus and the sparse Newton-Raphson (analytical
Jacobian) against the dense teaching versions and finite differences (v2.1);
the sparse Fast Decoupled and the DC load flow (v2.2)."""
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import formats
import gridcore
import solver
from gridcore import CASES
from solver import build_ybus, solve_loadflow, ybus_sparse

DATA = Path(__file__).parent / "data"
CFG = dict(method="Newton-Raphson", base=100.0, vmin=0.95, vmax=1.10, tol=1e-8,
           taps=True, shunts=True, qlim=False)
NAMES = list(CASES) + ["case9", "case30", "case118"]


def _case(name):
    if name in CASES:
        bus, lines, base = *CASES[name], 100.0
    else:
        c = formats.read_case(f"{name}.m", (DATA / f"{name}.m").read_text())
        bus, lines, base = c["bus"], c["lines"], c["base"]
    b, l, probs, _ = gridcore.prep_case(bus, lines, dict(CFG, base=base))
    assert probs == []
    return b, l


@pytest.mark.parametrize("name", NAMES)
def test_sparse_ybus_is_the_dense_one(name):
    b, l = _case(name)
    assert np.allclose(ybus_sparse(len(b), l, b).toarray(), build_ybus(len(b), l, b),
                       rtol=1e-13, atol=1e-13)


def test_sparse_ybus_with_every_branch_feature():
    b, l = _case("5-bus (demo)")
    l = l.assign(Tap=[1, 0.95, 1, 1.05, 1, 1, 1], Shift=[0, 0, 5.0, 0, -3.0, 0, 0],
                 InService=[1, 1, 1, 1, 1, 0, 1])
    l = pd.concat([l, l.iloc[[0]]], ignore_index=True)          # a parallel line
    b = b.assign(Gs=[0, 0, 0.05, 0, 0], Bs=[0, 0, 0, 0.1, 0])
    assert np.allclose(ybus_sparse(5, l, b).toarray(), build_ybus(5, l, b),
                       rtol=1e-13, atol=1e-13)


@pytest.mark.parametrize("name", NAMES)
def test_sparse_jacobian_matches_central_differences(name):
    """J at a point away from the flat start against a numerical Jacobian of
    the injections at the unknowns (θ at non-Slack buses, |V| at PQ buses)."""
    b, l = _case(name)
    n = len(b)
    Y = ybus_sparse(n, l, b)
    t = b["Type"].to_numpy()
    ang, mag = np.flatnonzero(t != "Slack"), np.flatnonzero(t == "PQ")
    rng = np.random.default_rng(1)
    th, V = rng.normal(0, 0.1, n), 1 + rng.normal(0, 0.05, n)

    def S(x):
        th2, V2 = th.copy(), V.copy()
        th2[ang], V2[mag] = x[:len(ang)], x[len(ang):]
        Vc = V2 * np.exp(1j * th2)
        s = Vc * np.conj(Y @ Vc)
        return np.r_[s.real[ang], s.imag[mag]]
    x0, h = np.r_[th[ang], V[mag]], 1e-6
    Jn = np.column_stack([(S(x0 + e) - S(x0 - e)) / (2 * h) for e in np.eye(len(x0)) * h])
    Vc = V * np.exp(1j * th)
    J = solver._jacobian(Y, ang, mag)(Vc, np.exp(1j * th), Y @ Vc).toarray()
    assert np.abs(J - Jn).max() < 1e-6 * max(1.0, np.abs(J).max())


def test_singular_newton_step_raises_linalg_error():
    """A PQ bus with no in-service branch: the Jacobian is exactly singular and
    the sparse solver raises LinAlgError as numpy did, so gridcore.loadflow can
    move on to its next attempt."""
    bus = pd.DataFrame({"Type": ["Slack", "PQ"], "V": [1.0, 1.0], "Pg": [0.0, 0.0],
                        "Qg": [0.0, 0.0], "Pd": [0.0, 0.5], "Qd": [0.0, 0.1]})
    lines = pd.DataFrame([dict(From=1, To=2, R=0.01, X=0.1, B=0.0, Tap=1.0, InService=0)])
    with pytest.raises(np.linalg.LinAlgError):
        solve_loadflow(bus, lines)


def test_newton_raphson_is_fast_on_case118():
    b, l = _case("case118")
    t0 = time.perf_counter()
    res, flows, ok, hist = solve_loadflow(b, l)
    took = time.perf_counter() - t0
    assert ok and len(hist) - 1 == 4
    assert took < 0.5        # v1.6 (numerical Jacobian) about 0.1 s, v2.1 under 0.02 s


# ------------------------------------------------- v2.2: sparse Fast Decoupled, DC
@pytest.mark.parametrize("name", ["case30", "case118"])
def test_fast_decoupled_ends_where_newton_raphson_does(name):
    b, l = _case(name)
    nr, _, ok1, _ = solve_loadflow(b, l, "Newton-Raphson", 1e-10)
    fd, _, ok2, hist = solve_loadflow(b, l, "Fast Decoupled", 1e-10)
    assert ok1 and ok2 and len(hist) - 1 < 30
    assert np.abs(nr["V (pu)"] - fd["V (pu)"]).max() < 1e-9
    assert np.abs(nr["Angle (deg)"] - fd["Angle (deg)"]).max() < 1e-7


def test_dc_load_flow_balances_every_bus_on_case118():
    """Each non-Slack bus: the flows leaving it add up to Pg - Pd - Gs; the
    Slack picks up the rest and nothing is lost."""
    b, l = _case("case118")
    res, flows, ok, hist = solver.dc_loadflow(b, l)
    out = np.bincount(l["From"] - 1, flows["P_ij"], len(b)) + \
        np.bincount(l["To"] - 1, flows["P_ji"], len(b))
    p = (b["Pg"] - b["Pd"] - b["Gs"]).to_numpy()
    slack = (b["Type"] == "Slack").to_numpy()
    assert ok and hist[-1] < 1e-10
    assert np.abs(out - p)[~slack].max() < 1e-10
    assert out.sum() == pytest.approx(0, abs=1e-10)
    assert res["Angle (deg)"][slack].tolist() == pytest.approx([30.0])   # the file's Va


def test_dc_load_flow_islands_each_with_a_slack():
    """Two islands: each angle follows its own Slack; out-of-service rows carry 0."""
    bus = pd.DataFrame({"Type": ["Slack", "PQ", "Slack", "PQ"], "V": [1.0] * 4,
                        "Va": [0.0, 0.0, 10.0, 0.0], "Pg": [0.0] * 4, "Qg": [0.0] * 4,
                        "Pd": [0, 0.5, 0, 0.2], "Qd": [0.0] * 4})
    lines = pd.DataFrame({"From": [1, 3, 1], "To": [2, 4, 4], "R": [0.0] * 3,
                          "X": [0.1, 0.2, 0.1], "B": [0.0] * 3, "InService": [1, 1, 0]})
    res, flows, ok, _ = solver.dc_loadflow(bus, lines)
    assert res["Angle (deg)"].tolist() == pytest.approx(
        [0, np.degrees(-0.05), 10, 10 + np.degrees(-0.04)], abs=1e-12)
    assert flows["P_ij"].tolist() == pytest.approx([0.5, 0.2, 0.0], abs=1e-12)


def test_fd_and_dc_are_fast_on_case118():
    b, l = _case("case118")
    t0 = time.perf_counter()
    assert solve_loadflow(b, l, "Fast Decoupled")[2]
    solver.dc_loadflow(b, l)
    assert time.perf_counter() - t0 < 0.5    # v2.2: about 15 ms together
