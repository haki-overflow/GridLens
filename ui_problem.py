"""Problem input page: textbook-style data in real units -> per unit.

The user types the data the way a textbook question gives it (MVA, kV,
ohms, ohms/km, µS, MVAr, MW); units.to_pu converts it and every converted
value is listed so it can be checked against a hand calculation. "Load
into study" hands the per-unit tables to the main case.
"""
import streamlit as st

import ui_tables
import ui_theme
import units

TABLES = ("buses", "lines", "trafos")


def _init():
    ss = st.session_state
    for k in ("sbase", "ref_bus", "ref_kv"):
        ss.setdefault(f"prob_{k}", units.EXAMPLE[k])


def _editor(where, name, column_config):
    ui_tables.editor(where, f"prob_{name}",
                     lambda: units.EXAMPLE[name].copy(), num_rows="dynamic",
                     column_config=column_config)


def page(load):
    """load(bus_pu, lines_pu, sbase) puts the converted case into the study."""
    _init()
    ss = st.session_state
    st.caption("Enter the data as the question gives it. Buses are numbered "
               "by row. Lines join buses of one voltage zone; transformers "
               "start a new zone (base kV scales with their rated ratio).")
    c = st.columns([1, 1, 1, 1.4], vertical_alignment="bottom")
    ss["prob_sbase"] = c[0].number_input("System base (MVA)", 1.0, 1e5,
                                         float(ss["prob_sbase"]), key="pi_sb")
    ss["prob_ref_bus"] = int(c[1].number_input(
        "Reference bus", 1, 999, int(ss["prob_ref_bus"]), key="pi_rb",
        help="Bus whose base kV is given."))
    ss["prob_ref_kv"] = c[2].number_input("Its base kV", 0.1, 2000.0,
                                          float(ss["prob_ref_kv"]), key="pi_kv")

    tb, tl, tt = st.tabs(["Buses", "Lines", "Transformers"])
    _editor(tb, "buses", {
        "Type": st.column_config.SelectboxColumn(options=["Slack", "PV", "PQ"]),
        "V": st.column_config.NumberColumn("V (pu)", format="%.4f"),
        "Pg": st.column_config.NumberColumn("Pg (MW)"),
        "Qg": st.column_config.NumberColumn("Qg (MVAr)"),
        "Pd": st.column_config.NumberColumn("Pd (MW)"),
        "Qd": st.column_config.NumberColumn("Qd (MVAr)"),
        "Qmin": st.column_config.NumberColumn("Qmin (MVAr)"),
        "Qmax": st.column_config.NumberColumn("Qmax (MVAr)"),
        "Shunt": st.column_config.NumberColumn(
            "Shunt (MVAr)", help="At 1 pu voltage; + capacitive.")})
    _editor(tl, "lines", {
        "From": st.column_config.NumberColumn(step=1),
        "To": st.column_config.NumberColumn(step=1),
        "Z unit": st.column_config.SelectboxColumn(options=list(units.Z_UNITS)),
        "B unit": st.column_config.SelectboxColumn(
            options=list(units.B_UNITS),
            help="µS total, µS/km (× Length), or MVAr total charging."),
        "Length": st.column_config.NumberColumn("Length (km)")})
    _editor(tt, "trafos", {
        "From": st.column_config.NumberColumn(step=1, help="Tap side."),
        "To": st.column_config.NumberColumn(step=1),
        "R": st.column_config.NumberColumn("R (pu own)"),
        "X": st.column_config.NumberColumn("X (pu own)"),
        "Tap": st.column_config.NumberColumn(
            help="Off-nominal ratio at the From side, 1 = nominal.")})

    try:
        t = {k: ss[f"tbl_prob_{k}"] for k in TABLES}
        r = units.to_pu(ss["prob_sbase"], ss["prob_ref_bus"], ss["prob_ref_kv"],
                        t["buses"], t["lines"], t["trafos"])
    except Exception as e:
        st.error(f"Cannot convert: {e}")
        return
    c[3].button("Load into study", type="primary", key="pi_load",
                on_click=load, args=(r["bus"], r["lines"], ss["prob_sbase"],
                                     dict(zones=r["zones"], table=r["table"])),
                help="Replace the Dashboard case with this per-unit data.")

    left, right = st.columns([1, 1.6], gap="medium")
    left.html(ui_theme.section("Base values per zone"))
    left.dataframe(r["zones"].round(4), hide_index=True)
    if (r["lines"]["Tap"] - 1).abs().max() > 1e-9:
        left.caption("Off-nominal taps present: switch Mode to Advanced and "
                     "turn on Transformer taps so the study uses them.")
    if (r["bus"]["Qmax"] < 99).any() or (r["bus"]["Qmin"] > -99).any():
        left.caption("Q limits given: Advanced mode → Generator Q limits "
                     "enforces them.")
    right.html(ui_theme.section("Per-unit conversion"))
    right.dataframe(r["table"].round(6), hide_index=True)
    with st.expander("Per-unit case (what the solver gets)"):
        a, b = st.columns([1.3, 1])
        a.dataframe(r["bus"].round(6), hide_index=True)
        b.dataframe(r["lines"].round(6), hide_index=True)
