"""n1.py (the fast N-1) against studies.contingency (the plain definition: take
a line out, solve the rest from a flat start): the same table on small cases
solved live, on case300 and case2383wp against tables the plain definition
made (tests/data/n1_*.csv.gz, tools/make_n1_reference.py), and the v2 phase 2
gate: all 2,896 outages of case2383wp in under 2 minutes."""
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import formats
import gridcore
import jobs
import n1
from gridcore import CASES
from solver import islands
from studies import contingency

DATA = Path(__file__).parent / "data"
TEXT = ["Outage", "Status", "Buses violating", "Lines overloaded", "Buses cut off"]
WHOLE = ["Violations", "Overloads", "Lost load (MW)"]
ROUNDED = ["Min V (pu)", "Loss (pu)"]      # to 4 decimals: the last bits of a solve may tip one
TIES = {"case2383wp": {"145-128"}}          # buses 145 and 146 share the lowest voltage to 1e-15


def prepared(name, qlim=False):
    c = formats.read_case(f"{name}.m", (DATA / f"{name}.m").read_text())
    return (*prep(c["bus"], c["lines"], c["base"], qlim), c["base"])


def prep(bus, lines, base=100.0, qlim=False, taps=True):
    b, l, probs, _ = gridcore.prep_case(bus, lines, dict(
        method="Newton-Raphson", base=base, vmin=0.95, vmax=1.1, tol=1e-8, taps=taps,
        shunts=taps, qlim=qlim))
    assert not probs, probs
    return b, l


def assert_same(fast, exact, ties=()):
    """Every cell of the exact table, in the exact order. Text, counts and the
    lost load must be equal, the rounded floats within one rounding unit and
    on all but a couple of rows within the solver's tolerance; At bus may
    differ only where two buses share the lowest voltage (ties)."""
    assert list(fast.columns) == list(exact.columns)
    assert list(fast["Outage"]) == list(exact["Outage"])
    for c in TEXT:
        assert (fast[c].astype(str).to_numpy() == exact[c].astype(str).to_numpy()).all(), c
    for c in WHOLE:
        assert np.array_equal(fast[c].to_numpy(float), exact[c].to_numpy(float), equal_nan=True), c
    for c in ROUNDED:
        d = np.abs(fast[c].to_numpy(float) - exact[c].to_numpy(float))
        assert np.nanmax(d, initial=0) <= 1.1e-4, c
        assert np.count_nonzero(d > 1e-9) <= 2, c
    a, b = fast["At bus"].to_numpy(float), exact["At bus"].to_numpy(float)
    differ = ~np.isclose(a, b, equal_nan=True)
    assert set(exact["Outage"][differ]) <= set(ties), exact.loc[differ, "Outage"].tolist()


# ------------------------------------------------- small cases, solved live
@pytest.mark.parametrize("qlim", [False, True])
@pytest.mark.parametrize("name", ["case9", "case14", "case24_ieee_rts", "case30", "case39", "case57"])
def test_matches_the_plain_definition(name, qlim):
    b, l, base = prepared(name, qlim)
    assert_same(n1.contingency(b, l, 0.95, 1.1, base, qlim),
                contingency(b, l, 0.95, 1.1, base, qlim))


def test_case118_matches_the_plain_definition():
    b, l, base = prepared("case118")
    fast = n1.contingency(b, l, 0.95, 1.1, base)
    assert_same(fast, contingency(b, l, 0.95, 1.1, base))
    assert (fast["Status"] == "ISLANDED").sum() == 9       # the bridges that cut a bus off


@pytest.mark.parametrize("qlim", [False, True])
@pytest.mark.parametrize("name", list(CASES))
def test_presets_match_the_plain_definition(name, qlim):
    bus, lines = CASES[name]
    b, l = prep(bus, lines, qlim=qlim, taps=False)
    assert_same(n1.contingency(b, l, 0.95, 1.1, 100.0, qlim),
                contingency(b, l, 0.95, 1.1, 100.0, qlim))


def case14():
    bus, lines = CASES["IEEE 14-bus"]
    return bus.copy(), lines.copy()


def check(bus, lines, qlim=False, base=100.0):
    b, l = prep(bus, lines, base, qlim)
    fast, exact = n1.contingency(b, l, 0.95, 1.1, base, qlim), contingency(b, l, 0.95, 1.1, base, qlim)
    assert_same(fast, exact)
    return fast


@pytest.mark.parametrize("qlim", [False, True])
def test_parallel_branches_out_of_service_lines_and_ratings(qlim):
    bus, lines = case14()
    lines = pd.concat([lines, lines.iloc[[2, 2, 9]]], ignore_index=True)   # twins of 2-3 and 5-6
    lines["InService"] = 1.0
    lines.loc[5, "InService"] = 0.0
    lines["Rate"] = 55.0                      # MVA: some lines overload in some outages
    fast = check(bus, lines, qlim)
    assert fast["Overloads"].fillna(0).gt(0).any() and (fast["Outage"] == "2-3 (3)").any()
    assert not fast["Outage"].str.startswith("3-4").any()      # the out-of-service line is not studied


def test_phase_shifters_and_taps():
    bus, lines = case14()
    lines["Shift"] = 0.0
    lines.loc[2, "Shift"] = 4.0
    lines.loc[11, "Shift"] = -3.0
    check(bus, lines)


def test_separate_islands_each_with_its_own_slack():
    (b9, l9), (b14, l14) = (CASES["5-bus (demo)"], CASES["IEEE 14-bus"])
    bus = pd.concat([b9, b14], ignore_index=True)[["Type", "V", "Pg", "Qg", "Pd", "Qd", "Bs"]]
    l14 = l14.assign(From=l14["From"] + len(b9), To=l14["To"] + len(b9))
    lines = pd.concat([l9, l14], ignore_index=True)
    fast = check(bus, lines)
    assert (fast["Status"] == "ISLANDED").sum() == 1 and len(fast) == len(l9) + len(l14)


def test_a_case_whose_base_does_not_solve_still_gets_its_table():
    bus, lines = case14()
    bus[["Pg", "Qg", "Pd", "Qd"]] = bus[["Pg", "Qg", "Pd", "Qd"]] * 7     # past the nose
    fast = check(bus, lines)
    assert (fast["Status"] == "FAILED").all() and (fast["Buses violating"] == "no solution (diverged)").all()


def test_every_outage_of_a_case_that_fails_after_some_outages():
    bus, lines = case14()
    bus[["Pg", "Qg", "Pd", "Qd"]] = bus[["Pg", "Qg", "Pd", "Qd"]] * 2.4   # some outages diverge, some not
    fast = check(bus, lines)
    assert set(fast["Status"]) >= {"OK", "FAILED"}


@pytest.mark.parametrize("name", ["case14", "case30", "case39", "case118"])
def test_the_buses_an_outage_cuts_off_are_what_islands_finds(name):
    b, l, _ = prepared(name)
    grid = n1.Grid(b, l)
    slack = b["Type"].to_numpy() == "Slack"
    for e, k in enumerate(grid.k):
        rest = l.drop(l.index[k]).reset_index(drop=True)
        want = sorted(i for isl in islands(len(b), rest) if not slack[isl].any() for i in isl)
        assert list(grid.cuts.get(e, grid.none_cut)) == want, (name, k)


def test_the_first_step_from_the_base_factors_is_the_exact_newton_step():
    """Only speed rides on it (a wrong first step is mended by the next ones),
    so it is checked directly: J^-1 f from the base factors and a small
    correction equals J^-1 f from a fresh factorisation."""
    b, l, _ = prepared("case118")
    g = n1.Grid(b, l)
    checked = 0
    for e in range(len(g.k)):
        if e in g.cuts:
            continue                                   # a bridge: too many slots change
        Yd = g.Yd0.copy()
        np.subtract.at(Yd, g.ypos[:, e], g.y4[:, e])
        Y, free = g.ybus(Yd), g.free(g.live(g.none_cut))
        E = np.exp(1j * g.thb)
        Vc = g.Vb * E
        I = Y @ Vc
        mis = Vc * np.conj(I) - g.S0
        f = np.where(free, np.r_[mis.real[g.ang], mis.imag[g.mag]], 0.0)
        J = g.jac.values(Yd, Vc, E, I, free)
        step = g.first_step(J, f)
        assert step is not None
        want = g.jac.solve(g.jac.factor(J), f)
        assert np.allclose(step, want, rtol=1e-7, atol=1e-10), e
        checked += 1
    assert checked > 150 and np.abs(want).max() > 1e-4     # a real step, on most branches


# --------------------------------------------------------- progress, cancel
def test_progress_counts_the_outages_and_a_raise_stops_the_run():
    b, l, base = prepared("case30")
    seen = []
    df = n1.contingency(b, l, 0.95, 1.1, base, progress=lambda d, t: seen.append((d, t)))
    total = len(l)
    assert seen == [(i, total) for i in range(total + 1)] and len(df) == total

    def stop_at(n, error):
        def progress(done, total):
            if done == n:
                raise error
        return progress

    for error in (jobs.Cancelled(), RuntimeError("stop")):     # never taken for an outage that failed
        with pytest.raises(type(error)):
            n1.contingency(b, l, 0.95, 1.1, base, progress=stop_at(5, error))


def test_run_study_has_the_plain_definitions_n1_table():
    bus, lines = CASES["IEEE 14-bus"]
    b, l = prep(bus, lines, taps=False)
    out = gridcore.run_study(b, l, "Newton-Raphson", 1e-8, 100.0, 0.95, 1.1)
    assert_same(out["n1"], contingency(b, l, 0.95, 1.1))


# -------------------------------------------- big cases, against stored tables
def stored(name, qlim):
    return pd.read_csv(DATA / f"n1_{name}{'_qlim' if qlim else ''}.csv.gz", keep_default_na=False,
                       na_values=[""], dtype={"Buses violating": str, "Lines overloaded": str,
                                              "Buses cut off": str})


@pytest.mark.parametrize("qlim", [False, True])
def test_case300_matches_the_stored_table(qlim):
    b, l, base = prepared("case300", qlim)
    fast = n1.contingency(b, l, 0.95, 1.1, base, qlim)
    exact = stored("case300", qlim)
    assert_same(fast, exact)
    assert {"OK", "ISLANDED", "FAILED"} == set(fast["Status"])    # every kind of row is there


def test_gate_case2383wp_all_outages_in_under_two_minutes():
    b, l, base = prepared("case2383wp")
    t = time.perf_counter()
    fast = n1.contingency(b, l, 0.95, 1.1, base)
    took = time.perf_counter() - t
    assert len(fast) == 2896 and took < 120, f"{took:.0f} s"
    assert_same(fast, stored("case2383wp", False), TIES["case2383wp"])
    assert fast["Status"].value_counts().to_dict() == {"OK": 2250, "ISLANDED": 644, "FAILED": 2}


@pytest.mark.skipif(not os.environ.get("GRIDLENS_BIG"), reason="36 s; set GRIDLENS_BIG=1")
def test_case2383wp_with_q_limits_matches_the_stored_table():
    b, l, base = prepared("case2383wp", True)
    t = time.perf_counter()
    fast = n1.contingency(b, l, 0.95, 1.1, base, True)
    assert time.perf_counter() - t < 120
    assert_same(fast, stored("case2383wp", True))
    assert fast["Status"].value_counts().to_dict() == {"OK": 2241, "ISLANDED": 644, "FAILED": 11}
