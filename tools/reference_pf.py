"""Make tests/data/reference_pf.json: MATPOWER's answers for the reference cases.

Runs PYPOWER (a Python port of MATPOWER: makeYbus, newtonpf, pfsoln, makeBdc)
on the same .m files GridLens reads: the AC load flow (runpf, Newton-Raphson,
tolerance 1e-11) and the DC load flow (rundcpf). Stores per bus |V| and angle
(AC) and the DC angle, and per generator P and Q (AC), by bus number and
generator row; Q is null where PYPOWER gives NaN (infinite Q limits). Only
needed to regenerate the file; GridLens and its tests do not use PYPOWER:
    pip install --target <dir> pypower
    PYTHONPATH=<dir> python tools/reference_pf.py
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from pypower.api import ppoption, rundcpf, runpf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import formats  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "tests" / "data"
CASES = ["case9", "case14", "case24_ieee_rts", "case30", "case39", "case57", "case118",
         "case300", "case1354pegase", "case2383wp"]


def ppc(text):
    t = re.sub(r"%[^\n]*", "", text)
    base = float(re.search(r"mpc\.baseMVA\s*=\s*([-+\d.eE]+)", t).group(1))
    m = {f: np.array(formats._matrix(t, f)) for f in ("bus", "gen", "branch")}
    return {"version": "2", "baseMVA": base, **m}


def main():
    opt = ppoption(VERBOSE=0, OUT_ALL=0, PF_TOL=1e-11)
    out = {"source": "PYPOWER 5.1.21 runpf (Newton-Raphson, PF_TOL 1e-11) and rundcpf "
                     "on the MATPOWER .m files in tests/data; tools/reference_pf.py. qg is null "
                     "where PYPOWER gives NaN: a generator with infinite Q limits (MATPOWER 6+ "
                     "puts finite stand-ins there, so a lone one takes its bus's Q)"}
    for name in CASES:
        text = (DATA / f"{name}.m").read_text()
        ac, ok = runpf(ppc(text), opt)[:2]
        dc = rundcpf(ppc(text), opt)[0]
        assert ok, name
        on = ac["gen"][:, 7] > 0
        out[name] = {"bus": ac["bus"][:, 0].astype(int).tolist(),
                     "vm": [round(v, 12) for v in ac["bus"][:, 7]],
                     "va": [round(v, 10) for v in ac["bus"][:, 8]],
                     "va_dc": [round(v, 10) for v in dc["bus"][:, 8]],
                     "gen": [f"gen{k + 1}" for k in np.flatnonzero(on)],
                     "pg": [round(v, 8) for v in ac["gen"][on, 1]],
                     "qg": [None if np.isnan(v) else round(v, 8) for v in ac["gen"][on, 2]]}
        print(name, len(out[name]["bus"]), "buses")
    (DATA / "reference_pf.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
