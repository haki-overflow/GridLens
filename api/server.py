"""GridLens API: JSON in, JSON out. Run: ./run_api.sh (docs at /docs).

A "case" is {"bus": [records], "lines": [records], "settings": {...}}
with the same columns as the app's bus / line tables (per unit). Every
endpoint that takes a case validates it with gridcore.prep_case first and
answers 422 {"problems": [...], "notes": [...]} when the data is wrong.
Any other failure is also a 422 with a one-line problem, never a stack
trace. All maths is done by the existing modules; this file only moves
data in and out.
"""
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import gridcore
import figures
import formats
import topics
import working as W
from gridcore import CASES
from solver import build_ybus
from studies import fault_analysis

from .schema import complex_in, frame, to_json

DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

app = FastAPI(title="GridLens API", version="2.7",
              description="Load flow, N-1, faults and textbook tools as JSON.")


# ------------------------------------------------------------------ models
class Settings(BaseModel):
    method: str = "Newton-Raphson"
    tol: float = 1e-8
    base: float = 100.0
    vmin: float = 0.95
    vmax: float = 1.10
    qlim: bool = False
    taps: bool = False
    shunts: bool = False
    init: str = Field("flat", description='"flat" (1∠0° start) or "setpoint" (V and Va columns)')
    fallback: bool = Field(True, description="try other methods/starts when the load flow "
                           "does not converge")
    freq: float = 50.0
    units: str = Field("pu", description='"pu" (per unit on base MVA) or "actual" '
                       "(MW, MVAr, kV, ohm, uS), converted per bus base kV")


class Case(BaseModel):
    bus: list[dict[str, Any]]
    lines: list[dict[str, Any]]
    settings: Settings = Field(default_factory=Settings)
    name: Optional[str] = Field(None, description="Case name (a label only).")


class FaultIn(BaseModel):
    case: Case
    xd: float = 0.2
    zf: float = 0.0
    kv: float = 33.0


class SeqFaultIn(BaseModel):
    case: Case
    kind: str = "SLG"
    bus: int = 1
    zf: Any = 0.0
    prefault: str = Field("flat", description='"flat" (1∠0°) or "loadflow"')
    gens: Optional[list[dict[str, Any]]] = None
    branches: Optional[list[dict[str, Any]]] = None
    kv: Optional[list[float]] = None


class IterIn(BaseModel):
    case: Case
    method: Optional[str] = None
    tol: Optional[float] = None
    alpha: float = 1.0


class AnswerIn(BaseModel):
    case: Case
    show: int = 2
    conversion: Optional[dict[str, list[dict[str, Any]]]] = None


class DispatchIn(BaseModel):
    units: list[dict[str, Any]]
    PD: float
    B: Optional[list[list[float]]] = None
    B0: Optional[list[float]] = None
    B00: float = 0.0
    pu_base: Optional[float] = Field(None, description="If set, B, B0, B00 "
                                     "are per unit on this MVA base.")
    use_limits: bool = True
    tol: float = 1e-6


class SymIn(BaseModel):
    abc: Optional[list[Any]] = None
    s012: Optional[list[Any]] = None


class TLineIn(BaseModel):
    model: str = "medium (π)"
    R: float = 0.1
    X: float = 0.5
    B_uS: float = 3.2
    length: float = 150.0
    VR_kV: float = 220.0
    PR_MW: float = 150.0
    pf: float = 0.85
    lagging: bool = True


class ImportIn(BaseModel):
    filename: str = Field(..., description="decides the reader: .m (MATPOWER), "
                          ".cdf / .txt (IEEE common format), .csv (GridLens templates)")
    text: str
    lines_text: Optional[str] = Field(None, description="the line CSV, for CSV imports")


class ToPuIn(BaseModel):
    sbase: float
    ref_bus: int
    ref_kv: float
    buses: list[dict[str, Any]]
    lines: list[dict[str, Any]] = []
    trafos: list[dict[str, Any]] = []


# ---------------------------------------------------------- error handling
class Problems(Exception):
    def __init__(self, problems, notes=()):
        self.problems, self.notes = list(problems), list(notes)


@app.exception_handler(Problems)
async def _problems(_, e: Problems):
    return JSONResponse(status_code=422,
                        content={"problems": e.problems, "notes": e.notes})


@app.exception_handler(RequestValidationError)
async def _bad_request(_, e: RequestValidationError):
    return JSONResponse(status_code=422, content={"problems": [
        f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]})


def _guard(fn, what):
    """Run fn(); any error becomes a 422 problem instead of a traceback."""
    try:
        return fn()
    except Problems:
        raise
    except Exception as e:
        raise Problems([f"{what} failed: {e}"]) from None


# ----------------------------------------------------------------- helpers
def _cfg(case):
    return case.settings.model_dump()


def _prep(case):
    """Validated per-unit tables; 422 on problems."""
    b, l, probs, notes = _guard(lambda: gridcore.prep_case(
        frame(case.bus), frame(case.lines), _cfg(case)), "Validation")
    if probs:
        raise Problems(probs, notes)
    return b, l, notes


def _loadflow(case):
    """Main load flow as run_study does it (Q limits when on): b, l, res,
    flows, ok, hist, b_lf (bus types after Q-limit switching), qlog."""
    b, l, _ = _prep(case)
    s = case.settings

    def run():
        res, flows, ok, hist, b_lf, qlog, *_ = gridcore.loadflow(
            b, l, s.method, s.tol, s.qlim, s.init, s.fallback)
        return b, l, res, flows, ok, hist, b_lf, qlog
    return _guard(run, "Load flow")


def _bus_kv(b, default):
    """Base kV per bus: the bus kV column where given (> 0), else default."""
    if "kV" not in b:
        return np.full(len(b), float(default))
    kv = pd.to_numeric(b["kV"], errors="coerce").to_numpy(float)
    return np.where(np.isfinite(kv) & (kv > 0), kv, float(default))


# --------------------------------------------------------------- endpoints
@app.get("/api/cases")
def cases():
    return {"cases": list(CASES)}


@app.get("/api/case/{name}")
def case(name: str):
    if name not in CASES:
        return JSONResponse(status_code=404, content={
            "problems": [f"No preset called {name!r}."], "cases": list(CASES)})
    bus, lines = CASES[name]
    return {"name": name, "bus": to_json(bus), "lines": to_json(lines),
            "settings": Settings().model_dump()}


@app.post("/api/import")
def import_case(body: ImportIn):
    """A case file -> a GridLens case (per unit, taps and shunts on)."""
    c = _guard(lambda: formats.read_case(body.filename, body.text, body.lines_text), "Import")
    settings = Settings(base=c["base"], taps=True, shunts=True).model_dump()
    b, l, probs, notes = _guard(lambda: gridcore.prep_case(c["bus"], c["lines"], settings),
                                "Validation")
    return {"name": c["name"], "bus": to_json(c["bus"]), "lines": to_json(c["lines"]),
            "settings": settings, "notes": c["notes"] + notes, "problems": probs}


@app.post("/api/validate")
def validate(case: Case):
    b, l, probs, notes = _guard(lambda: gridcore.prep_case(
        frame(case.bus), frame(case.lines), _cfg(case)), "Validation")
    return {"problems": probs, "notes": notes}


@app.post("/api/study")
def study(case: Case):
    b, l, notes = _prep(case)
    s = case.settings
    out = _guard(lambda: gridcore.run_study(b, l, s.method, s.tol, s.base,
                                            s.vmin, s.vmax, s.qlim, s.init,
                                            s.fallback), "Study")
    pv, lam = out.pop("pv")
    if out["ok"] and len(out["attempts"]) > 1:
        notes = notes + [f"{s.method} ({s.init} start) did not converge; solved with "
                         f"{out['solved_with']}. See Solve > Do the 3 methods agree?"]
    return {**to_json(out), "pv": {"curve": to_json(pv), "lambda_max": lam},
            "notes": notes}


@app.post("/api/layout")
def layout(case: Case):
    b, l, _ = _prep(case)
    edges = [(int(f) - 1, int(t) - 1) for f, t in zip(l["From"], l["To"])]
    g = _guard(lambda: figures.layout(len(b), edges, b),
               "Layout")
    return to_json(g)


@app.post("/api/outage/{k}")
def outage(k: int, case: Case):
    b, l, _ = _prep(case)
    if not 0 <= k < len(l):
        raise Problems([f"Line index k must be 0 to {len(l) - 1} (row order)."])
    res, flows, ok, hist, cut = _guard(lambda: gridcore.outage(b, l, k, case.settings.qlim),
                                       "Outage")
    return {"line": f"{int(l['From'][k])}-{int(l['To'][k])}", "res": to_json(res),
            "flows": to_json(flows), "ok": bool(ok), "hist": to_json(hist),
            "cut_off": [int(i) + 1 for i in cut],
            "lost_load": float(b["Pd"].to_numpy(float)[cut].sum() * case.settings.base)}


@app.post("/api/fault")
def fault(body: FaultIn):
    b, l, res, *_ = _loadflow(body.case)
    kv = _bus_kv(b, body.kv)
    tbl, Z, V0, If = _guard(lambda: fault_analysis(
        b, l, res, body.xd, body.zf, body.case.settings.base,
        body.kv if np.all(kv == body.kv) else kv), "Fault analysis")
    out = {"table": to_json(tbl), "V0": to_json(V0), "If": to_json(If)}
    if len(b) <= W.TEACH_MAX:     # the dense Zbus only where someone could read it
        out["Z"] = to_json(Z)
    return out


@app.post("/api/seqfault")
def seqfault(body: SeqFaultIn):
    b, l, res, *_ = _loadflow(body.case)
    n = len(b)
    g0, b0 = topics.seed_tables(b, l)
    gens = frame(body.gens) if body.gens is not None else g0
    br = frame(body.branches) if body.branches is not None else b0
    kv = np.asarray(body.kv, float) if body.kv is not None else _bus_kv(b, 33.0)
    vf = np.ones(n, complex) if body.prefault == "flat" else \
        res["V (pu)"].to_numpy() * np.exp(1j * np.radians(res["Angle (deg)"].to_numpy()))
    zf, base = complex_in(body.zf), body.case.settings.base

    def run():
        r = topics.solve_fault(body.kind, body.bus, gens, br, vf, zf, base, kv)
        return r, topics.fault_table(body.kind, gens, br, vf, zf, base, kv)
    r, tab = _guard(run, "Sequence fault")
    return {**to_json(r), "table": to_json(tab), "gens": to_json(gens),
            "branches": to_json(br), "kv": to_json(kv)}


def _teaching_size(b):
    """Show working builds dense matrices and step-by-step tables: small cases only."""
    if len(b) > W.TEACH_MAX:
        raise Problems([f"Show working is for cases up to {W.TEACH_MAX} buses; this one has "
                        f"{len(b)}. The matrices and step-by-step tables would be too big to "
                        "read; the results pages have every number."])


@app.post("/api/ybus")
def ybus(case: Case):
    _, l, _, _, _, _, b_lf, _ = _loadflow(case)
    _teaching_size(b_lf)
    parts = _guard(lambda: W.ybus_parts(b_lf, l), "Ybus")
    return {"parts": to_json(parts), "Y": to_json(build_ybus(len(b_lf), l, b_lf))}


@app.post("/api/iterations")
def iterations(body: IterIn):
    _, l, _, _, _, _, b_lf, _ = _loadflow(body.case)
    _teaching_size(b_lf)
    method = body.method or body.case.settings.method
    tol = body.tol or (1e-6 if method == "Gauss-Seidel" else 1e-8)

    def run():
        if method == "Gauss-Seidel":
            return W.gauss_seidel_trace(b_lf, l, body.alpha, tol, 2000)
        if method == "Fast Decoupled":
            return W.fast_decoupled_trace(b_lf, l, tol)
        if method == "Newton-Raphson":
            return W.newton_trace(b_lf, l, tol)
        raise ValueError(f"unknown method {method!r}")
    return {"method": method, "tol": tol, "trace": to_json(_guard(run, "Trace"))}


@app.post("/api/answer")
def answer(body: AnswerIn):
    _, l, res, flows, _, _, b_lf, _ = _loadflow(body.case)
    _teaching_size(b_lf)
    s = body.case.settings
    conv = None if body.conversion is None else \
        {k: frame(v) for k, v in body.conversion.items()}
    text = _guard(lambda: W.answer_text(
        b_lf, l, res, flows, s.base, s.method,
        W.trace_lines(s.method, b_lf, l, tol=s.tol, show=body.show),
        conversion=conv), "Answer")
    return {"text": text}


@app.post("/api/dispatch")
def dispatch(body: DispatchIn):
    def run():
        B, B0, B00 = body.B, body.B0, body.B00
        if body.pu_base and B is not None:
            B, B0, B00 = topics.b_from_pu(B, B0 if B0 is not None else [0.0] * len(B),
                                     B00, body.pu_base)
        return topics.dispatch(frame(body.units), body.PD, B, B0, B00,
                          use_limits=body.use_limits, tol=body.tol)
    return to_json(_guard(run, "Dispatch"))


@app.post("/api/symcomp")
def symcomp(body: SymIn):
    if body.abc is None and body.s012 is None:
        raise Problems(['Give "abc" (phase -> sequence) or "s012" '
                        "(sequence -> phase), three phasors each."])
    out = {}
    if body.abc is not None:
        out["s012"] = to_json(_guard(lambda: topics.to_sequence(
            [complex_in(v) for v in body.abc]), "to_sequence"))
    if body.s012 is not None:
        out["abc"] = to_json(_guard(lambda: topics.to_phase(
            [complex_in(v) for v in body.s012]), "to_phase"))
    return out


@app.post("/api/tline")
def tline(body: TLineIn):
    p = body.model_dump()

    def run():
        A, B, C, Dd = topics.abcd(p["model"], p["R"], p["X"], p["B_uS"], p["length"])
        return dict(abcd=dict(A=A, B=B, C=C, D=Dd), performance=topics.performance(**p))
    return to_json(_guard(run, "Line calculation"))


@app.post("/api/topu")
def topu(body: ToPuIn):
    r = _guard(lambda: topics.to_pu(body.sbase, body.ref_bus, body.ref_kv,
                                   frame(body.buses), frame(body.lines),
                                   frame(body.trafos)), "Per-unit conversion")
    return to_json(r)


@app.get("/api/units/example")
def units_example():
    """The textbook example (real units) that the input wizard starts from."""
    ex = topics.UNITS_EXAMPLE
    return to_json({"sbase": ex["sbase"], "ref_bus": ex["ref_bus"], "ref_kv": ex["ref_kv"],
                    "buses": ex["buses"], "lines": ex["lines"], "trafos": ex["trafos"],
                    "z_units": list(topics.Z_UNITS), "b_units": list(topics.B_UNITS)})


# --------------------------------------------------------------- AI write-up
class ReportIn(BaseModel):
    summary: str
    model: str


@app.get("/api/lm/models")
def lm_models_ep():
    """Models loaded in LM Studio (empty when the server is not running)."""
    import gridcore as ai_report
    return {"models": ai_report.lm_models(), "url": ai_report.LMSTUDIO_URL}


@app.post("/api/report")
def report(body: ReportIn):
    """Plain-English write-up of the solver's own summary by a local model;
    the model only rephrases the numbers it is given."""
    import gridcore as ai_report
    import requests
    try:
        return {"text": ai_report.ai_report(body.summary, body.model)}
    except requests.ConnectionError:
        raise Problems([f"LM Studio is not reachable at {ai_report.LMSTUDIO_URL}. Open LM Studio, "
                        "load a model and start the server (Developer tab)."])
    except requests.HTTPError as e:
        raise Problems([f"LM Studio refused the request ({e.response.status_code}). Check that "
                        f"the model id \"{body.model}\" is loaded."])
    except Exception as e:  # noqa: BLE001 - reported to the user, never a stack trace
        raise Problems([f"The write-up failed: {e}"])


# ------------------------------------------------------------ static web app
class _Web(StaticFiles):
    """web/dist (the workspace built by `npm run build`) at "/". Checked on
    every request, so a build made while the server runs is picked up;
    until it exists "/" redirects to the API docs."""

    async def get_response(self, path, scope):
        if not (DIST / "index.html").is_file():
            return RedirectResponse("/docs")
        self.directory = DIST
        self.all_directories = [DIST]
        return await super().get_response(path, scope)


app.mount("/", _Web(directory=DIST, html=True, check_dir=False), name="web")
