"""API: every endpoint on the 5-bus preset answers 200 with the same values
as calling the Python functions directly; bad data gives 422 + problems;
floats survive the JSON round trip exactly."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import dispatch as D
import gridcore
import figures
import seqfaults as SF
import symcomp as SC
import tline as TL
import units
import working as W
from api.schema import to_json
from api.server import app
from cases import CASES
from solver import build_ybus, solve_loadflow
from studies import fault_analysis

NAME = "5-bus (demo)"
CFG = dict(method="Newton-Raphson", base=100.0, vmin=0.95, vmax=1.10,
           tol=1e-8, taps=False, shunts=False, qlim=False)
client = TestClient(app)


@pytest.fixture(scope="module")
def case():
    r = client.get(f"/api/case/{NAME}")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def prepped():
    b, l, probs, _ = gridcore.prep_case(*CASES[NAME], CFG)
    assert not probs
    return b, l


def post(path, body):
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_cases_and_case(case):
    assert client.get("/api/cases").json()["cases"] == list(CASES)
    assert case["bus"] == to_json(CASES[NAME][0])
    assert client.get("/api/case/nope").status_code == 404


def test_validate(case):
    assert post("/api/validate", case) == {"problems": [], "notes": []}


def test_study_matches_and_round_trip_is_exact(case, prepped):
    out = post("/api/study", case)
    ref = gridcore.run_study(*prepped, "Newton-Raphson", 1e-8, 100.0, 0.95, 1.10)
    assert out["res"] == to_json(ref["res"])
    assert out["flows"] == to_json(ref["flows"])
    assert out["n1"] == to_json(ref["n1"])
    assert out["cmp"] == to_json(ref["cmp"])
    assert out["pv"]["lambda_max"] == ref["pv"][1]
    assert out["its"] == ref["its"] and out["ok"] == ref["ok"]
    # exact float round trip: JSON value == the solver's double, bit for bit
    v = pd.DataFrame(out["res"])["V (pu)"].to_numpy()
    assert np.array_equal(v, ref["res"]["V (pu)"].to_numpy())
    assert out["loss"] == ref["loss"] and out["slack_p"] == ref["slack_p"]


def test_study_bad_case_is_422(case):
    bad = dict(case, bus=[dict(r, Type="PQ") for r in case["bus"]])
    r = client.post("/api/study", json=bad)
    assert r.status_code == 422
    assert r.json()["problems"] == [
        "No Slack bus: set exactly one bus Type to Slack."]
    assert "Traceback" not in r.text


def test_malformed_body_is_422_without_trace():
    r = client.post("/api/study", json={"bus": "x"})
    assert r.status_code == 422 and "problems" in r.json()


def test_layout(case, prepped):
    b, l = prepped
    edges = [(int(f) - 1, int(t) - 1) for f, t in zip(l["From"], l["To"])]
    assert post("/api/layout", case) == to_json(figures.layout(len(b), edges, b))


def test_outage(case, prepped):
    out = post("/api/outage/0", case)
    res, flows, ok, hist = gridcore.outage(*prepped, 0)
    assert out["res"] == to_json(res) and out["flows"] == to_json(flows)
    assert out["ok"] == ok
    assert client.post("/api/outage/99", json=case).status_code == 422


def test_fault(case, prepped):
    b, l = prepped
    res = solve_loadflow(b, l, "Newton-Raphson", 1e-8)[0]
    tbl, Z, V0, If = fault_analysis(b, l, res, 0.2, 0.0, 100.0, 33.0)
    out = post("/api/fault", {"case": case, "xd": 0.2, "zf": 0.0, "kv": 33.0})
    assert out["table"] == to_json(tbl) and out["If"] == to_json(If)


def test_seqfault(case, prepped):
    b, l = prepped
    g, br = SF.seed_tables(b, l)
    vf, kv = np.ones(len(b), complex), np.full(len(b), 33.0)
    r = SF.solve_fault("SLG", 1, g, br, vf, 0j, 100.0, kv)
    out = post("/api/seqfault", {"case": case, "kind": "SLG", "bus": 1})
    assert out["Iabc"] == to_json(r["Iabc"]) and out["kA"] == to_json(r["kA"])
    assert out["table"] == to_json(SF.fault_table("SLG", g, br, vf, 0j, 100.0, kv))
    # SLG = 3 Vf / (Z1 + Z2 + Z0)
    I = out["Iabc"][0]
    assert abs(complex(I["re"], I["im"]) - 3 / sum(r["Zth"])) < 1e-12


def test_ybus(case, prepped):
    b, l = prepped
    out = post("/api/ybus", case)
    assert out["parts"] == to_json(W.ybus_parts(b, l))
    assert out["Y"] == to_json(build_ybus(len(b), l, b))


@pytest.mark.parametrize("method", ["Newton-Raphson", "Gauss-Seidel",
                                    "Fast Decoupled"])
def test_iterations(case, prepped, method):
    b, l = prepped
    out = post("/api/iterations", {"case": case, "method": method})
    ref = {"Newton-Raphson": lambda: W.newton_trace(b, l, 1e-8),
           "Gauss-Seidel": lambda: W.gauss_seidel_trace(b, l, 1.0, 1e-6, 2000),
           "Fast Decoupled": lambda: W.fast_decoupled_trace(b, l, 1e-8)}[method]()
    assert out["trace"] == to_json(ref)


def test_answer(case, prepped):
    b, l = prepped
    res, flows, _, _ = solve_loadflow(b, l, "Newton-Raphson", 1e-8)
    text = W.answer_text(b, l, res, flows, 100.0, "Newton-Raphson",
                         W.trace_lines("Newton-Raphson", b, l, tol=1e-8, show=2))
    assert post("/api/answer", {"case": case})["text"] == text


def test_dispatch():
    e = D.EXAMPLE
    body = {"units": to_json(e["units"]), "PD": e["PD"], "B": e["B"],
            "B0": e["B0"], "B00": e["B00"], "pu_base": e["base"]}
    B, B0, B00 = D.b_from_pu(e["B"], e["B0"], e["B00"], e["base"])
    ref = D.dispatch(e["units"], e["PD"], B, B0, B00)
    assert post("/api/dispatch", body) == to_json(ref)


def test_symcomp():
    abc = [{"mag": 1.0, "deg": 0.0}, {"mag": 0.8, "deg": -110.0},
           {"mag": 1.1, "deg": 125.0}]
    out = post("/api/symcomp", {"abc": abc, "s012": [0, 1, 0]})
    ref = SC.to_sequence([SC.polar(1.0, 0.0), SC.polar(0.8, -110.0),
                          SC.polar(1.1, 125.0)])
    assert out["s012"] == to_json(ref)
    assert out["abc"] == to_json(SC.to_phase([0, 1, 0]))
    assert client.post("/api/symcomp", json={}).status_code == 422


def test_tline():
    p = dict(model="long", R=0.1, X=0.5, B_uS=3.2, length=300.0, VR_kV=220.0,
             PR_MW=150.0, pf=0.85, lagging=True)
    out = post("/api/tline", p)
    assert out["performance"] == to_json(TL.performance(**p))
    A, B, C, Dd = TL.abcd("long", 0.1, 0.5, 3.2, 300.0)
    assert out["abcd"] == to_json(dict(A=A, B=B, C=C, D=Dd))


def test_topu():
    e = units.EXAMPLE
    body = {"sbase": e["sbase"], "ref_bus": e["ref_bus"], "ref_kv": e["ref_kv"],
            "buses": to_json(e["buses"]), "lines": to_json(e["lines"]),
            "trafos": to_json(e["trafos"])}
    ref = units.to_pu(e["sbase"], e["ref_bus"], e["ref_kv"], e["buses"],
                      e["lines"], e["trafos"])
    assert post("/api/topu", body) == to_json(ref)


def test_root_redirects_to_docs_without_web_build(tmp_path, monkeypatch):
    import api.server as srv
    monkeypatch.setattr(srv, "DIST", tmp_path / "missing")
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/docs"


def test_root_serves_web_build(tmp_path, monkeypatch):
    import api.server as srv
    (tmp_path / "index.html").write_text("<!doctype html><title>GridLens</title>")
    monkeypatch.setattr(srv, "DIST", tmp_path)
    r = client.get("/")
    assert r.status_code == 200 and "GridLens" in r.text
    assert client.get("/api/cases").status_code == 200   # API still wins


# ------------------------------------------------- workspace extras (v1.3)
def test_units_example_matches_module():
    d = client.get("/api/units/example").json()
    assert d["sbase"] == units.EXAMPLE["sbase"] and d["ref_bus"] == units.EXAMPLE["ref_bus"]
    assert d["z_units"] == list(units.Z_UNITS) and d["b_units"] == list(units.B_UNITS)
    body = dict(sbase=d["sbase"], ref_bus=d["ref_bus"], ref_kv=d["ref_kv"],
                buses=d["buses"], lines=d["lines"], trafos=d["trafos"])
    r = client.post("/api/topu", json=body)
    assert r.status_code == 200 and len(r.json()["bus"]) == len(d["buses"])


def test_lm_models_empty_without_server(monkeypatch):
    import ai_report
    monkeypatch.setattr(ai_report, "lm_models", lambda url=None: [])
    assert client.get("/api/lm/models").json()["models"] == []


def test_report_says_when_lm_studio_is_down(monkeypatch):
    import ai_report
    import requests

    def down(*a, **k):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(ai_report, "ai_report", down)
    r = client.post("/api/report", json={"summary": "x", "model": "m"})
    assert r.status_code == 422 and "not reachable" in r.json()["problems"][0]


def test_report_returns_the_models_text(monkeypatch):
    import ai_report
    monkeypatch.setattr(ai_report, "ai_report", lambda s, m: f"{m}:{s}")
    assert client.post("/api/report", json={"summary": "S", "model": "M"}).json() == {"text": "M:S"}
