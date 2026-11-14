"""A4: the full 8,760-hour chain against pvlib ModelChain (physics 01 PV-06, PV-09, section 7).

Tolerance from section 7: 1e-4 relative on annual AC energy, 0.01 W per hour.
Inputs are synthetic clear-sky years, so this tests the chain, not a site.
"""
import numpy as np
import pytest

pytest.importorskip("pvlib")

from a4_reference import modelchain, ours, plane_inputs, synthetic_clear_sky_year  # noqa: E402

from backend.analysis.physics.pv import PV09_SCENARIOS, annual_energy, transmitted_irradiance

ANNUAL_REL = 1e-4
HOURLY_W = 0.01


def _compare(loc, weather, tilt, az, pdc0_w, shading_percent, **scenario):
    mine = ours(loc, weather, tilt, az, shading_percent=shading_percent, **scenario)
    mc = modelchain(loc, weather, tilt, az, pdc0_w, shading_percent=shading_percent, **scenario)
    ref_ac_w = np.clip(mc.results.ac.to_numpy(), 0.0, None)
    my_ac_w = mine.ac_kwh_per_kw * pdc0_w  # kWh per kW per hour * W -> W over the hour
    assert np.max(np.abs(my_ac_w - ref_ac_w)) < HOURLY_W
    assert my_ac_w.sum() == pytest.approx(ref_ac_w.sum(), rel=ANNUAL_REL)
    return mine, mc


@pytest.fixture(scope="module")
def la_year():
    return synthetic_clear_sky_year(34.05, -118.25, altitude=90.0, tz="Etc/GMT+8")


@pytest.fixture(scope="module")
def golden_house_year():
    return synthetic_clear_sky_year(34.0935, -118.3171, altitude=90.0, tz="Etc/GMT+8")


@pytest.fixture(scope="module")
def houston_year():
    return synthetic_clear_sky_year(29.8, -95.4, altitude=15.0, tz="Etc/GMT+6")


def test_pv06_worked_example_whole_year(la_year):
    """PV-06 table: 6 kW, tilt 20, south, close-mount row, shading loss 0."""
    loc, w = la_year
    mine, mc = _compare(loc, w, 20.0, 180.0, 6000.0, 0.0)
    p = plane_inputs(loc, w, 20.0, 180.0)
    assert mine.poa_global_w_m2.sum() / 1000 == pytest.approx(2543.682, abs=1e-3)
    etr = transmitted_irradiance(p["poa_beam"], p["poa_sky_diffuse"], p["poa_ground"], p["incidence_deg"])
    assert etr.sum() / 1000 == pytest.approx(2498.739, abs=1e-3)
    assert 6 * mine.dc_net_w_per_kw.sum() / 1000 == pytest.approx(11832.986, abs=1e-3)
    energy = annual_energy(mine.ac_kwh_per_kw, pdc0_kw=6.0, month=w.index.month)
    assert energy["annual_kwh"] == pytest.approx(11358.305, abs=1e-3)
    assert round(energy["yield_kwh_per_kw"]) == 1893
    assert len(energy["monthly_kwh"]) == 12
    assert sum(energy["monthly_kwh"]) == pytest.approx(energy["annual_kwh"], rel=1e-12)


PV09_TABLE = {
    180.0: (1807.5, 1867.5, 1853.1),
    90.0: (1601.0, 1540.8, 1458.1),
    270.0: (1599.8, 1538.7, 1455.0),
    0.0: (1365.3, 1104.2, 863.7),
}


@pytest.mark.parametrize("azimuth", sorted(PV09_TABLE))
def test_pv09_golden_house_twelve_yields(golden_house_year, azimuth):
    """PV-09 table: 14 x 430 W, PVWatts default losses incl. 3 % shading, three tilts."""
    loc, w = golden_house_year
    for tilt, printed in zip((15.8, 28.4, 41.1), PV09_TABLE[azimuth]):
        mine, _ = _compare(loc, w, tilt, azimuth, 6020.0, 3.0)
        assert mine.annual_kwh_per_kw == pytest.approx(printed, abs=0.05)


@pytest.mark.parametrize("scenario", sorted(PV09_SCENARIOS))
def test_houston_clear_sky_year_scenarios(houston_year, scenario):
    """Second golden site, every PV-09 temperature/gamma scenario, default losses."""
    loc, w = houston_year
    mine, _ = _compare(loc, w, 20.0, 180.0, 6000.0, 3.0, **PV09_SCENARIOS[scenario])
    assert 1000 < mine.annual_kwh_per_kw < 2500


def test_pv09_bounds_order(houston_year):
    loc, w = houston_year
    yields = {k: ours(loc, w, 20.0, 180.0, **v).annual_kwh_per_kw for k, v in PV09_SCENARIOS.items()}
    assert yields["low"] < yields["expected"] < yields["high"]
