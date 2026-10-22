"""Case file readers: MATPOWER .m, IEEE common data format (.cdf / .txt) and
the GridLens CSV templates.

Every reader returns a case dict {name, base, bus, lines, notes} in the
GridLens data model, in per unit: bus rows in file order (lines refer to bus
rows, 1..N, like the rest of GridLens), the file's own bus numbers kept in
the label column Num, names in Name. No maths beyond unit scaling; the
solver and gridcore.prep_case do the rest.
"""
import io
import re

import numpy as np
import pandas as pd

import model

BUS_COLS = ["Num", "Name", "Type", "V", "Va", "kV", "Pg", "Qg", "Pd", "Qd",
            "Qmin", "Qmax", "Gs", "Bs"]
LINE_COLS = ["From", "To", "R", "X", "B", "Tap", "Shift", "Rate", "InService", "Kind"]


def read_case(filename, text, lines_text=None):
    """Pick the reader from the file name (and contents)."""
    low = filename.lower()
    if low.endswith(".m") or "mpc.bus" in text:
        return read_matpower(text, _stem(filename))
    if low.endswith(".csv"):
        return read_csv(text, lines_text, _stem(filename))
    if "BUS DATA FOLLOWS" in text.upper():
        return read_cdf(text, _stem(filename))
    raise ValueError("unknown file type: use a MATPOWER .m file, an IEEE common data "
                     "format file (.cdf / .txt) or the GridLens CSV templates.")


def _stem(filename):
    name = re.split(r"[\\/]", filename)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


def _case(name, base, bus, lines, notes):
    bus = bus.reset_index(drop=True)
    lines = lines.reset_index(drop=True)
    return dict(name=name, base=float(base), bus=bus, lines=lines, notes=notes)


def _renumber(bus, lines, notes):
    """File bus numbers (bus.Num) -> row numbers in lines.From / To."""
    row = {int(n): i + 1 for i, n in enumerate(bus["Num"])}
    bad = [(f, t) for f, t in zip(lines["From"], lines["To"])
           if int(f) not in row or int(t) not in row]
    if bad:
        notes.append(f"{len(bad)} branch(es) refer to buses that are not in the file "
                     "and were left out.")
        keep = [int(f) in row and int(t) in row for f, t in zip(lines["From"], lines["To"])]
        lines = lines[keep]
    lines = lines.assign(From=[row[int(f)] for f in lines["From"]],
                         To=[row[int(t)] for t in lines["To"]])
    if list(bus["Num"]) != list(range(1, len(bus) + 1)):
        notes.append("Bus numbers in the file are kept in the Num column; lines refer to "
                     "bus rows 1.." f"{len(bus)}.")
    return lines


# ------------------------------------------------------------------ MATPOWER
def _matrix(text, field):
    m = re.search(rf"mpc\.{field}\s*=\s*\[(.*?)\]\s*;", text, re.S)
    if not m:
        return None
    rows = []
    for raw in re.split(r"[;\n]", m.group(1)):
        vals = [float(v) for v in re.split(r"[\s,]+", raw.strip()) if v]
        if vals:
            rows.append(vals)
    return rows


def read_matpower(text, name="case"):
    """MATPOWER case (version 2) in the v1 tables: read_matpower_model, then
    generators, loads and shunts summed per bus (model.to_tables)."""
    case, notes = read_matpower_model(text, name)
    bus, lines = model.to_tables(case)
    if list(bus["Num"]) != list(range(1, len(bus) + 1)):
        notes.append("Bus numbers in the file are kept in the Num column; lines refer to "
                     "bus rows 1.." f"{len(bus)}.")
    return _case(case.name, case.base, bus[BUS_COLS], lines[LINE_COLS], notes)


def read_matpower_model(text, name="case"):
    """MATPOWER case (version 2): mpc.baseMVA, mpc.bus, mpc.gen, mpc.branch and
    optional mpc.bus_name -> (model.Case, notes). Every generator is kept with
    its own limits and status (gen<row>); a generator holds a voltage at bus
    types 2 and 3, and the bus starts at the voltage of its first generator in
    service. Loads and shunts come from the bus rows; buses of type 4
    (isolated) are left out with their branches and generators."""
    text = re.sub(r"%[^\n]*", "", text)
    m = re.search(r"function\s+mpc\s*=\s*(\w+)", text)
    name = m.group(1) if m else name
    m = re.search(r"mpc\.baseMVA\s*=\s*([-+\d.eE]+)", text)
    if not m:
        raise ValueError("mpc.baseMVA not found: is this a MATPOWER case file?")
    base = float(m.group(1))
    bus_m, gen_m, br_m = (_matrix(text, f) for f in ("bus", "gen", "branch"))
    if not bus_m or br_m is None:
        raise ValueError("mpc.bus or mpc.branch not found in the file.")
    names = re.search(r"mpc\.bus_name\s*=\s*\{(.*?)\}\s*;", text, re.S)
    names = re.findall(r"'([^']*)'", names.group(1)) if names else []
    notes = []

    B = np.array([r[:10] for r in bus_m], float)
    num, typ = B[:, 0].astype(int), B[:, 1].astype(int)
    keep = typ != 4
    if not keep.all():
        notes.append(f"{int((~keep).sum())} isolated bus(es) (type 4) were left out.")
    at = {n: i for i, n in enumerate(num) if keep[i]}
    vm = B[:, 7].copy()
    gens, held = [], set()        # held: bus rows with a generator in service
    for j, g in enumerate(gen_m or []):
        i = at.get(int(g[0]))
        if i is None:
            continue
        on = (g[7] if len(g) > 7 else 1) > 0
        if on and i not in held:
            vm[i] = g[5]                       # the bus starts at its first generator's voltage
            held.add(i)
        gens.append(dict(id=f"gen{j + 1}", bus=f"bus{num[i]}", p=g[1], q=g[2], qmax=g[3],
                         qmin=g[4], vset=g[5] if typ[i] in (2, 3) else np.nan, in_service=on))
    lost_pv = [int(num[i]) for i in range(len(num)) if typ[i] == 2 and i not in held]
    if lost_pv:
        notes.append("PV buses with no generator in service were made PQ: "
                     + ", ".join(map(str, lost_pv)) + ".")
    k = np.flatnonzero(keep)
    case = model.Case(name=name, base=base)
    case.bus = model.table("bus", {
        "id": [f"bus{n}" for n in num[k]], "num": num[k],
        "name": [names[i].strip() if i < len(names) else "" for i in k],
        "kv": np.where(B[k, 9] > 0, B[k, 9], np.nan), "slack": typ[k] == 3, "vm": vm[k],
        "va": B[k, 8]})
    case.gen = model.table("gen", gens)
    for kind, (a, c), cols in (("load", ("p", "q"), (2, 3)), ("shunt", ("g", "b"), (4, 5))):
        has = k[(B[k, cols[0]] != 0) | (B[k, cols[1]] != 0)]
        setattr(case, kind, model.table(kind, {
            "id": [f"{kind}{n + 1}" for n in range(len(has))],
            "bus": [f"bus{num[i]}" for i in has], a: B[has, cols[0]], c: B[has, cols[1]]}))
    br = [r for r in br_m if int(r[0]) in at and int(r[1]) in at]
    if len(br) < len(br_m):
        notes.append(f"{len(br_m) - len(br)} branch(es) refer to buses that are not in the file "
                     "and were left out.")
    count = {"line": 0, "trafo": 0}
    rows = []
    for r in br:
        ratio = r[8] if len(r) > 8 else 0.0
        shift = r[9] if len(r) > 9 else 0.0
        kind = "trafo" if ratio or shift else "line"
        count[kind] += 1
        rows.append(dict(id=f"{kind}{count[kind]}", kind=kind, from_bus=f"bus{int(r[0])}",
                         to_bus=f"bus{int(r[1])}", r=r[2], x=r[3], b=r[4], rate=r[5],
                         tap=ratio or 1.0, shift=shift,
                         in_service=(r[10] if len(r) > 10 else 1.0) > 0))
    case.branch = model.table("branch", rows)
    return case, notes


# ------------------------------------------------------- IEEE common format
def _f(line, a, b):
    """Columns a..b (1-based, inclusive) as a float; blank = 0."""
    s = line[a - 1:b].strip()
    return float(s) if s else 0.0


def read_cdf(text, name="case"):
    """IEEE common data format, columns as in MATPOWER's cdf2mpc."""
    lines_in = text.splitlines()
    if not lines_in:
        raise ValueError("the file is empty.")
    title = lines_in[0].ljust(80)
    try:
        base = float(title[31:37])
    except ValueError:
        raise ValueError("the base MVA (columns 32-37 of the first line) is not a number.") from None
    name = title[45:].strip() or name
    i = next((k for k, s in enumerate(lines_in) if s.upper().startswith("BUS DATA FOLLOWS")), None)
    if i is None:
        raise ValueError("'BUS DATA FOLLOWS' not found.")
    rows = []
    for s in lines_in[i + 1:]:
        if s.strip().startswith("-999"):
            break
        s = s.ljust(130)
        typ = int(_f(s, 25, 26))
        vdes = _f(s, 85, 90)
        gen = typ >= 2
        rows.append(dict(Num=int(_f(s, 1, 4)), Name=s[5:17].strip(),
                         Type="Slack" if typ == 3 else "PV" if typ == 2 else "PQ",
                         V=vdes if gen and vdes > 0 else _f(s, 28, 33), Va=_f(s, 34, 40),
                         kV=_f(s, 77, 83), Pg=_f(s, 60, 67) / base, Qg=_f(s, 68, 75) / base,
                         Pd=_f(s, 41, 49) / base, Qd=_f(s, 50, 59) / base,
                         Qmin=_f(s, 99, 106) / base if gen else np.nan,
                         Qmax=_f(s, 91, 98) / base if gen else np.nan,
                         Gs=_f(s, 107, 114), Bs=_f(s, 115, 122)))
    j = next((k for k, s in enumerate(lines_in) if s.upper().startswith("BRANCH DATA FOLLOWS")), None)
    if j is None:
        raise ValueError("'BRANCH DATA FOLLOWS' not found.")
    br = []
    for s in lines_in[j + 1:]:
        if s.strip().startswith("-999"):
            break
        s = s.ljust(130)
        ratio, shift = _f(s, 77, 82), _f(s, 84, 90)
        br.append(dict(From=int(_f(s, 1, 4)), To=int(_f(s, 6, 9)), R=_f(s, 20, 29),
                       X=_f(s, 30, 40), B=_f(s, 41, 50), Tap=ratio or 1.0, Shift=shift,
                       Rate=_f(s, 51, 55), InService=1,
                       Kind="trafo" if int(_f(s, 19, 19)) > 0 or ratio or shift else "line"))
    notes = []
    bus = pd.DataFrame(rows, columns=BUS_COLS)
    bus["kV"] = bus["kV"].where(bus["kV"] > 0)   # 0 = not given
    lines = _renumber(bus, pd.DataFrame(br, columns=LINE_COLS), notes)
    return _case(name, base, bus, lines, notes)


# ----------------------------------------------------------------- CSV
def read_csv(bus_text, lines_text=None, name="case"):
    """The GridLens CSV templates: a bus table (Type, V, Pg, Qg, Pd, Qd, Bs,
    optional Num, Name, kV, Gs, Qmin, Qmax, x, y) and a line table (From, To,
    R, X, B, Tap, optional Shift, Rate, InService, Kind), already in per unit.
    Either file may come first; the one with From/To columns is the lines."""
    a = pd.read_csv(io.StringIO(bus_text))
    b = pd.read_csv(io.StringIO(lines_text)) if lines_text else pd.DataFrame(columns=["From", "To"])
    if {"From", "To"} <= set(a.columns):
        a, b = b, a
    if "Type" not in a.columns:
        raise ValueError("the bus CSV needs a Type column (Slack / PV / PQ).")
    notes = [] if lines_text else ["Only a bus table was given; add lines (Network > "
                                   "Data tables) or import the line CSV too."]
    return _case(name, 100.0, a, b, notes)
