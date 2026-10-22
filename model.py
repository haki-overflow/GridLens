"""GridLens element model (v2): a case as element tables with stable IDs.

One pandas DataFrame per element type, one row per element; "id" is unique
across the case and is what other elements, results, scenarios and
contingency lists refer to. Bus numbers and names are labels only.

  bus     id, num, name, kv, slack, vm, va, x, y
  branch  id, kind ("line" | "trafo"), from_bus, to_bus (bus ids), r, x, b
          (pu on the case base), tap (ratio at the From side, 1 = none),
          shift (deg), rate (MVA, 0 = none), in_service
  gen     id, bus, p (MW), q (MVAr), vset (pu; NaN = holds no voltage),
          qmin, qmax (MVAr; NaN = no limit), in_service
  load    id, bus, p (MW), q (MVAr), in_service
  shunt   id, bus, g (MW at 1 pu), b (MVAr at 1 pu, + = capacitor), in_service

A bus is Slack when its slack flag is set, PV when an in-service generator
holds a voltage there (finite vset), else PQ. vm and va are the start values
(va also the Slack's reference angle).

The solvers still take the v1 per-unit bus / line tables: to_tables makes
them from a case, from_tables makes a case from them, and results() keys a
load flow's results by element ID. No maths here beyond unit scaling and
sharing a bus's generation among its generators.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

NAN = float("nan")
COLUMNS = {   # column -> default for a new element
    "bus": {"id": "", "num": 0, "name": "", "kv": NAN, "slack": False, "vm": 1.0, "va": 0.0,
            "x": NAN, "y": NAN},
    "branch": {"id": "", "kind": "line", "from_bus": "", "to_bus": "", "r": 0.0, "x": 0.0,
               "b": 0.0, "tap": 1.0, "shift": 0.0, "rate": 0.0, "in_service": True},
    "gen": {"id": "", "bus": "", "p": 0.0, "q": 0.0, "vset": NAN, "qmin": NAN, "qmax": NAN,
            "in_service": True},
    "load": {"id": "", "bus": "", "p": 0.0, "q": 0.0, "in_service": True},
    "shunt": {"id": "", "bus": "", "g": 0.0, "b": 0.0, "in_service": True},
}
KINDS = list(COLUMNS)


def table(kind, rows=None):
    """A table of one element type with every column (missing ones get the
    default), in the COLUMNS order."""
    df = pd.DataFrame(rows if rows is not None else [])
    for c, d in COLUMNS[kind].items():
        if c not in df:
            df[c] = pd.Series([d] * len(df), dtype=object if isinstance(d, str) else None)
    return df[list(COLUMNS[kind])].reset_index(drop=True)


@dataclass
class Case:
    name: str = ""
    base: float = 100.0     # MVA
    freq: float = 50.0      # Hz
    bus: pd.DataFrame = field(default_factory=lambda: table("bus"))
    branch: pd.DataFrame = field(default_factory=lambda: table("branch"))
    gen: pd.DataFrame = field(default_factory=lambda: table("gen"))
    load: pd.DataFrame = field(default_factory=lambda: table("load"))
    shunt: pd.DataFrame = field(default_factory=lambda: table("shunt"))

    def tables(self):
        return {k: getattr(self, k) for k in KINDS}


def new_id(case, prefix):
    """The next free id with this prefix ("bus", "line", "trafo", "gen",
    "load", "shunt"): one more than the highest number in use."""
    used = [i[len(prefix):] for t in case.tables().values() for i in t["id"]
            if str(i).startswith(prefix)]
    return f"{prefix}{max([int(u) for u in used if u.isdigit()] or [0]) + 1}"


def check_ids(case):
    """Problems with the ids: duplicates, and references to buses that do not exist."""
    probs = []
    ids = pd.concat([t["id"] for t in case.tables().values()], ignore_index=True)
    dup = sorted(set(ids[ids.duplicated()]))
    if dup:
        probs.append("Duplicate element ids: " + ", ".join(map(str, dup)) + ".")
    buses = set(case.bus["id"])
    for kind, cols in (("branch", ("from_bus", "to_bus")), ("gen", ("bus",)),
                       ("load", ("bus",)), ("shunt", ("bus",))):
        t = getattr(case, kind)
        bad = sorted({i for c in cols for i, b in zip(t["id"], t[c]) if b not in buses})
        if bad:
            probs.append(f"{kind.capitalize()} elements refer to buses that do not exist: "
                         + ", ".join(bad) + ".")
    return probs


def bus_types(case):
    """Slack / PV / PQ per bus (in bus order) and the vset of each bus's first
    in-service generator that holds a voltage (NaN where none does)."""
    row = {bid: i for i, bid in enumerate(case.bus["id"])}
    first = np.full(len(row), NAN)
    G = case.gen
    for b, v, on in zip(G["bus"][::-1], G["vset"].to_numpy(float)[::-1],
                        G["in_service"].astype(bool)[::-1]):   # first generator wins
        if on and np.isfinite(v):
            first[row[b]] = v
    slack = case.bus["slack"].astype(bool).to_numpy()
    return np.where(slack, "Slack", np.where(np.isfinite(first), "PV", "PQ")), first


# ---------------------------------------------------------------- v1 tables
def from_tables(bus, lines, base=100.0, name="", freq=50.0):
    """Case from the v1 per-unit tables (as prep_case returns them): bus ids
    from the bus numbers (Num, else the row), one generator per Slack / PV bus
    (holding V) and per PQ bus with Pg or Qg, one load per bus with Pd or Qd,
    one shunt per bus with Gs or Bs; a branch with Kind "trafo", a tap or a
    phase shift is a transformer."""
    b = bus.reset_index(drop=True)
    n = len(b)

    def col(df, c, fill):
        return pd.to_numeric(df[c], errors="coerce").fillna(fill).to_numpy(float) \
            if c in df else np.full(len(df), fill)
    num = col(b, "Num", 0).astype(int) if "Num" in b else np.arange(1, n + 1)
    ids = [f"bus{k}" for k in num]
    t = b["Type"].astype(str).to_numpy()
    case = Case(name=name, base=float(base), freq=float(freq))
    case.bus = table("bus", {
        "id": ids, "num": num, "name": b["Name"].fillna("").astype(str) if "Name" in b else "",
        "kv": col(b, "kV", NAN), "slack": t == "Slack", "vm": col(b, "V", 1.0),
        "va": col(b, "Va", 0.0), "x": col(b, "x", NAN), "y": col(b, "y", NAN)})
    pg, qg = col(b, "Pg", 0.0), col(b, "Qg", 0.0)
    gen = (t != "PQ") | (pg != 0) | (qg != 0)
    case.gen = table("gen", {
        "id": [f"gen{k + 1}" for k in range(gen.sum())], "bus": np.array(ids)[gen],
        "p": pg[gen] * base, "q": qg[gen] * base,
        "vset": np.where(t != "PQ", col(b, "V", 1.0), NAN)[gen],
        "qmin": col(b, "Qmin", NAN)[gen] * base, "qmax": col(b, "Qmax", NAN)[gen] * base})
    for kind, (pc, qc), (p, q) in (("load", ("Pd", "Qd"), ("p", "q")),
                                   ("shunt", ("Gs", "Bs"), ("g", "b"))):
        pv, qv = col(b, pc, 0.0), col(b, qc, 0.0)
        has = (pv != 0) | (qv != 0)
        setattr(case, kind, table(kind, {
            "id": [f"{kind}{k + 1}" for k in range(has.sum())], "bus": np.array(ids)[has],
            p: pv[has] * base, q: qv[has] * base}))
    case.branch = _branches_from_lines(lines, ids)
    return case


def _branches_from_lines(lines, ids):
    l = lines.reset_index(drop=True)

    def col(c, fill):
        return pd.to_numeric(l[c], errors="coerce").fillna(fill).to_numpy(float) \
            if c in l else np.full(len(l), fill)
    tap, shift = col("Tap", 1.0), col("Shift", 0.0)
    tap = np.where(tap > 0, tap, 1.0)
    kind = l["Kind"].fillna("").astype(str).to_numpy() if "Kind" in l else np.full(len(l), "")
    trafo = (kind == "trafo") | (np.abs(tap - 1) > 1e-12) | (shift != 0)
    count = {"line": 0, "trafo": 0}
    bid = []
    for tr in trafo:
        k = "trafo" if tr else "line"
        count[k] += 1
        bid.append(f"{k}{count[k]}")
    on = l["InService"].to_numpy() if "InService" in l else np.ones(len(l))
    return table("branch", {
        "id": bid, "kind": np.where(trafo, "trafo", "line"),
        "from_bus": [ids[int(f) - 1] for f in l["From"]], "to_bus": [ids[int(t) - 1] for t in l["To"]],
        "r": col("R", 0.0), "x": col("X", 0.0), "b": col("B", 0.0), "tap": tap, "shift": shift,
        "rate": col("Rate", 0.0), "in_service": [bool(float(v)) if pd.notna(v) else True for v in on]})


def to_tables(case):
    """The v1 per-unit bus and line tables of a case, rows in the case's order
    (bus Num = num, lines refer to bus rows 1..N). Generators, loads and
    shunts in service are summed per bus in table order; V of a Slack / PV
    bus is the vset of its first generator holding a voltage."""
    B, base = case.bus.reset_index(drop=True), case.base
    n = len(B)
    row = {bid: i for i, bid in enumerate(B["id"])}

    def per_bus(t, *cols):
        on = t["in_service"].astype(bool).to_numpy()
        at = t["bus"].map(row).to_numpy()[on].astype(int)
        return at, [t[c].to_numpy(float)[on] for c in cols]
    gi, (p, q, qmin, qmax) = per_bus(case.gen, "p", "q", "qmin", "qmax")
    has_gen = np.bincount(gi, minlength=n) > 0
    typ, first = bus_types(case)
    V = np.where((typ != "PQ") & np.isfinite(first), first, B["vm"].to_numpy(float))
    li, (pd_, qd) = per_bus(case.load, "p", "q")
    si, (g, bs) = per_bus(case.shunt, "g", "b")

    def total(at, v):   # in table order, from 0 (bincount gives int zeros when empty)
        return np.bincount(at, v / base, n).astype(float)
    bus = pd.DataFrame({
        "Num": B["num"].to_numpy(int), "Name": B["name"].to_numpy(object), "Type": typ, "V": V,
        "Va": B["va"].to_numpy(float), "kV": B["kv"].to_numpy(float),
        "Pg": total(gi, p), "Qg": total(gi, q), "Pd": total(li, pd_), "Qd": total(li, qd),
        "Qmin": np.where(has_gen, total(gi, qmin), NAN),
        "Qmax": np.where(has_gen, total(gi, qmax), NAN),
        "Gs": total(si, g), "Bs": total(si, bs)})
    for c in ("x", "y"):
        if B[c].notna().any():
            bus[c] = B[c].to_numpy(float)
    R = case.branch.reset_index(drop=True)
    lines = pd.DataFrame({
        "From": R["from_bus"].map(row).to_numpy(int) + 1, "To": R["to_bus"].map(row).to_numpy(int) + 1,
        "R": R["r"].to_numpy(float), "X": R["x"].to_numpy(float), "B": R["b"].to_numpy(float),
        "Tap": R["tap"].to_numpy(float), "Shift": R["shift"].to_numpy(float),
        "Rate": R["rate"].to_numpy(float),
        "InService": R["in_service"].astype(bool).to_numpy().astype(int),
        "Kind": R["kind"].to_numpy(object)})
    return bus, lines


# ------------------------------------------------------------------ results
def results(case, res, flows, b_lf):
    """Load flow results keyed by element ID, in MW, MVAr, pu and degrees.
    res / flows are solver results on to_tables(case); b_lf the bus table the
    load flow ended with (its Type after any PV -> PQ switching).
      bus     num, name, type, vm, va, p, q (net injection into the network)
      branch  kind, from_bus, to_bus, p_from, q_from, p_to, q_to (into the
              branch at each end), loss_p, loss_q, loading (% of rate)
      gen     bus, p, q: as scheduled at PQ buses; at Slack / PV buses the bus's
              Q is shared in proportion to the Q ranges (equally when a limit
              is missing) and the Slack's first generator takes the P balance,
              as MATPOWER's pfsoln does
      load    bus, p, q;  shunt  bus, p, q (taken from the bus at the solved |V|)"""
    base, B, R = case.base, case.bus, case.branch
    bus = pd.DataFrame({
        "num": B["num"].to_numpy(), "name": B["name"].to_numpy(), "type": b_lf["Type"].to_numpy(),
        "vm": res["V (pu)"].to_numpy(), "va": res["Angle (deg)"].to_numpy(),
        "p": res["P_inj"].to_numpy() * base, "q": res["Q_inj"].to_numpy() * base},
        index=pd.Index(B["id"], name="id"))
    sf = np.hypot(flows["P_ij"], flows["Q_ij"]).to_numpy() * base
    st = np.hypot(flows["P_ji"], flows["Q_ji"]).to_numpy() * base
    rate = R["rate"].to_numpy(float)
    branch = pd.DataFrame({
        "kind": R["kind"].to_numpy(), "from_bus": R["from_bus"].to_numpy(),
        "to_bus": R["to_bus"].to_numpy(),
        **{k: flows[c].to_numpy() * base for k, c in (
            ("p_from", "P_ij"), ("q_from", "Q_ij"), ("p_to", "P_ji"), ("q_to", "Q_ji"),
            ("loss_p", "Loss_P"), ("loss_q", "Loss_Q"))},
        "loading": np.where(rate > 0, np.maximum(sf, st) / np.where(rate > 0, rate, 1) * 100, NAN)},
        index=pd.Index(R["id"], name="id"))
    vm2 = pd.Series(bus["vm"].to_numpy() ** 2, index=B["id"])
    L, S = case.load, case.shunt
    on_l, on_s = (t["in_service"].astype(bool).to_numpy() for t in (L, S))
    sv = vm2[S["bus"]].to_numpy()
    return {"bus": bus, "branch": branch, "gen": _gen_results(case, bus, b_lf),
            "load": _frame(L, np.where(on_l, L["p"].to_numpy(float), 0.0),
                           np.where(on_l, L["q"].to_numpy(float), 0.0)),
            "shunt": _frame(S, np.where(on_s, S["g"].to_numpy(float) * sv, 0.0),
                            np.where(on_s, -S["b"].to_numpy(float) * sv, 0.0))}


def _frame(t, p, q):
    return pd.DataFrame({"bus": t["bus"].to_numpy(), "p": p, "q": q},
                        index=pd.Index(t["id"], name="id"))


def _gen_results(case, bus, b_lf):
    G = case.gen
    on = G["in_service"].astype(bool).to_numpy()
    p = np.where(on, G["p"].to_numpy(float), 0.0)
    q = np.where(on, G["q"].to_numpy(float), 0.0)
    lo, hi = G["qmin"].to_numpy(float), G["qmax"].to_numpy(float)
    pd_, qd = (b_lf[c].to_numpy(float) * case.base for c in ("Pd", "Qd"))
    typ, _ = bus_types(case)
    at = {}                       # bus row -> its in-service generators, in table order
    row = {bid: i for i, bid in enumerate(case.bus["id"])}
    for k in np.flatnonzero(on):
        at.setdefault(row[G["bus"].iloc[k]], []).append(k)
    for i, k in at.items():
        if typ[i] == "PQ":        # Q (and P) as scheduled
            continue
        k = np.array(k)
        qtot = bus["q"].iloc[i] + qd[i]
        span = hi[k].sum() - lo[k].sum()
        q[k] = lo[k] + (qtot - lo[k].sum()) / span * (hi[k] - lo[k]) \
            if np.isfinite(span) and span > 0 else qtot / len(k)
        if typ[i] == "Slack":
            p[k[0]] = bus["p"].iloc[i] + pd_[i] - p[k[1:]].sum()
    return _frame(G, p, q)


# --------------------------------------------------------------------- JSON
def to_dict(case):
    """{"model": 1, name, base, freq, bus: [records], branch: [...], ...};
    NaN becomes None."""
    out = {"model": 1, "name": case.name, "base": case.base, "freq": case.freq}
    for k, t in case.tables().items():
        out[k] = [{c: (None if isinstance(v, float) and np.isnan(v) else
                       v.item() if hasattr(v, "item") else v) for c, v in r.items()}
                  for r in t.to_dict(orient="records")]
    return out


def from_dict(d):
    """Case from to_dict's form (missing columns get their defaults)."""
    case = Case(name=d.get("name", ""), base=float(d.get("base", 100.0)),
                freq=float(d.get("freq", 50.0)))
    for k in KINDS:
        t = table(k, d.get(k) or [])
        for c, default in COLUMNS[k].items():
            if isinstance(default, float):
                t[c] = pd.to_numeric(t[c], errors="coerce").astype(float)
            elif isinstance(default, bool):
                t[c] = t[c].fillna(default).astype(bool)
        setattr(case, k, t)
    return case
