"""Background jobs (v2.8): jobs.py runs work on one worker thread with
progress and cancel; the studies report progress and never swallow a
cancel; /api/jobs gives exactly what /api/study gives."""
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import figures
import gridcore
import jobs
from api.schema import frame, to_json
from api.server import app
from gridcore import CASES, STAGES
from studies import contingency, pv_curve

DATA = Path(__file__).parent / "data"
client = TestClient(app)
CFG = dict(method="Newton-Raphson", base=100.0, vmin=0.95, vmax=1.10, tol=1e-8,
           taps=False, shunts=False, qlim=False)
END = ("done", "failed", "cancelled")


def wait(job_id, until=END, timeout=30.0):
    """Poll jobs.get until the status is in `until`."""
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        s = jobs.get(job_id)
        if s["status"] in until:
            return s
        time.sleep(0.005)
    raise AssertionError(f"job {job_id} still {jobs.get(job_id)['status']}")


def poll(job_id, timeout=60.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        s = client.get(f"/api/jobs/{job_id}").json()
        if s["status"] in END:
            return s
        time.sleep(0.01)
    raise AssertionError("job did not finish")


class Boom(Exception):
    problems = ["first", "second"]


# ------------------------------------------------------------- jobs.py
def test_job_reports_progress_and_result():
    gate = threading.Event()

    def work(progress):
        progress("Counting", 0, 4)
        progress("Counting", 3, 4)
        gate.wait(5)
        return {"answer": 42}

    j = jobs.start("test", work)
    assert j["status"] in ("queued", "running") and "result" not in j
    s = wait(j["id"], until=("running",))
    for _ in range(500):
        s = jobs.get(j["id"])
        if s["done"] == 3:
            break
        time.sleep(0.002)
    assert (s["stage"], s["done"], s["total"]) == ("Counting", 3, 4)
    assert s["eta"] is not None and s["eta"] >= 0 and "result" not in s
    gate.set()
    s = wait(j["id"])
    assert s["status"] == "done" and s["result"] == {"answer": 42} and s["eta"] is None
    assert s["elapsed"] >= 0
    assert all("result" not in x for x in jobs.listing())


def test_cancel_stops_a_running_job_at_its_next_progress_call():
    calls = []

    def work(progress):
        for i in range(10_000):
            progress("Loop", i, 10_000)
            calls.append(i)
            time.sleep(0.001)
        return "finished"

    j = jobs.start("test", work)
    wait(j["id"], until=("running",))
    while not calls:
        time.sleep(0.001)
    jobs.cancel(j["id"])
    s = wait(j["id"])
    assert s["status"] == "cancelled" and "result" not in s
    assert len(calls) < 10_000


def test_jobs_run_one_at_a_time_in_order_and_a_queued_one_cancels_at_once():
    gate, order = threading.Event(), []
    a = jobs.start("test", lambda p: (gate.wait(5), order.append("a")))
    b = jobs.start("test", lambda p: order.append("b"))
    c = jobs.start("test", lambda p: order.append("c"))
    assert jobs.get(b["id"])["status"] == "queued"
    assert jobs.cancel(b["id"])["status"] == "cancelled"
    gate.set()
    assert wait(c["id"])["status"] == "done"
    assert wait(a["id"])["status"] == "done"
    assert order == ["a", "c"] and jobs.get(b["id"])["status"] == "cancelled"


def test_a_cancelled_job_stuck_in_a_long_step_does_not_hold_up_its_kind():
    inside, gate, after = threading.Event(), threading.Event(), []

    def long_step(progress):
        progress("One big factorisation", 0, 1)
        inside.set()
        gate.wait(5)                  # no progress call for a long time
        after.append("finished")
        return "dropped"

    a = jobs.start("long", long_step)
    b = jobs.start("long", lambda p: "next")
    inside.wait(5)
    assert jobs.get(b["id"])["status"] == "queued"
    assert jobs.cancel(a["id"])["status"] == "cancelled"
    assert wait(b["id"])["result"] == "next"      # did not wait for a's long step
    assert not after
    gate.set()
    time.sleep(0.05)
    s = jobs.get(a["id"])
    assert after == ["finished"] and s["status"] == "cancelled" and "result" not in s


def test_each_kind_has_its_own_worker_so_a_layout_never_blocks_a_study():
    gate = threading.Event()
    slow = jobs.start("slow-kind", lambda p: gate.wait(5))
    quick = jobs.start("quick-kind", lambda p: "ok")
    assert wait(quick["id"])["result"] == "ok"
    assert jobs.get(slow["id"])["status"] == "running"
    gate.set()
    assert wait(slow["id"])["status"] == "done"


def test_a_failing_job_keeps_its_problems():
    j = jobs.start("test", lambda p: (_ for _ in ()).throw(ValueError("bad data")))
    s = wait(j["id"])
    assert s["status"] == "failed" and s["problems"] == ["bad data"] and "result" not in s
    s = wait(jobs.start("test", lambda p: (_ for _ in ()).throw(Boom()))["id"])
    assert s["problems"] == ["first", "second"]


def test_only_the_last_finished_jobs_are_kept():
    ids = []
    for _ in range(jobs.KEEP + 3):
        ids.append(jobs.start("test", lambda p: None)["id"])
        wait(ids[-1])
    gate = threading.Event()
    held = jobs.start("test", lambda p: gate.wait(5))   # running jobs are never dropped
    assert len(jobs.listing()) <= jobs.KEEP + 1 and jobs.get(held["id"]) is not None
    assert jobs.get(ids[-1]) is not None
    assert jobs.get(ids[0]) is None and jobs.cancel(ids[0]) is None
    gate.set()
    wait(held["id"])


# ------------------------------------------------------------ the studies
@pytest.fixture(scope="module")
def ieee14():
    bus, lines = CASES["IEEE 14-bus"]
    lines = lines.copy()
    lines["InService"] = 1.0
    lines.loc[3, "InService"] = 0.0           # 19 outages to study
    b, l, probs, _ = gridcore.prep_case(bus, lines, CFG)
    assert not probs
    return b, l


def test_contingency_progress_counts_every_outage_and_changes_nothing(ieee14):
    b, l = ieee14
    seen = []
    df = contingency(b, l, 0.95, 1.1, progress=lambda d, t: seen.append((d, t)))
    assert seen == [(i, 19) for i in range(20)]
    assert df.equals(contingency(b, l, 0.95, 1.1))


def test_a_cancel_from_progress_is_not_an_outage_that_failed(ieee14):
    b, l = ieee14

    def progress(done, total):
        if done == 3:
            raise jobs.Cancelled

    with pytest.raises(jobs.Cancelled):
        contingency(b, l, 0.95, 1.1, progress=progress)
    with pytest.raises(jobs.Cancelled):
        pv_curve(b, l, progress=progress)


def test_pv_curve_reports_points_without_a_total(ieee14):
    b, l = ieee14
    seen = []
    curve, lam = pv_curve(b, l, progress=lambda d, t: seen.append((d, t)))
    assert all(t is None for _, t in seen)
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)
    assert seen[-1][0] == len(curve)


def test_run_study_goes_through_the_stages_in_order(ieee14):
    b, l = ieee14
    stages = []
    out = gridcore.run_study(b, l, "Newton-Raphson", 1e-8, 100.0, 0.95, 1.1,
                             progress=lambda s, d, t: stages.append(s))
    assert list(dict.fromkeys(stages)) == list(STAGES)
    ref = gridcore.run_study(b, l, "Newton-Raphson", 1e-8, 100.0, 0.95, 1.1)
    assert out["n1"].equals(ref["n1"]) and out["pv"][0].equals(ref["pv"][0])


@pytest.fixture(scope="module")
def case118():
    """IEEE 118 as the API sees it (no bus positions: the stress layout)."""
    r = client.post("/api/import", json={"filename": "case118.m",
                                         "text": (DATA / "case118.m").read_text()})
    assert r.status_code == 200
    d = r.json()
    return {"name": d["name"], "bus": d["bus"], "lines": d["lines"], "settings": d["settings"]}


def test_layout_progress_follows_the_stress_layout_and_changes_nothing(case118):
    b, l, _, _ = gridcore.prep_case(frame(case118["bus"]), frame(case118["lines"]),
                                    case118["settings"])
    edges = [(int(f) - 1, int(t) - 1) for f, t in zip(l["From"], l["To"])]
    seen = []
    g = figures.layout(len(b), edges, b, progress=lambda s, d, t: seen.append((s, d, t)))
    assert list(dict.fromkeys(s for s, _, _ in seen)) == ["Hop distances", "Starting positions",
                                                         "Stress layout"]
    assert [d for s, d, _ in seen if s == "Hop distances"] == list(range(len(b)))
    assert to_json(g) == to_json(figures.layout(len(b), edges, b))

    def stop(stage, done, total):
        if stage == "Stress layout" and done == 5:
            raise jobs.Cancelled

    with pytest.raises(jobs.Cancelled):
        figures.layout(len(b), edges, b, progress=stop)


def test_layout_job_is_exactly_the_layout_response(case118):
    r = client.post("/api/jobs", json={"kind": "layout", "case": case118})
    assert r.status_code == 202 and r.json()["kind"] == "layout"
    s = poll(r.json()["id"])
    assert s["status"] == "done" and s["stage"] == "Stress layout"
    assert s["result"] == client.post("/api/layout", json=case118).json()


# -------------------------------------------------------------------- API
@pytest.mark.parametrize("name", list(CASES))
def test_job_result_is_exactly_the_study_response(name):
    case = client.get(f"/api/case/{name}").json()
    r = client.post("/api/jobs", json={"kind": "study", "case": case})
    assert r.status_code == 202 and r.json()["kind"] == "study"
    s = poll(r.json()["id"])
    assert s["status"] == "done" and s["stage"] == STAGES[-1]
    assert s["result"] == client.post("/api/study", json=case).json()


def test_bad_data_is_refused_before_a_job_starts():
    case = client.get("/api/case/5-bus (demo)").json()
    case["bus"][0]["Type"] = "Swing"
    before = len(client.get("/api/jobs").json()["jobs"])
    r = client.post("/api/jobs", json={"case": case})
    assert r.status_code == 422 and any("Slack, PV or PQ" in p for p in r.json()["problems"])
    assert len(client.get("/api/jobs").json()["jobs"]) == before
    r = client.post("/api/jobs", json={"kind": "nope", "case": case})
    assert r.status_code == 422 and r.json()["problems"][0].startswith("body.kind")


def test_unknown_jobs_are_404():
    for r in (client.get("/api/jobs/abc"), client.delete("/api/jobs/abc")):
        assert r.status_code == 404 and "No job 'abc'" in r.json()["problems"][0]


def test_cancel_through_the_api(monkeypatch):
    def slow_study(*args, progress=None, **kw):
        for i in range(20_000):
            progress("Line outages (N-1)", i, 20_000)
            time.sleep(0.001)
        raise AssertionError("not cancelled")

    monkeypatch.setattr(gridcore, "run_study", lambda *a: slow_study(*a[:-1], progress=a[-1]))
    case = client.get("/api/case/5-bus (demo)").json()
    jid = client.post("/api/jobs", json={"case": case}).json()["id"]
    wait(jid, until=("running",))
    while client.get(f"/api/jobs/{jid}").json()["done"] < 2:
        time.sleep(0.002)
    r = client.delete(f"/api/jobs/{jid}")
    assert r.status_code == 200 and r.json()["id"] == jid
    s = poll(jid)
    assert s["status"] == "cancelled" and s["stage"] == "Line outages (N-1)"
    assert any(j["id"] == jid for j in client.get("/api/jobs").json()["jobs"])


def test_a_study_that_fails_in_the_job_reports_its_problem(monkeypatch):
    def broken(*a):
        raise RuntimeError("singular matrix")

    monkeypatch.setattr(gridcore, "run_study", broken)
    case = client.get("/api/case/5-bus (demo)").json()
    s = poll(client.post("/api/jobs", json={"case": case}).json()["id"])
    assert s["status"] == "failed" and s["problems"] == ["Study failed: singular matrix"]
