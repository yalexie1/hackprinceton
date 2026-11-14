"""SOL-01 to SOL-07: worked examples of specs/physics/01-solar-pv.md and the section 7 test plan.

pvlib is the reference only; the implementation under test does not import it.
"""
import numpy as np
import pandas as pd
import pytest

from backend.analysis.physics.climate.solar_position import (
    declination_spencer,
    equation_of_time_spencer,
    hour_angle,
    interval_bounds,
    interval_midpoints,
    pressure_from_elevation,
    solar_position,
    solar_position_simple,
    sun_vector,
    zenith_azimuth_from_angles,
)

pvlib = pytest.importorskip("pvlib")

# Golden lots (specs/examples/*/property_bundle.json, climate): house LA, office LA, office Houston
GOLDEN_LOTS = [
    (34.0934917, -118.3171, "Etc/GMT+8"),
    (34.0365339, -118.4431182, "Etc/GMT+8"),
    (29.7452, -95.4567, "Etc/GMT+6"),
]

# Running example, section 0.4
LAT, LON, TZ = 34.05, -118.25, -8
NOON_0621 = pd.Timestamp("2026-06-21 12:00:00", tz="Etc/GMT+8")


def _angle_diff(a, b):
    return np.abs((np.asarray(a) - np.asarray(b) + 180.0) % 360.0 - 180.0)


# ---------- SOL-01 ----------

def test_sol01_spa_table_a51():
    """SPA Table A5.1: 17 Oct 2003 12:30:30 UTC-7, published zenith 50.11162, azimuth 194.34024."""
    t = pd.Timestamp("2003-10-17 12:30:30", tz="Etc/GMT+7")
    sp = solar_position([t], 39.742476, -105.1786, 1830.14, pressure_pa=82000.0, temperature_c=11.0)
    assert sp["apparent_zenith_deg"].iloc[0] == pytest.approx(50.11162, abs=1e-4)
    assert sp["azimuth_deg"].iloc[0] == pytest.approx(194.34024, abs=1e-4)
    assert sp["equation_of_time_min"].iloc[0] == pytest.approx(14.641503, abs=1e-4)
    # refraction step alone: e0 = 39.87205, de = 0.016332
    assert sp["elevation_deg"].iloc[0] == pytest.approx(39.87205, abs=1e-5)
    de = sp["apparent_elevation_deg"].iloc[0] - sp["elevation_deg"].iloc[0]
    assert de == pytest.approx(0.016332, abs=1e-6)


@pytest.mark.parametrize("lat,lon,tz", GOLDEN_LOTS)
def test_sol01_year_against_pvlib(lat, lon, tz):
    """One hourly year at each golden lot (hour midpoints) against pvlib nrel_numpy, 1e-6 deg."""
    times = pd.date_range("2026-01-01 00:30", periods=8760, freq="h", tz=tz)
    elev, temp = 90.0, 18.0
    ours = solar_position(times, lat, lon, elev, temperature_c=temp)
    ref = pvlib.solarposition.get_solarposition(times, lat, lon, altitude=elev, temperature=temp,
                                                method="nrel_numpy")
    assert np.max(np.abs(ours["apparent_zenith_deg"] - ref["apparent_zenith"])) < 1e-6
    assert np.max(np.abs(ours["zenith_deg"] - ref["zenith"])) < 1e-6
    assert np.max(_angle_diff(ours["azimuth_deg"], ref["azimuth"])) < 1e-6
    assert np.max(np.abs(ours["equation_of_time_min"] - ref["equation_of_time"])) < 1e-6


def test_sol01_pressure_from_elevation_matches_pvlib():
    for h in (0.0, 90.0, 1830.14):
        assert pressure_from_elevation(h) == pytest.approx(pvlib.atmosphere.alt2pres(h), rel=1e-12)


def test_sol01_rejects_naive_times():
    with pytest.raises(ValueError):
        solar_position(pd.DatetimeIndex(["2026-06-21 12:00"]), LAT, LON)


# ---------- SOL-02 to SOL-05 ----------

def test_sol02_equation_of_time():
    assert equation_of_time_spencer(172) == pytest.approx(-1.3437, abs=1e-4)
    assert equation_of_time_spencer(172) == pytest.approx(
        float(pvlib.solarposition.equation_of_time_spencer71(172)), abs=1e-3)


def test_sol03_declination():
    assert declination_spencer(172) == pytest.approx(23.4520, abs=1e-4)
    assert declination_spencer(172) == pytest.approx(
        np.degrees(float(pvlib.solarposition.declination_spencer71(172))), abs=1e-4)


def test_sol04_hour_angle():
    E = equation_of_time_spencer(172)
    omega = hour_angle([NOON_0621], LON, E)[0]
    assert omega == pytest.approx(1.4141, abs=1e-4)
    # the spec's clock-time form: tst = 60 hr + mn + sc/60 + E + 4 lon - 60 tz
    tst = 720 + E + 4 * LON - 60 * TZ
    assert omega == pytest.approx(tst / 4 - 180, abs=1e-9)
    ref = pvlib.solarposition.hour_angle(pd.DatetimeIndex([NOON_0621]), LON, E)
    assert omega == pytest.approx(float(np.asarray(ref)[0]), abs=1e-9)


def test_sol05_zenith_azimuth():
    # the entry chains SOL-02..04 at full precision (delta 23.4520, omega 1.4141 when rounded)
    delta = float(declination_spencer(172))
    omega = float(hour_angle([NOON_0621], LON, equation_of_time_spencer(172))[0])
    z, a = zenith_azimuth_from_angles(LAT, delta, omega)
    assert float(z) == pytest.approx(10.6698, abs=1e-4)
    assert float(a) == pytest.approx(187.0234, abs=1e-4)
    zr = np.degrees(pvlib.solarposition.solar_zenith_analytical(
        np.radians(LAT), np.radians(omega), np.radians(delta)))
    ar = np.degrees(pvlib.solarposition.solar_azimuth_analytical(
        np.radians(LAT), np.radians(omega), np.radians(delta), np.radians(zr)))
    assert float(z) == pytest.approx(float(zr), abs=1e-9)
    assert float(a) == pytest.approx(float(ar), abs=1e-9)
    # the same through the timestamp helper
    z2, a2 = solar_position_simple([NOON_0621], LAT, LON, TZ)
    assert float(z2[0]) == pytest.approx(float(z), abs=1e-12)
    assert float(a2[0]) == pytest.approx(float(a), abs=1e-12)


def test_sol05_overhead_azimuth_is_180():
    z, a = zenith_azimuth_from_angles(23.4520, 23.4520, 0.0)
    assert float(z) == pytest.approx(0.0, abs=1e-6) and float(a) == 180.0


def test_sol05_against_sol01_over_a_year():
    """Simple algorithm within 1 degree of SPA for zenith below 85 (measured 0.57 and 0.78)."""
    times = pd.date_range("2026-01-01 00:30", periods=8760, freq="h", tz="Etc/GMT+8")
    spa = solar_position(times, LAT, LON, 90.0)
    z, a = solar_position_simple(times, LAT, LON, TZ)
    up = spa["zenith_deg"].to_numpy() < 85
    dz = np.abs(z[up] - spa["zenith_deg"].to_numpy()[up])
    da = _angle_diff(a[up], spa["azimuth_deg"].to_numpy()[up])
    assert dz.max() < 1.0 and da.max() < 1.0
    assert dz.max() == pytest.approx(0.57, abs=0.05)


# ---------- SOL-06 ----------

def test_sol06_sun_vector_worked_example():
    s = np.array(sun_vector(30.0, 150.0))
    assert s == pytest.approx([0.250000, -0.433013, 0.866025], abs=1e-6)
    assert np.linalg.norm(s) == pytest.approx(1.0, abs=1e-12)
    n = np.array([0.0, -np.sin(np.radians(20)), np.cos(np.radians(20))])   # ROOF-01, beta 20, gamma 180
    assert n @ s == pytest.approx(0.961897, abs=1e-6)


def test_sol06_dot_product_equals_pvlib_aoi():
    rng = np.random.default_rng(1)
    tilt, saz = rng.uniform(0, 180, 1000), rng.uniform(0, 360, 1000)
    zen, az = rng.uniform(0, 90, 1000), rng.uniform(0, 360, 1000)
    s = np.vstack(sun_vector(zen, az))
    n = np.vstack(sun_vector(tilt, saz))    # a plane normal has the same form as a direction
    cos_ref = np.cos(np.radians(pvlib.irradiance.aoi(tilt, saz, zen, az)))
    assert np.max(np.abs((n * s).sum(axis=0) - cos_ref)) < 1e-9


# ---------- SOL-07 ----------

def test_sol07_hour_ending_row_evaluated_at_half_past():
    stamps = pd.DatetimeIndex([pd.Timestamp("2024-06-21 15:00", tz="Etc/GMT+8")])
    mid = interval_midpoints(stamps, LAT, LON)
    assert mid[0] == pd.Timestamp("2024-06-21 14:30", tz="Etc/GMT+8")


def test_sol07_conventions():
    stamps = pd.DatetimeIndex([pd.Timestamp("2024-06-21 15:00", tz="Etc/GMT+8")])
    expect = {"hour_end": "14:30", "hour_start": "15:30", "hour_centre": "15:00"}
    for conv, hhmm in expect.items():
        mid = interval_midpoints(stamps, LAT, LON, convention=conv)
        assert mid[0] == pd.Timestamp(f"2024-06-21 {hhmm}", tz="Etc/GMT+8"), conv
    with pytest.raises(ValueError):
        interval_bounds(stamps, "instant")


def test_sol07_sunrise_and_sunset_hours_use_the_sun_up_part():
    stamps = pd.date_range("2024-06-21 01:00", periods=24, freq="h", tz="Etc/GMT+8")
    mid = interval_midpoints(stamps, LAT, LON)
    start, end = interval_bounds(stamps)
    zs = solar_position(start, LAT, LON)["apparent_zenith_deg"].to_numpy()
    ze = solar_position(end, LAT, LON)["apparent_zenith_deg"].to_numpy()
    edge = np.flatnonzero((zs < 90) != (ze < 90))
    assert len(edge) == 2                       # one sunrise hour, one sunset hour
    rise, sett = edge
    assert zs[rise] >= 90 > ze[rise] and zs[sett] < 90 <= ze[sett]
    # sunrise: the instant is the middle of [crossing, end]; recover the crossing and check it
    crossing_rise = mid[rise] - (end[rise] - mid[rise])
    crossing_set = mid[sett] + (mid[sett] - start[sett])
    for c in (crossing_rise, crossing_set):
        z = solar_position([c], LAT, LON)["apparent_zenith_deg"].iloc[0]
        assert z == pytest.approx(90.0, abs=0.01)
        assert start[rise] <= crossing_rise <= end[rise]
    sun_at_mid = solar_position(mid[[rise, sett]], LAT, LON)["apparent_zenith_deg"].to_numpy()
    assert np.all(sun_at_mid < 90)
    others = np.setdiff1d(np.arange(24), edge)
    assert np.all(mid[others] == (start + pd.Timedelta(minutes=30))[others])
