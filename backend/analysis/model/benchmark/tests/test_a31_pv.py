"""A31 PV-10: the modelled PV yield against PVGIS (physics 01 section 3)."""
import json
import math
import socket
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.schema import BuildingModel, MeasureResult, PropertyBundle
from backend.analysis.model.benchmark import Plane, check_pv, cross_check_pv, pv_inputs, read_weather_csv
from backend.analysis.model.benchmark import pv as P

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"
WEATHER = {"house": "typical_year_hourly.csv", "office": "typical_year_hourly.csv",
           "office_houston": "typical_year_hourly_houston.csv"}
LA = (34.0934917, -118.3171, "America/Los_Angeles")
HOU = (29.7452, -95.4567, "America/Chicago")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A31 must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)


def _weather(name, tz):
    return read_weather_csv(EXAMPLES / "weather" / name, tz, "hour_end")


def test_weather_reader_drops_29_february():
    w = _weather("typical_year_hourly.csv", LA[2])
    assert len(w["ghi"]) == 8760 and w["utc_offset_h"] == -8.0
    assert w["hour"][0] == -0.5 and w["doy"].max() == 365


@pytest.mark.parametrize("site, name", [(LA, "typical_year_hourly.csv"), (HOU, "typical_year_hourly_houston.csv")])
def test_hay_davies_against_pvlib(site, name):
    """IRR-07 with the Spencer sun against pvlib's SPA and haydavies on the same weather: annual POA."""
    pvlib = pytest.importorskip("pvlib")
    lat, lon, tz = site
    w = _weather(name, tz)
    frame = pd.read_csv(EXAMPLES / "weather" / name)
    stamps = pd.DatetimeIndex(pd.to_datetime(frame.time_local)).tz_localize(f"Etc/GMT{int(-w['utc_offset_h']):+d}")
    keep = ~((stamps.month == 2) & (stamps.day == 29))
    frame, times = frame[keep], stamps[keep] - pd.Timedelta("30min")
    sp = pvlib.solarposition.get_solarposition(times, lat, lon)
    extra = pvlib.irradiance.get_extra_radiation(times, solar_constant=1367.0)
    for tilt, az in ((20, 180), (1.2, 180), (15, 180), (30, 90), (20, 356.4)):
        ref = pvlib.irradiance.get_total_irradiance(tilt, az, sp.zenith, sp.azimuth, frame.dni_w_m2.values,
                                                   frame.ghi_w_m2.values, frame.dhi_w_m2.values,
                                                   dni_extra=extra, model="haydavies", albedo=P.ALBEDO)
        ref_kwh = float(np.nansum(np.where(sp.zenith < 90, ref["poa_global"], 0.0))) / 1000.0
        assert P.plane_irradiation(w, lat, lon, tilt, az) == pytest.approx(ref_kwh, rel=0.01), (tilt, az)


@pytest.mark.parametrize("site, name", [(LA, "typical_year_hourly.csv"), (HOU, "typical_year_hourly_houston.csv")])
def test_clear_sky_ratio_within_its_allowance(site, name):
    """CLEAR_SKY_EXTRA: over tilts 0 to 45 and eight azimuths the clear-sky transposition ratio stays
    within 6 % of the weather-file ratio (largest measured: 5.8 %, LA, 45 degrees facing east)."""
    lat, lon, tz = site
    w = _weather(name, tz)
    cs = P.clear_sky_year(lat, lon, w["utc_offset_h"])
    for tilt, az in ((t, a) for t in range(0, 50, 5) for a in range(0, 360, 45)):
        rw = P.plane_irradiation(w, lat, lon, tilt, az) / P.plane_irradiation(w, lat, lon, 20, 180)
        rc = P.plane_irradiation(cs, lat, lon, tilt, az) / P.plane_irradiation(cs, lat, lon, 20, 180)
        assert abs(rc - rw) <= P.CLEAR_SKY_EXTRA, (tilt, az, rc, rw)


def test_tolerance():
    assert P.pv_tolerance(0.02301, False) == pytest.approx(math.hypot(1.96 * 0.02301, 0.05), rel=1e-9)
    assert P.pv_tolerance(0.02301, False) == pytest.approx(0.0673, abs=5e-5)
    assert P.pv_tolerance(None, True) == pytest.approx(math.hypot(1.96 * 0.04, 0.05) + 0.06)


def test_worked_example_golden_house():
    """PV-10 worked example: the golden house design against PVGIS 1754.23 kWh/kWp."""
    w = _weather("typical_year_hourly.csv", LA[2])
    r = cross_check_pv(3768.3, 2.15, [Plane(20.0, 176.4, 2.15)], 1754.23, 0.02301, LA[0], LA[1],
                       losses_percent=11.42, shading_fraction=1 - 3768.3 / 3884.85, weather=w)
    assert r.status == "checked" and r.within
    assert r.loss_ratio == pytest.approx((1 - 0.1142) * 0.96 / 0.86, abs=1e-4)
    assert r.transposition_ratio == pytest.approx(0.9977, abs=2e-4)
    assert r.expected_kwh_per_kw == pytest.approx(1730.6, abs=0.3)
    assert r.deviation == pytest.approx(0.0441, abs=5e-4)
    assert r.warnings == []


@pytest.mark.parametrize("factor, word", [(1.25, "above"), (0.75, "below")])
def test_out_of_tolerance_warns(factor, word):
    w = _weather("typical_year_hourly.csv", LA[2])
    r = cross_check_pv(1730.6 * factor, 1.0, [Plane(20.0, 176.4)], 1754.23, 0.02301, LA[0], LA[1],
                       losses_percent=11.4182, weather=w)
    assert not r.within and len(r.warnings) == 1 and word in r.warnings[0]


def test_clear_sky_fallback_says_so():
    r = cross_check_pv(1730.6, 1.0, [Plane(20.0, 180.0)], 1754.23, 0.02301, LA[0], LA[1],
                       losses_percent=11.4182, timezone=LA[2])
    assert r.transposition_source == "clear-sky year" and r.within
    assert r.tolerance == pytest.approx(P.pv_tolerance(0.02301, True), abs=5e-5)
    assert any("clear-sky" in x for x in r.warnings)


@pytest.mark.parametrize("kwargs, words", [
    (dict(pvgis_kwh_per_kw=None), "no PVGIS"),
    (dict(annual_kwh=None), "no PV design"),
    (dict(lat=None), "no site coordinates"),
    (dict(planes=[]), "no plane orientation"),
])
def test_missing_inputs_are_not_checked(kwargs, words):
    args = dict(annual_kwh=3768.3, system_kw_dc=2.15, planes=[Plane(20.0, 176.4, 2.15)], pvgis_kwh_per_kw=1754.23,
                pvgis_sd_fraction=0.02301, lat=LA[0], lon=LA[1])
    args.update(kwargs)
    r = cross_check_pv(**args)
    assert r.status == "not_checked" and words in r.reason and len(r.warnings) == 1


def _golden(folder):
    d = EXAMPLES / folder
    bundle = PropertyBundle.model_validate_json((d / "property_bundle.json").read_text())
    model = BuildingModel.model_validate_json((d / "building_model.json").read_text())
    pv = next(MeasureResult.model_validate(m) for m in json.loads((d / "measures.json").read_text())
              if m["measure_id"] == "PV_ROOF")
    return bundle, model, pv


def test_pv_inputs_read_shading_and_racks():
    _, model, pv = _golden("house")
    i = pv_inputs(pv.solar, model.roof_planes, pv.params)
    # #330: the house roof is A11's parametric Vexcel roof (the example's splat planes were hand-made)
    assert i["losses_percent"] == pytest.approx(P.PVWATTS_LOSSES_NO_SHADING)
    assert i["shading_fraction"] == pytest.approx(0.03, abs=2e-4)
    assert [(p.tilt_deg, p.azimuth_deg) for p in i["planes"]] == [(28.4, 176.4)]
    _, model, pv = _golden("office")
    i = pv_inputs(pv.solar, model.roof_planes, pv.params)
    assert i["losses_percent"] == pytest.approx(P.PVWATTS_LOSSES_NO_SHADING)
    assert i["shading_fraction"] == pytest.approx(0.03, abs=2e-4)          # 14.08 = 11.42 and 3 % shading
    assert [(p.tilt_deg, p.azimuth_deg) for p in i["planes"]] == [(15.0, 180.0)]    # flat plane, LAY-02 rack
    no_losses = pv.solar.model_copy(update={"losses_percent": None})
    assert pv_inputs(no_losses, model.roof_planes)["shading_fraction"] == pytest.approx(0.03, abs=2e-4)


# Where each golden example's PV_ROOF design lands against its PVGIS figure (reported in the PR).
# #330: the building-mounted PVGIS figures and the real designs.
GOLDEN = {"house": (1653.2, 1676.9, -0.0141), "office": (1599.4, 1630.0, -0.0187),
          "office_houston": (1434.6, 1323.2, 0.0841)}


@pytest.mark.parametrize("folder", sorted(GOLDEN))
def test_golden_examples(folder):
    bundle, model, pv = _golden(folder)
    warnings, r = check_pv(pv.solar, model.roof_planes, bundle.climate, params=pv.params,
                           weather_csv=str(EXAMPLES / "weather" / WEATHER[folder]))
    unshaded, expected, deviation = GOLDEN[folder]
    assert r.status == "checked" and r.transposition_source == "weather file"
    assert r.modelled_unshaded_kwh_per_kw == pytest.approx(unshaded, abs=0.2)
    assert r.expected_kwh_per_kw == pytest.approx(expected, abs=0.3)
    assert r.deviation == pytest.approx(deviation, abs=5e-4)
    assert r.within and warnings == []


def test_check_pv_without_design_or_pvgis():
    bundle, model, pv = _golden("house")
    warnings, r = check_pv(None, model.roof_planes, bundle.climate)
    assert r.status == "not_checked" and "no PV design" in r.reason and len(warnings) == 1
    climate = bundle.climate.model_copy(update={"pvgis_annual_kwh_per_kw": None})
    warnings, r = check_pv(pv.solar, model.roof_planes, climate, params=pv.params)
    assert r.status == "not_checked" and "no PVGIS" in r.reason
    warnings, r = check_pv(pv.solar, model.roof_planes, bundle.climate, params=pv.params,
                           weather_csv="/nonexistent/weather.csv")
    assert r.status == "checked" and r.transposition_source == "clear-sky year"
