"""Case file import: MATPOWER .m, IEEE common data format, CSV templates.
Reference answers are MATPOWER's published runpf results."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import formats
import gridcore
from api.server import app

DATA = Path(__file__).parent / "data"
CFG = dict(method="Newton-Raphson", base=100.0, vmin=0.95, vmax=1.10, tol=1e-10,
           taps=True, shunts=True, qlim=False)


def _solve(case):
    b, l, probs, _ = gridcore.prep_case(case["bus"], case["lines"], dict(CFG, base=case["base"]))
    assert probs == []
    res, flows, ok, *_ = gridcore.loadflow(b, l, "Newton-Raphson", 1e-10)
    assert ok
    return res


def _mp(name):
    return formats.read_case(f"{name}.m", (DATA / f"{name}.m").read_text())


def test_matpower_case9_matches_runpf():
    res = _solve(_mp("case9"))
    vm = [1.040, 1.025, 1.025, 1.026, 1.013, 1.032, 1.016, 1.026, 0.996]
    va = [0.000, 9.280, 4.665, -2.217, -3.687, 1.967, 0.728, 3.720, -3.989]
    assert np.allclose(res["V (pu)"], vm, atol=5e-4)
    assert np.allclose(res["Angle (deg)"], va, atol=5e-4)


def test_matpower_case14_matches_runpf_and_the_preset():
    case = _mp("case14")
    res = _solve(case)
    vm = [1.060, 1.045, 1.010, 1.018, 1.020, 1.070, 1.062, 1.090, 1.056, 1.051, 1.057,
          1.055, 1.050, 1.036]
    va = [0.000, -4.983, -12.725, -10.313, -8.774, -14.221, -13.360, -13.360, -14.939,
          -15.097, -14.791, -15.076, -15.156, -16.034]
    assert np.allclose(res["V (pu)"], vm, atol=5e-4)
    assert np.allclose(res["Angle (deg)"], va, atol=5e-4)
    pre = _solve(dict(base=100.0, bus=gridcore.CASES["IEEE 14-bus"][0],
                      lines=gridcore.CASES["IEEE 14-bus"][1]))
    assert np.allclose(res["V (pu)"], pre["V (pu)"], atol=1e-4)


def test_matpower_case118_solves_near_the_stored_solution():
    case = _mp("case118")
    assert len(case["bus"]) == 118 and len(case["lines"]) == 186
    res = _solve(case)
    assert res["Angle (deg)"][68] == pytest.approx(30.0)         # slack bus 69 at 30 deg
    assert np.abs(res["V (pu)"] - case["bus"]["V"]).max() < 0.02
    assert np.abs(res["Angle (deg)"] - case["bus"]["Va"]).max() < 0.5


def _cdf_line(cols, width=128):
    """Place values at 1-based (start, end, text) column spans."""
    s = [" "] * width
    for a, b, txt in cols:
        txt = str(txt)
        assert len(txt) <= b - a + 1, (a, b, txt)
        s[b - len(txt):b] = txt                     # right-aligned like the archive files
    return "".join(s).rstrip()


def _to_cdf(case):
    """Write a case in IEEE common data format (columns as cdf2mpc reads them)."""
    base, bus, ln = case["base"], case["bus"], case["lines"]
    out = [_cdf_line([(32, 37, f"{base:.1f}"), (46, 60, "TEST CASE")])]
    out.append(f"BUS DATA FOLLOWS                            {len(bus)} ITEMS")
    code = {"PQ": 0, "PV": 2, "Slack": 3}
    for i, r in bus.iterrows():
        gen = r["Type"] != "PQ"
        out.append(_cdf_line([
            (1, 4, i + 1), (25, 26, code[r["Type"]]), (28, 33, f"{r['V']:.3f}"),
            (34, 40, f"{r['Va']:.2f}"), (41, 49, f"{r['Pd'] * base:.1f}"),
            (50, 59, f"{r['Qd'] * base:.1f}"), (60, 67, f"{r['Pg'] * base:.1f}"),
            (68, 75, f"{r['Qg'] * base:.1f}"), (77, 83, "0.0"),
            (85, 90, f"{r['V']:.3f}" if gen else "0.0"),
            (91, 98, f"{r['Qmax'] * base:.1f}" if gen else "0.0"),
            (99, 106, f"{r['Qmin'] * base:.1f}" if gen else "0.0"),
            (107, 114, f"{r['Gs']:.4f}"), (115, 122, f"{r['Bs']:.4f}")]))
    out += ["-999", f"BRANCH DATA FOLLOWS                         {len(ln)} ITEMS"]
    for _, r in ln.iterrows():
        out.append(_cdf_line([
            (1, 4, int(r["From"])), (6, 9, int(r["To"])), (19, 19, 1 if r["Kind"] == "trafo" else 0),
            (20, 29, f"{r['R']:.5f}"), (30, 40, f"{r['X']:.5f}"), (41, 50, f"{r['B']:.4f}"),
            (77, 82, f"{r['Tap'] if r['Kind'] == 'trafo' else 0:.3f}")]))
    out += ["-999", "END OF DATA"]
    return "\n".join(out)


def test_cdf_reads_what_matpower_case14_holds():
    mp = _mp("case14")
    cdf = formats.read_case("ieee14cdf.txt", _to_cdf(mp))
    assert len(cdf["bus"]) == 14 and len(cdf["lines"]) == 20
    for c in ("Pd", "Qd", "Pg", "Gs", "Bs", "V"):
        assert np.allclose(cdf["bus"][c], mp["bus"][c], atol=1e-3), c
    for c in ("From", "To", "R", "X", "B", "Tap"):
        assert np.allclose(cdf["lines"][c], mp["lines"][c], atol=1e-4), c
    assert np.allclose(_solve(cdf)["V (pu)"], _solve(mp)["V (pu)"], atol=1e-3)


def test_file_bus_numbers_with_gaps_become_rows():
    text = (DATA / "case9.m").read_text()
    for old, new in (("\n\t1\t", "\n\t101\t"), ("\n\t9\t", "\n\t909\t")):
        text = text.replace(old, new)
    text = text.replace("\t9\t4\t", "\t909\t4\t")
    case = formats.read_case("odd.m", text)
    assert case["bus"]["Num"].tolist()[:2] == [101, 2]
    assert case["lines"]["From"].max() <= 9
    assert any("Num column" in n for n in case["notes"])


def test_csv_templates():
    bus = "Type,V,Pg,Qg,Pd,Qd,Bs\nSlack,1.05,0,0,0,0,0\nPQ,1,0,0,0.5,0.2,0\n"
    lines = "From,To,R,X,B,Tap\n1,2,0.01,0.1,0,1\n"
    case = formats.read_case("mine.csv", lines, bus)        # either order works
    assert list(case["bus"]["Type"]) == ["Slack", "PQ"] and len(case["lines"]) == 1
    _solve(case)


def test_unknown_file_type_is_a_clear_error():
    with pytest.raises(ValueError, match="unknown file type"):
        formats.read_case("notes.docx", "hello")


def test_import_endpoint():
    c = TestClient(app)
    r = c.post("/api/import", json={"filename": "case9.m", "text": (DATA / "case9.m").read_text()})
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "case9" and d["problems"] == [] and len(d["bus"]) == 9
    assert d["settings"]["taps"] and d["settings"]["shunts"]
    s = c.post("/api/study", json={"bus": d["bus"], "lines": d["lines"], "settings": d["settings"],
                                   "name": d["name"]})
    assert s.status_code == 200 and s.json()["ok"]
    bad = c.post("/api/import", json={"filename": "x.m", "text": "nothing here"})
    assert bad.status_code == 422 and "Import failed" in bad.json()["problems"][0]
