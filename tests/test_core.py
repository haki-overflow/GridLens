"""gridcore: the pure study must give exactly what the snapshot holds.
tests/data/core_golden.pkl holds res, flows, ok, iterations, cmp, n1 and pv
for both presets with default settings and with generator Q limits on. It was
taken from app._study at 52e819d (before the move-only refactor) and
regenerated at v2.1 (sparse Newton-Raphson, every value within 1e-13 of the
old one). Regenerate (only after an approved maths change):
GOLDEN_WRITE=1 pytest tests/test_core.py"""
import os
import pickle
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

import gridcore
from gridcore import CASES

GOLDEN_FILE = Path(__file__).parent / "data" / "core_golden.pkl"
GOLDEN = pickle.loads(GOLDEN_FILE.read_bytes())
CFG = dict(method="Newton-Raphson", base=100.0, vmin=0.95, vmax=1.10,
           tol=1e-8, taps=False, shunts=False, qlim=False)


def _run(name, qlim):
    cfg = dict(CFG, qlim=qlim)
    b, l, probs, _ = gridcore.prep_case(*CASES[name], cfg)
    assert probs == []
    return gridcore.run_study(b, l, cfg["method"], cfg["tol"], cfg["base"],
                              cfg["vmin"], cfg["vmax"], qlim)


@pytest.mark.parametrize("qlim", [False, True])
@pytest.mark.parametrize("name", list(CASES))
def test_run_study_matches_previous_app(name, qlim):
    out = _run(name, qlim)
    if os.environ.get("GOLDEN_WRITE"):
        GOLDEN[(name, qlim)] = {k: out[k] for k in ("res", "flows", "ok", "its", "cmp",
                                                   "n1", "pv")}
        GOLDEN_FILE.write_bytes(pickle.dumps(GOLDEN))
        pytest.skip("snapshot written")
    ref = GOLDEN[(name, qlim)]
    for k in ("res", "flows", "cmp", "n1"):   # later versions may add columns, never change old ones
        assert_frame_equal(out[k][list(ref[k].columns)], ref[k], check_exact=True)
    assert_frame_equal(out["pv"][0], ref["pv"][0], check_exact=True)
    assert out["pv"][1] == ref["pv"][1]
    assert out["ok"] == ref["ok"]
    assert out["its"] == ref["its"]


def test_outage_is_the_case_without_that_line():
    b, l, _, _ = gridcore.prep_case(*CASES["5-bus (demo)"], CFG)
    res, flows, ok, _ = gridcore.outage(b, l, 0)
    assert ok and len(flows) == len(l) - 1


def _probs(bus, lines):
    return gridcore.prep_case(bus, lines, CFG)[2]


B5, L5 = CASES["5-bus (demo)"]


def test_problem_no_slack():
    bus = B5.assign(Type=["PQ"] + list(B5["Type"][1:]))
    assert _probs(bus, L5) == ["No Slack bus: set exactly one bus Type to Slack."]


def test_problem_two_slacks():
    bus = B5.assign(Type=["Slack", "Slack"] + list(B5["Type"][2:]))
    assert _probs(bus, L5) == [
        "More than one Slack bus (buses 1, 2); exactly one required."]


def test_problem_zero_x():
    lines = L5.assign(X=[0.0] + list(L5["X"][1:]))
    assert _probs(B5, lines) == [
        "Series reactance X must be greater than 0 (lines 1-2)."]


def test_problem_line_to_missing_bus():
    extra = pd.DataFrame([dict(From=2, To=9, R=0.01, X=0.1, B=0.0, Tap=1.0)])
    lines = pd.concat([L5, extra], ignore_index=True)
    assert _probs(B5, lines) == [
        "Lines reference buses that do not exist (buses run from 1 to N in "
        "row order): row 8: To = 9"]


def test_problem_disconnected():
    keep = ~(((L5["From"] == 4) & (L5["To"] == 5)) |
             ((L5["From"] == 2) & (L5["To"] == 5)))
    assert _probs(B5, L5[keep].reset_index(drop=True)) == [
        "Network is disconnected: buses 5 have no path to a Slack bus. Connect them, "
        "or make one of them the Slack bus of its own island."]


def test_problem_no_lines_yet():
    # a new drawing: one bus, an empty line table with no columns at all
    bus = B5.iloc[:1].reset_index(drop=True)
    assert _probs(bus, pd.DataFrame()) == [
        "There are no lines: add at least one line between two buses."]


def test_problem_no_buses():
    assert _probs(pd.DataFrame(), L5)[0] == "There are no buses: every row needs a Type."
