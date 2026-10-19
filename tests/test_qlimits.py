"""Generator Q limits (qlimits.py) around the unchanged solver."""
import numpy as np
import pytest

import units
from cases import CASES
from qlimits import solve_with_qlimits
from solver import solve_loadflow


@pytest.mark.parametrize("name", list(CASES))
def test_no_limits_gives_identical_results(name):
    bus, lines = CASES[name]
    r0, f0, ok0, _ = solve_loadflow(bus, lines)
    r1, f1, ok1, _, _, log = solve_with_qlimits(bus, lines)
    assert ok0 and ok1 and log == []
    assert np.array_equal(r0.to_numpy(), r1.to_numpy())
    assert np.array_equal(f0.to_numpy(), f1.to_numpy())


def test_pv_bus_switches_to_pq_at_qmax():
    e = units.EXAMPLE
    r = units.to_pu(e["sbase"], e["ref_bus"], e["ref_kv"], e["buses"],
                    e["lines"], e["trafos"])
    res, flows, ok, _, b, log = solve_with_qlimits(r["bus"], r["lines"])
    assert ok and [x["Bus"] for x in log] == [4]
    qg4 = res["Q_inj"].iloc[3] + r["bus"]["Qd"].iloc[3]
    assert qg4 == pytest.approx(0.25, abs=1e-6)          # held at Qmax
    assert res["V (pu)"].iloc[3] < 1.02                   # V drops below setpoint
    assert b["Type"].iloc[3] == "PQ"
