"""v2.6 reference suite: GridLens against MATPOWER's answers on ten MATPOWER
cases, case9 to case2383wp. Reference values (tests/data/reference_pf.json)
come from PYPOWER's runpf / rundcpf, MATPOWER's algorithms in Python, on the
same .m files (tools/reference_pf.py). Gate of v2 phase 1: every case matches
and case2383wp solves in under 1 s."""
import json
import time
from pathlib import Path

import numpy as np
import pytest

import formats
import gridcore
from solver import dc_loadflow, solve_loadflow

DATA = Path(__file__).parent / "data"
REF = json.loads((DATA / "reference_pf.json").read_text())
CASES = [k for k in REF if k != "source"]
CFG = dict(method="Newton-Raphson", base=100.0, vmin=0.95, vmax=1.10, tol=1e-10,
           taps=True, shunts=True, qlim=False)


def _prep(name):
    c = formats.read_case(f"{name}.m", (DATA / f"{name}.m").read_text())
    b, l, probs, _ = gridcore.prep_case(c["bus"], c["lines"], dict(CFG, base=c["base"]))
    assert probs == []
    return b, l


def _ref(name, b, key):
    """Reference values for GridLens's bus rows (matched by bus number)."""
    at = dict(zip(REF[name]["bus"], REF[name][key]))
    return np.array([at[n] for n in b["Num"]])


@pytest.mark.parametrize("name", CASES)
def test_ac_load_flow_matches_matpower(name):
    b, l = _prep(name)
    res, flows, ok, hist = solve_loadflow(b, l, "Newton-Raphson", 1e-10)
    assert ok
    assert np.abs(res["V (pu)"] - _ref(name, b, "vm")).max() < 1e-9
    assert np.abs(res["Angle (deg)"] - _ref(name, b, "va")).max() < 1e-7


@pytest.mark.parametrize("name", CASES)
def test_dc_load_flow_matches_matpower(name):
    b, l = _prep(name)
    res = dc_loadflow(b, l)[0]
    assert np.abs(res["Angle (deg)"] - _ref(name, b, "va_dc")).max() < 1e-8


@pytest.mark.parametrize("name", CASES)
def test_generators_match_matpower(name):
    """P and Q of every generator in service (element model, MATPOWER's sharing).
    Where the reference has no Q (infinite Q limits; PYPOWER gives NaN there) the
    generator is alone at its bus and takes the bus's Q, as MATPOWER 6+ does."""
    case, _ = formats.read_matpower_model((DATA / f"{name}.m").read_text(), name)
    r = gridcore.solve_case(case, tol=1e-10)
    g, ref = r["gen"], REF[name]
    assert np.abs(g.loc[ref["gen"], "p"].to_numpy() - ref["pg"]).max() < 1e-6
    known = [q is not None for q in ref["qg"]]
    assert np.abs(g.loc[np.array(ref["gen"])[known], "q"].to_numpy()
                  - np.array(ref["qg"])[known].astype(float)).max() < 1e-6
    for gid in np.array(ref["gen"])[~np.array(known)]:
        bus = g.loc[gid, "bus"]
        assert (case.gen["bus"][case.gen["in_service"]] == bus).sum() == 1
        need = r["bus"].loc[bus, "q"] + r["load"]["q"][r["load"]["bus"] == bus].sum()
        assert g.loc[gid, "q"] == pytest.approx(need, abs=1e-9)


def test_gate_case2383wp_solves_in_under_a_second():
    b, l = _prep("case2383wp")
    t0 = time.perf_counter()
    res, flows, ok, hist = solve_loadflow(b, l)
    took = time.perf_counter() - t0
    assert ok and took < 1.0    # v1.6: 47.5 s; v2.6: about 0.07 s
