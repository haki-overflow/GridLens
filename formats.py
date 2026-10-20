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
    """MATPOWER case (version 2): mpc.baseMVA, mpc.bus, mpc.gen, mpc.branch
    and optional mpc.bus_name. Generator data are summed per bus; buses of
    type 4 (isolated) are left out with their branches."""
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

    rows = []
    for k, r in enumerate(bus_m):
        num, typ, pd_, qd, gs, bs, _, vm, va, kv = r[:10]
        rows.append(dict(Num=int(num), Name=names[k].strip() if k < len(names) else "",
                         Type=int(typ), V=vm, Va=va, kV=kv, Pg=0.0, Qg=0.0,
                         Pd=pd_ / base, Qd=qd / base, Qmin=np.nan, Qmax=np.nan,
                         Gs=gs / base, Bs=bs / base))
    bus = pd.DataFrame(rows)
    iso = bus["Type"] == 4
    if iso.any():
        notes.append(f"{int(iso.sum())} isolated bus(es) (type 4) were left out.")
    at = {n: i for i, n in enumerate(bus["Num"])}
    has_gen = set()
    for g in gen_m or []:
        gb, pg, qg, qmax, qmin, vg = g[:6]
        status = g[7] if len(g) > 7 else 1
        i = at.get(int(gb))
        if i is None or status <= 0:
            continue
        first = i not in has_gen
        has_gen.add(i)
        bus.loc[i, "Pg"] += pg / base
        bus.loc[i, "Qg"] += qg / base
        bus.loc[i, "Qmax"] = (0 if first else bus.loc[i, "Qmax"]) + qmax / base
        bus.loc[i, "Qmin"] = (0 if first else bus.loc[i, "Qmin"]) + qmin / base
        if first:
            bus.loc[i, "V"] = vg
    lost_pv = [int(bus["Num"][i]) for i in range(len(bus))
               if bus["Type"][i] == 2 and i not in has_gen]
    if lost_pv:
        notes.append("PV buses with no generator in service were made PQ: "
                     + ", ".join(map(str, lost_pv)) + ".")
    bus["Type"] = [("Slack" if t == 3 else "PV" if t == 2 and i in has_gen else "PQ")
                   for i, t in enumerate(bus["Type"])]
    bus = bus[~iso.to_numpy()].reset_index(drop=True)
    bus["kV"] = bus["kV"].where(bus["kV"] > 0)   # 0 = not given

    br = []
    for r in br_m:
        f, t, rr, xx, bb, rate = r[:6]
        ratio = r[8] if len(r) > 8 else 0.0
        shift = r[9] if len(r) > 9 else 0.0
        status = r[10] if len(r) > 10 else 1.0
        br.append(dict(From=int(f), To=int(t), R=rr, X=xx, B=bb, Tap=ratio or 1.0,
                       Shift=shift, Rate=rate, InService=1 if status > 0 else 0,
                       Kind="trafo" if ratio or shift else "line"))
    lines = pd.DataFrame(br, columns=LINE_COLS)
    lines = _renumber(bus, lines, notes)
    return _case(name, base, bus[BUS_COLS], lines, notes)


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
