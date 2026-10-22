"""Regression snapshot of every study endpoint on the preset cases.

v1.6 widens the case model (bus numbers, islands, units, imports). With the
old data every number must stay exactly what v1.5 returned. Keys added later
are allowed; keys and values in the snapshot are not allowed to change.
Regenerated at v2.1 (sparse Newton-Raphson with the analytical Jacobian):
results within 1.2e-12 of v2.0; the per-iteration mismatches (hist) within
2.1e-9, the error of the old numerical Jacobian.
Regenerate (only after an approved maths change): GOLDEN_WRITE=1 pytest tests/test_golden_api.py
"""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import app

GOLDEN = Path(__file__).parent / "data" / "api_golden.json"
client = TestClient(app)
SETTINGS = {
    "5-bus (demo)": [{}, {"qlim": True}, {"method": "Fast Decoupled"}, {"method": "Gauss-Seidel"}],
    "IEEE 14-bus": [{}, {"taps": True, "shunts": True}, {"taps": True, "shunts": True, "qlim": True}],
}


def _case(name, extra):
    c = client.get(f"/api/case/{name}").json()
    c["settings"].update(extra)
    for b in c["bus"]:          # positions and labels are not study inputs
        for k in ("x", "y", "Name", "Num"):
            b.pop(k, None)
    return c


def _calls(name, extra):
    c = _case(name, extra)
    yield "study", client.post("/api/study", json=c)
    yield "fault", client.post("/api/fault", json={"case": c})
    yield "seqfault", client.post("/api/seqfault", json={"case": c, "kind": "SLG", "bus": 2})
    yield "ybus", client.post("/api/ybus", json=c)
    for m in ("Newton-Raphson", "Fast Decoupled", "Gauss-Seidel"):
        yield f"iter-{m}", client.post("/api/iterations", json={"case": c, "method": m})
    yield "outage0", client.post("/api/outage/0", json=c)


def _snapshot():
    out = {}
    for name, variants in SETTINGS.items():
        for extra in variants:
            key = f"{name}|{json.dumps(extra, sort_keys=True)}"
            for what, r in _calls(name, extra):
                assert r.status_code == 200, (key, what, r.text[:300])
                out[f"{key}|{what}"] = r.json()
    return out


def _contains(old, new, path="$"):
    """Every key/value of old is in new with the same value (new may add keys)."""
    if isinstance(old, dict):
        assert isinstance(new, dict), path
        for k, v in old.items():
            assert k in new, f"{path}.{k} missing"
            _contains(v, new[k], f"{path}.{k}")
    elif isinstance(old, list):
        assert isinstance(new, list) and len(new) == len(old), f"{path} length"
        for i, (a, b) in enumerate(zip(old, new)):
            _contains(a, b, f"{path}[{i}]")
    else:
        assert old == new, f"{path}: {old!r} != {new!r}"


def test_api_matches_snapshot():
    snap = _snapshot()
    if os.environ.get("GOLDEN_WRITE") or not GOLDEN.exists():
        GOLDEN.write_text(json.dumps(snap))
        pytest.skip("snapshot written")
    old = json.loads(GOLDEN.read_text())
    assert set(old) == set(snap)
    for k in old:
        _contains(old[k], snap[k], k)
