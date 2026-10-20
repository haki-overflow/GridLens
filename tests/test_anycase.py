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
