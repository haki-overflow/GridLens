"""Real units -> per unit (units.py)."""
import pandas as pd
import pytest
import topics



def _example():
    e = topics.UNITS_EXAMPLE
    return topics.to_pu(e["sbase"], e["ref_bus"], e["ref_kv"], e["buses"],
                       e["lines"], e["trafos"])


def test_zone_base_kv_follows_transformer_ratio():
    r = _example()
    assert list(r["kv"]) == [11.0, 132.0, 132.0, 132.0]
    assert r["zones"]["Zbase (Ω)"].tolist() == pytest.approx([1.21, 174.24])


def test_line_conversion_ohm_per_km_and_microsiemens():
    l = _example()["lines"].iloc[0]          # 2-3: 0.12+j0.4 ohm/km, 2.8 uS/km, 80 km
    zb = 132.0 ** 2 / 100.0
    assert l["R"] == pytest.approx(0.12 * 80 / zb)
    assert l["X"] == pytest.approx(0.4 * 80 / zb)
    assert l["B"] == pytest.approx(2.8e-6 * 80 * zb)


def test_charging_mvar_and_loads():
    r = _example()
    assert r["lines"].iloc[2]["B"] == pytest.approx(10.0 / 100.0)   # 10 MVAr
    assert r["bus"]["Pd"].tolist() == pytest.approx([0, 0, 1.0, 0.2])
    assert r["bus"]["Qmax"].iloc[3] == pytest.approx(0.25)


def test_transformer_rebased_to_system_base():
    tr = pd.DataFrame({"From": [1], "To": [2], "kV From": [11.0], "kV To": [132.0],
                       "MVA": [50.0], "R": [0.0], "X": [0.1], "Tap": [1.0]})
    e = topics.UNITS_EXAMPLE
    r = topics.to_pu(100.0, 1, 11.0, e["buses"], e["lines"], tr)
    t = r["lines"].iloc[-1]
    assert t["X"] == pytest.approx(0.1 * 100 / 50)     # Z_new = Z_old * S_new/S_old
    assert t["Tap"] == pytest.approx(1.0)


def test_rated_voltage_mismatch_gives_off_nominal_tap():
    # base kV 11 on bus 1 but the transformer is rated 10.5/132 kV
    tr = pd.DataFrame({"From": [1], "To": [2], "kV From": [10.5], "kV To": [132.0],
                       "MVA": [100.0], "R": [0.0], "X": [0.1], "Tap": [1.0]})
    e = topics.UNITS_EXAMPLE
    r = topics.to_pu(100.0, 2, 132.0, e["buses"], e["lines"], tr)
    assert r["kv"][0] == pytest.approx(10.5)            # zone follows the rating
    assert r["lines"].iloc[-1]["X"] == pytest.approx(0.1)


def test_unreachable_bus_is_reported():
    e = topics.UNITS_EXAMPLE
    with pytest.raises(ValueError, match="No base kV"):
        topics.to_pu(100.0, 1, 11.0, e["buses"], e["lines"], e["trafos"].iloc[:0])
