"""v2.4: the element model (model.py): stable IDs, conversion to and from the
v1 tables, the MATPOWER reader on top of it, results keyed by element ID."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import formats
import gridcore
import model
from gridcore import CASES

DATA = Path(__file__).parent / "data"
CFG = dict(method="Newton-Raphson", base=100.0, vmin=0.95, vmax=1.10, tol=1e-8,
           taps=True, shunts=True, qlim=False)


def _tables(name):
    if name in CASES:
        bus, lines, base = *CASES[name], 100.0
    else:
        c = formats.read_case(f"{name}.m", (DATA / f"{name}.m").read_text())
        bus, lines, base = c["bus"], c["lines"], c["base"]
    b, l, probs, _ = gridcore.prep_case(bus, lines, dict(CFG, base=base))
    assert probs == []
    return b, l, base


def _mp(name):
    return formats.read_matpower_model((DATA / f"{name}.m").read_text(), name)[0]


@pytest.mark.parametrize("name", list(CASES) + ["case9", "case30", "case118", "case300"])
def test_v1_tables_round_trip(name):
    """v1 tables -> model -> v1 tables: the same per-unit data (MW and back can
    move the last bit) and the same load flow."""
    b, l, base = _tables(name)
    case = model.from_tables(b, l, base)
    assert model.check_ids(case) == []
    b2, l2 = model.to_tables(case)
    assert (b2["Type"].to_numpy() == b["Type"].to_numpy()).all()
    for c in ("V", "Pg", "Qg", "Pd", "Qd", "Gs", "Bs"):
        assert np.allclose(b2[c], b[c], rtol=0, atol=1e-15), c
    for c in ("From", "To", "R", "X", "B", "Tap", "Shift", "Rate", "InService"):
        assert (l2[c].to_numpy(float) == l[c].to_numpy(float)).all(), c
    r1 = gridcore.loadflow(b, l, "Newton-Raphson", 1e-10)[0]
    r2 = gridcore.loadflow(*gridcore.prep_case(b2, l2, dict(CFG, base=base))[:2],
                           "Newton-Raphson", 1e-10)[0]
    assert np.abs(r1["V (pu)"] - r2["V (pu)"]).max() < 1e-12


def test_matpower_reader_keeps_every_generator():
    case = _mp("case24_ieee_rts")
    assert len(case.gen) == 33 and (case.gen["bus"] == "bus15").sum() == 6
    bus, lines = model.to_tables(case)            # what read_case gives: summed per bus
    v1 = formats.read_case("case24_ieee_rts.m", (DATA / "case24_ieee_rts.m").read_text())
    assert_frame_equal(v1["bus"], bus[formats.BUS_COLS])
    assert bus["Pg"].iloc[14] == pytest.approx(case.gen[case.gen["bus"] == "bus15"]["p"].sum() / 100)


def test_generators_share_like_matpower():
    """At a Slack or PV bus the bus's Q is shared in proportion to the Q ranges and
    the Slack's first generator takes the P balance (MATPOWER pfsoln). Reference:
    PYPOWER 5.1.21 runpf (MATPOWER's algorithm) on case24_ieee_rts."""
    r = gridcore.solve_case(_mp("case24_ieee_rts"), tol=1e-10)
    g = r["gen"]
    assert g.loc[["gen12", "gen13", "gen14"], "p"].tolist() == pytest.approx(
        [-2.953585, 95.1, 95.1], abs=1e-5)                      # bus 13, the Slack
    assert g.loc[["gen12", "gen13", "gen14"], "q"].tolist() == pytest.approx([44.663844] * 3, abs=1e-5)
    assert g.loc[["gen16", "gen21"], "q"].tolist() == pytest.approx([1.726706, -12.588031], abs=1e-5)


def test_results_balance_and_follow_ids():
    case = _mp("case118")
    r = gridcore.solve_case(case, tol=1e-10)
    loss_p, loss_q = r["branch"]["loss_p"].sum(), r["branch"]["loss_q"].sum()
    assert r["gen"]["p"].sum() - r["load"]["p"].sum() - r["shunt"]["p"].sum() == pytest.approx(loss_p, abs=1e-6)
    assert r["gen"]["q"].sum() - r["load"]["q"].sum() - r["shunt"]["q"].sum() == pytest.approx(loss_q, abs=1e-6)
    assert r["bus"].loc["bus69", "va"] == pytest.approx(30.0)    # the Slack keeps its angle
    # take a branch out of the table: every other result keeps its id
    gone = case.branch["id"].iloc[2]
    case.branch = case.branch.drop(index=2).reset_index(drop=True)
    r2 = gridcore.solve_case(case, tol=1e-10)
    assert gone not in r2["branch"].index
    assert list(r2["branch"].index) == [i for i in r["branch"].index if i != gone]
    assert (r2["branch"]["from_bus"] == r["branch"]["from_bus"].drop(gone)).all()
    assert list(r2["gen"].index) == list(r["gen"].index)


def test_new_id_and_id_checks():
    case = _mp("case9")
    assert model.new_id(case, "load") == "load4" and model.new_id(case, "trafo") == "trafo1"
    case.load = pd.concat([case.load, model.table("load", [dict(id="load1", bus="bus99")])],
                          ignore_index=True)
    assert model.check_ids(case) == [
        "Duplicate element ids: load1.", "Load elements refer to buses that do not exist: load1."]


def test_dict_round_trip_and_problems_from_solve_case():
    case = _mp("case30")
    back = model.from_dict(json.loads(json.dumps(model.to_dict(case))))  # plain JSON
    for k in model.KINDS:
        assert_frame_equal(getattr(back, k), getattr(case, k), check_dtype=False)
    case.branch.loc[0, ["r", "x"]] = 0.0
    with pytest.raises(ValueError, match="Series impedance must not be zero"):
        gridcore.solve_case(case)
