"""A5 lighting credit and desk score, LCT-01 to LCT-03 (physics 03 test plan T-LCT)."""
import socket

import numpy as np
import pytest

from backend.analysis.physics.daylight.daylight import daylight_autonomy
from backend.analysis.physics.daylight.lighting import (desk_score, lighting_energy_saved,
                                                        lighting_power_fraction)

E_IN = np.array([101.2, 232.6, 517.7, 569.6, 308.5, 63.3])
TABLE = {  # LCT-01 at 500 lx, f_L,min 0.2, f_P,min 0.3
    "continuous": [0.8229, 0.5929, 0.3000, 0.3000, 0.4601, 0.8892],
    "continuous_off": [0.8229, 0.5929, 0, 0, 0.4601, 0.8892],
    "auto_on_off": [1, 1, 0, 0, 1, 1],
    "stepped": [1, 0.6667, 0, 0, 0.6667, 1],
}
SAVED_500 = {"continuous": 0.4391, "continuous_off": 0.5391, "auto_on_off": 0.3333, "stepped": 0.4444}
SAVED_300 = {"continuous": 0.5430, "continuous_off": 0.6930, "auto_on_off": 0.5000, "stepped": 0.6667}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A5 tests must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.mark.parametrize("ctrl", list(TABLE))
def test_lct01_table(ctrl):
    f = lighting_power_fraction(E_IN, 500, ctrl)
    assert np.allclose(f, TABLE[ctrl], atol=1e-4)
    assert 1 - f.mean() == pytest.approx(SAVED_500[ctrl], abs=1e-4)
    assert 1 - lighting_power_fraction(E_IN, 300, ctrl).mean() == pytest.approx(SAVED_300[ctrl], abs=1e-4)


def test_lct01_identities():
    # the dimming line passes through (f_L,min, f_P,min) and (1, 1)
    e_at_min = 500 * (1 - 0.2)
    assert float(lighting_power_fraction(e_at_min, 500, "continuous")) == pytest.approx(0.3)
    assert float(lighting_power_fraction(0.0, 500, "continuous")) == pytest.approx(1.0)
    # with f_L,min = f_P,min = 0 the mean saved fraction is cDA
    f = lighting_power_fraction(E_IN, 500, "continuous", f_l_min=0.0, f_p_min=0.0)
    cda = daylight_autonomy(E_IN, np.ones(6, bool), 500)["cda"]
    assert 1 - f.mean() == pytest.approx(cda, abs=1e-12)
    assert np.all(lighting_power_fraction(E_IN, 500, "none") == 1)


def test_lct02_example():
    # 2600 occupied hours repeating the toy day; continuous dimming at 500 lx
    e = np.tile(E_IN, 2600 // 6 + 1)[:2600]
    occ = np.ones(2600, bool)
    r = lighting_energy_saved(E_IN, np.ones(6, bool), 500, "continuous", 10, 8)
    assert r["lighting_kwh_saved"].expected * 1000 == pytest.approx(210.8, abs=0.1)   # Wh over 6 h
    full = lighting_energy_saved(e, occ, 500, "continuous", 10, 8)["lighting_kwh_saved"]
    assert full.expected == pytest.approx(0.080 * 2600 * 0.4391, rel=2e-3)
    none = lighting_energy_saved(e, occ, 500, "none", 10, 8)
    s = none["lighting_kwh_saved"]
    assert s.low == 0.0
    pot = lighting_energy_saved(e, occ, 500, "auto_on_off", 10, 8)["lighting_kwh_saved"].expected
    assert s.high == pytest.approx(pot) and s.expected == pytest.approx(0.5 * pot)
    assert "depends on occupants switching lights off" in none["warnings"]
    assert 0.080 * 2600 * 0.4391 == pytest.approx(91.3, abs=0.05)


@pytest.mark.parametrize("da, g, ppd, s_d, s_g, s_c, score", [
    (0.50, 0.03, 8.0, 0.500, 0.850, 0.850, 0.710),
    (0.05, 0.0, 6.0, 0.050, 1.000, 0.950, 0.605),
    (0.90, 0.25, 18.0, 0.900, 0.0, 0.350, 0.465),
])
def test_lct03_rows(da, g, ppd, s_d, s_g, s_c, score):
    r = desk_score(da, g, ppd)
    assert (r["s_d"], r["s_g"], r["s_c"], r["score"]) == pytest.approx((s_d, s_g, s_c, score), abs=1e-4)


def test_lct03_orderings():
    base = desk_score(0.5, 0.05, 10)["score"]
    assert desk_score(0.6, 0.05, 10)["score"] > base
    assert desk_score(0.5, 0.10, 10)["score"] < base
    assert desk_score(0.5, 0.05, 12)["score"] < base
