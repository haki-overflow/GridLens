"""Real units -> per unit, the way textbook problems give the data.

Input tables (one row per item, buses numbered by row order like the rest
of GridLens):

buses   Type, V (pu), Pg (MW), Qg (MVAr), Pd (MW), Qd (MVAr),
        Qmin (MVAr), Qmax (MVAr), Shunt (MVAr at 1 pu, + = capacitive)
lines   From, To, R, X, Z unit ("ohm" | "ohm/km"), Length (km),
        B, B unit ("uS" | "uS/km" | "MVAr" = total charging at base kV)
trafos  From, To, kV From, kV To (rated), MVA (rating),
        R, X (pu on own rating), Tap (off-nominal, at the From side)

Zones: buses joined by lines share a base kV; a transformer moves to the
next zone with base_to = base_from * kV_To / kV_From. The base kV of one
reference bus is given, the rest follows.
"""
import numpy as np
import pandas as pd

Z_UNITS = ("ohm", "ohm/km")
B_UNITS = ("uS", "uS/km", "MVAr")


def _num(df, col, fill=0.0):
    return pd.to_numeric(df[col], errors="coerce").fillna(fill).to_numpy(float) \
        if col in df else np.full(len(df), fill)


def zones(n, lines, trafos, ref_bus, ref_kv):
    """Zone index and base kV per bus. Raises ValueError on a bus that no
    line or transformer reaches, or on a loop with inconsistent ratios."""
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for f, t in zip(_num(lines, "From").astype(int), _num(lines, "To").astype(int)):
        parent[find(f - 1)] = find(t - 1)
    roots = sorted({find(i) for i in range(n)})
    zone = np.array([roots.index(find(i)) for i in range(n)])
    kv = {zone[ref_bus - 1]: float(ref_kv)}
    links = [(zone[int(f) - 1], zone[int(t) - 1], float(kf), float(kt))
             for f, t, kf, kt in zip(_num(trafos, "From"), _num(trafos, "To"),
                                     _num(trafos, "kV From"), _num(trafos, "kV To"))]
    changed = True
    while changed:
        changed = False
        for zf, zt, kf, kt in links:
            for a, b, ka, kb in ((zf, zt, kf, kt), (zt, zf, kt, kf)):
                if a in kv:
                    want = kv[a] * kb / ka
                    if b not in kv:
                        kv[b] = want
                        changed = True
                    elif abs(kv[b] - want) > 1e-6 * want:
                        raise ValueError(
                            f"Transformer ratios disagree around zone {b + 1}: "
                            f"{kv[b]:g} kV vs {want:g} kV.")
    missing = sorted({i + 1 for i in range(n) if zone[i] not in kv})
    if missing:
        raise ValueError("No base kV reaches bus(es) "
                         + ", ".join(map(str, missing))
                         + ": connect them by a line or transformer.")
    return zone, np.array([kv[z] for z in zone])


def to_pu(sbase, ref_bus, ref_kv, buses, lines, trafos):
    """Convert the three real-unit tables to the GridLens per-unit data model.

    Returns dict(bus, lines, kv, zones, table): bus/lines are ready for
    solve_loadflow (bus also carries Qmin/Qmax in pu and kV = base kV),
    zones is the base table per zone and table lists every conversion."""
    n = len(buses)
    zone, kv = zones(n, lines, trafos, ref_bus, ref_kv)
    zbase = kv ** 2 / sbase
    rows = []

    def note(item, given, unit, base, pu):
        rows.append([item, given, unit, base, pu])

    pu = pd.DataFrame({"Type": buses["Type"].astype(str).to_numpy(),
                       "V": _num(buses, "V", 1.0)})
    for col, unit in (("Pg", "MW"), ("Qg", "MVAr"), ("Pd", "MW"), ("Qd", "MVAr")):
        val = _num(buses, col)
        pu[col] = val / sbase
        for i in np.flatnonzero(val):
            note(f"Bus {i + 1} {col}", val[i], unit, f"{sbase:g} MVA", val[i] / sbase)
    sh = _num(buses, "Shunt")
    pu["Bs"] = sh / sbase
    for i in np.flatnonzero(sh):
        note(f"Bus {i + 1} shunt", sh[i], "MVAr", f"{sbase:g} MVA", sh[i] / sbase)
    for col in ("Qmin", "Qmax"):
        val = _num(buses, col, -9999.0 if col == "Qmin" else 9999.0)
        pu[col] = val / sbase
    pu["kV"] = kv

    out = []
    for k, r in lines.reset_index(drop=True).iterrows():
        i, j = int(r["From"]) - 1, int(r["To"]) - 1
        zb, name = zbase[i], f"Line {i + 1}-{j + 1}"
        length = float(r.get("Length", 0) or 0)
        per_km = str(r.get("Z unit", "ohm")) == "ohm/km"
        R = float(r["R"]) * (length if per_km else 1.0)
        X = float(r["X"]) * (length if per_km else 1.0)
        bu, Bv = str(r.get("B unit", "uS")), float(r.get("B", 0) or 0)
        if bu == "MVAr":
            Bpu = Bv / sbase
            note(f"{name} charging", Bv, "MVAr", f"{sbase:g} MVA", Bpu)
        else:
            Bs = Bv * 1e-6 * (length if bu == "uS/km" else 1.0)
            Bpu = Bs * zb
            note(f"{name} B", Bs * 1e6, "µS", f"Ybase {1e6 / zb:.4g} µS", Bpu)
        note(f"{name} R", R, "Ω", f"Zbase {zb:.4g} Ω", R / zb)
        note(f"{name} X", X, "Ω", f"Zbase {zb:.4g} Ω", X / zb)
        out.append([i + 1, j + 1, R / zb, X / zb, Bpu, 1.0])
    for _, r in trafos.reset_index(drop=True).iterrows():
        i, j = int(r["From"]) - 1, int(r["To"]) - 1
        name = f"Trafo {i + 1}-{j + 1}"
        kf, kt, mva = float(r["kV From"]), float(r["kV To"]), float(r["MVA"])
        scale = (sbase / mva) * (kf / kv[i]) ** 2
        R, X = float(r.get("R", 0) or 0), float(r["X"])
        tap = float(r.get("Tap", 1) or 1) * (kf / kt) / (kv[i] / kv[j])
        note(f"{name} X", X, f"pu on {mva:g} MVA, {kf:g} kV",
             f"{sbase:g} MVA, {kv[i]:g} kV", X * scale)
        if R:
            note(f"{name} R", R, f"pu on {mva:g} MVA, {kf:g} kV",
                 f"{sbase:g} MVA, {kv[i]:g} kV", R * scale)
        if abs(tap - 1) > 1e-9:
            note(f"{name} tap", float(r.get("Tap", 1) or 1), "ratio",
                 "nominal", tap)
        out.append([i + 1, j + 1, R * scale, X * scale, 0.0, tap])
    lpu = pd.DataFrame(out, columns=["From", "To", "R", "X", "B", "Tap"])

    zt = pd.DataFrame({"Zone": np.arange(1, zone.max() + 2)})
    zt["Buses"] = [", ".join(str(i + 1) for i in np.flatnonzero(zone == z))
                   for z in range(len(zt))]
    zt["Base kV"] = [kv[zone == z][0] for z in range(len(zt))]
    zt["Zbase (Ω)"] = zt["Base kV"] ** 2 / sbase
    zt["Ibase (A)"] = sbase * 1e3 / (np.sqrt(3) * zt["Base kV"])
    table = pd.DataFrame(rows, columns=["Item", "Given", "Unit", "Base", "Per unit"])
    return dict(bus=pu, lines=lpu, kv=kv, zones=zt, table=table)


EXAMPLE = dict(
    sbase=100.0, ref_bus=1, ref_kv=11.0,
    buses=pd.DataFrame({
        "Type": ["Slack", "PQ", "PQ", "PV"], "V": [1.05, 1.0, 1.0, 1.02],
        "Pg": [0.0, 0.0, 0.0, 60.0], "Qg": [0.0] * 4,
        "Pd": [0.0, 0.0, 100.0, 20.0], "Qd": [0.0, 0.0, 50.0, 10.0],
        "Qmin": [-9999.0, -9999.0, -9999.0, -20.0],
        "Qmax": [9999.0, 9999.0, 9999.0, 25.0], "Shunt": [0.0] * 4}),
    lines=pd.DataFrame({
        "From": [2, 3, 2], "To": [3, 4, 4],
        "R": [0.12, 10.0, 12.0], "X": [0.4, 30.0, 40.0],
        "Z unit": ["ohm/km", "ohm", "ohm"], "Length": [80.0, 0.0, 0.0],
        "B": [2.8, 150.0, 10.0], "B unit": ["uS/km", "uS", "MVAr"]}),
    trafos=pd.DataFrame({
        "From": [1], "To": [2], "kV From": [11.0], "kV To": [132.0],
        "MVA": [100.0], "R": [0.0], "X": [0.1], "Tap": [1.0]}),
)
