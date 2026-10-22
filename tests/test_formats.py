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


# ------------------------------------------------------------ layout of big cases
import figures


def _layout(case):
    l = case["lines"]
    edges = [(int(a) - 1, int(b) - 1) for a, b in zip(l["From"], l["To"])]
    return figures.layout(len(case["bus"]), edges, case["bus"]), edges


@pytest.mark.parametrize("name", ["case30", "case118"])
def test_big_layout_is_tidy_and_deterministic(name):
    g, edges = _layout(_mp(name))
    g2, _ = _layout(_mp(name))
    assert np.array_equal(g["cx"], g2["cx"]) and np.array_equal(g["cy"], g2["cy"])
    cx, cy, w = np.asarray(g["cx"]), np.asarray(g["cy"]), np.asarray(g["w"])
    for r in np.unique(cy):                       # bars in a row never overlap
        row = np.flatnonzero(cy == r)
        order = row[np.argsort(cx[row])]
        gaps = (cx[order][1:] - w[order][1:] / 2) - (cx[order][:-1] + w[order][:-1] / 2)
        assert (gaps > 1.0).all()
    aspect = np.ptp(cx) / np.ptp(cy)
    assert 1.0 < aspect < 3.0
    assert len(g["routes"]) == len(edges) and all(len(r) == 2 for r in g["routes"])


def _bfs_hops(n, edges):
    """The plain breadth-first hop counts that figures._hops replaced (v2.10)."""
    adj = [[] for _ in range(n)]
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    D = np.full((n, n), np.inf)
    for s in range(n):
        D[s, s], todo = 0, [s]
        while todo:
            nxt = []
            for i in todo:
                for j in adj[i]:
                    if D[s, j] == np.inf:
                        D[s, j] = D[s, i] + 1
                        nxt.append(j)
            todo = nxt
    return D


def test_hop_counts_are_breadth_first_hops_and_islands_sit_apart():
    _, edges = _layout(_mp("case118"))
    edges = edges + [(118, 119), (119, 120)]          # a 3-bus island
    D = figures._hops(121, edges)
    plain = _bfs_hops(121, edges)
    fin = np.isfinite(plain)
    assert np.array_equal(D[fin], plain[fin]) and (D[~fin] == plain[fin].max() + 2).all()


def _plain_step(X, D):
    """The textbook Guttman step: pinv(V) B(X) X with an SVD pseudo-inverse."""
    n = len(D)
    W = np.where(D > 0, 1.0 / np.where(D > 0, D, 1) ** 2, 0.0)
    V = np.diag(W.sum(axis=1)) - W
    dist = np.linalg.norm(X[:, None] - X[None], axis=-1)
    B = -W * D / np.where(dist > 0, dist, 1)
    np.fill_diagonal(B, 0.0)
    np.fill_diagonal(B, -B.sum(axis=1))
    return np.linalg.pinv(V) @ (B @ X)


@pytest.mark.parametrize("name", ["case30", "case118"])
def test_a_stress_step_is_the_textbook_guttman_transform(name):
    g, edges = _layout(_mp(name))
    n = len(g["cx"])
    D = figures._hops(n, edges)
    X = figures._stress(D, iters=5)                    # past the start, no two buses on one spot
    WD, Vp = figures._majorizer(D)
    assert np.allclose(figures._smacof(X, WD, Vp), _plain_step(X, D), rtol=1e-9, atol=1e-9)


def _stress_value(X, D):
    i, j = np.triu_indices(len(D), 1)
    return np.sum((np.linalg.norm(X[i] - X[j], axis=1) - D[i, j]) ** 2 / D[i, j] ** 2)


def test_the_stress_layout_lowers_the_stress_and_keeps_its_shape_when_buses_are_renumbered():
    from scipy.spatial.distance import pdist
    _, edges = _layout(_mp("case118"))
    D = figures._hops(118, edges)
    start, X = figures._stress(D, iters=0), figures._stress(D)
    assert _stress_value(X, D) < 0.5 * _stress_value(start, D)
    # v2.10: buses that start on one spot are parted by a fixed nudge, not by
    # round-off, so the drawing does not hinge on bus order or on the BLAS used
    Xb = figures._stress(D[::-1, ::-1])[::-1]          # buses in reverse order
    assert np.abs(pdist(X) - pdist(Xb)).max() < 1e-3   # the same shape (distances about 6)


def test_the_layout_of_a_big_case_takes_seconds():
    import time
    case = _mp("case1354pegase")
    t = time.perf_counter()
    g, _ = _layout(case)
    assert len(g["cx"]) == 1354 and time.perf_counter() - t < 20   # v2.9: 27 s, v2.10: 4 s


def test_small_networks_keep_the_layered_drawing():
    bus, lines = gridcore.CASES["5-bus (demo)"]
    edges = [(int(a) - 1, int(b) - 1) for a, b in zip(lines["From"], lines["To"])]
    g = figures.layout(5, edges, bus)
    assert sorted(set(np.round(g["cy"], 6))) == [0.0, 5.0, 10.0]   # rows by distance from the slack


def test_matpower_case300_imports_with_its_series_capacitor():
    # v2.3: negative X is accepted (case300 has one series capacitor, X = -0.3697 pu)
    case = _mp("case300")
    b, l, probs, _ = gridcore.prep_case(case["bus"], case["lines"], dict(CFG, base=case["base"]))
    assert probs == [] and (l["X"] < 0).sum() == 1
    res, flows, ok, hist = gridcore.loadflow(b, l, "Newton-Raphson", 1e-10)[:4]
    assert ok and len(hist) - 1 <= 6
