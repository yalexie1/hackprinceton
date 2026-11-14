"""IRR-01 to IRR-10: worked examples of specs/physics/01-solar-pv.md and the section 7 test plan.

Running example (section 0.4): theta_z = 30, A = 150, beta = 20, gamma = 180, GHI = 800,
n = 172, albedo 0.2. pvlib is the reference only.
"""
from pathlib import Path

import numpy as np
import pytest

from backend.analysis.physics.climate.irradiance import (
    PEREZ_COEFFICIENTS,
    decompose_ghi_erbs,
    extraterrestrial_normal_irradiance,
    incidence_angle,
    perez_bin,
    plane_of_array_irradiance,
    poa_beam,
    poa_ground_reflected,
    relative_air_mass,
    sky_diffuse_haydavies,
    sky_diffuse_isotropic,
    sky_diffuse_perez,
)

pvlib = pytest.importorskip("pvlib")
irr = pvlib.irradiance

ZEN, AZ, TILT, SAZ, GHI, DOY, RHO = 30.0, 150.0, 20.0, 180.0, 800.0, 172, 0.2
REL = 1e-6


@pytest.fixture(scope="module")
def running():
    e0n = float(extraterrestrial_normal_irradiance(DOY))
    dni, dhi, kt = (float(x) for x in decompose_ghi_erbs(GHI, ZEN, DOY))
    am = float(relative_air_mass(ZEN))
    aoi = float(incidence_angle(TILT, SAZ, ZEN, AZ))
    return dict(e0n=e0n, dni=dni, dhi=dhi, kt=kt, am=am, aoi=aoi)


def test_irr01_extraterrestrial(running):
    assert running["e0n"] == pytest.approx(1321.62, abs=0.005)
    assert float(extraterrestrial_normal_irradiance(3)) == pytest.approx(1414.02, abs=0.005)
    for n in (3, 172):
        assert float(extraterrestrial_normal_irradiance(n)) == pytest.approx(
            float(irr.get_extra_radiation(n, method="spencer")), rel=REL)


def test_irr02_erbs(running):
    assert running["kt"] == pytest.approx(0.69896, abs=5e-6)
    assert running["dhi"] == pytest.approx(196.48, abs=0.005)
    assert running["dni"] == pytest.approx(696.885, abs=0.0005)
    ref = irr.erbs(GHI, ZEN, DOY)
    assert running["dni"] == pytest.approx(float(ref["dni"]), rel=REL)
    assert running["dhi"] == pytest.approx(float(ref["dhi"]), rel=REL)
    assert running["kt"] == pytest.approx(float(ref["kt"]), rel=REL)


def test_irr02_erbs_ranges_and_guards_against_pvlib():
    rng = np.random.default_rng(2)
    ghi = rng.uniform(-5, 1100, 2000)
    zen = rng.uniform(0, 95, 2000)
    doy = rng.integers(1, 366, 2000)
    dni, dhi, kt = decompose_ghi_erbs(ghi, zen, doy)
    ref = irr.erbs(ghi, zen, doy)
    np.testing.assert_allclose(dni, ref["dni"], rtol=REL, atol=1e-9)
    np.testing.assert_allclose(dhi, ref["dhi"], rtol=REL, atol=1e-9)
    np.testing.assert_allclose(kt, ref["kt"], rtol=REL, atol=1e-12)


def test_irr03_air_mass(running):
    assert running["am"] == pytest.approx(1.153608, abs=1e-6)
    assert float(relative_air_mass(80.0)) == pytest.approx(5.580339, abs=1e-6)
    for z in (30.0, 80.0, 89.5):
        assert float(relative_air_mass(z)) == pytest.approx(
            float(pvlib.atmosphere.get_relative_airmass(z, model="kasten1966")), rel=REL)
    assert np.isnan(relative_air_mass(95.0))


def test_irr04_incidence(running):
    assert running["aoi"] == pytest.approx(15.8675, abs=1e-4)
    assert np.cos(np.radians(running["aoi"])) == pytest.approx(0.961897, abs=1e-6)
    assert running["aoi"] == pytest.approx(float(irr.aoi(TILT, SAZ, ZEN, AZ)), rel=REL)


def test_irr04_spa_case():
    """SPA Table A5.1: slope 30, surface azimuth 170, sun (50.111622, 194.340241): 25.18700."""
    assert float(incidence_angle(30.0, 170.0, 50.111622, 194.340241)) == pytest.approx(25.18700, abs=1e-4)


def test_irr05_beam(running):
    eb = float(poa_beam(running["dni"], running["aoi"]))
    assert eb == pytest.approx(670.33, abs=0.005)
    assert eb == pytest.approx(float(irr.beam_component(TILT, SAZ, ZEN, AZ, running["dni"])), rel=REL)
    assert float(poa_beam(500.0, 120.0)) == 0.0


def test_irr06_isotropic(running):
    e = float(sky_diffuse_isotropic(running["dhi"], TILT))
    assert e == pytest.approx(190.56, abs=0.005)
    assert e == pytest.approx(float(irr.isotropic(TILT, running["dhi"])), rel=REL)


def test_irr07_haydavies(running):
    e = float(sky_diffuse_haydavies(running["dhi"], running["dni"], running["e0n"], TILT, running["aoi"], ZEN))
    assert e == pytest.approx(205.15, abs=0.005)
    ref = irr.haydavies(TILT, SAZ, running["dhi"], running["dni"], running["e0n"], ZEN, AZ)
    assert e == pytest.approx(float(ref), rel=REL)


def test_irr08_perez_worked_example(running):
    d = sky_diffuse_perez(running["dhi"], running["dni"], running["e0n"], TILT, running["aoi"], ZEN, running["am"])
    assert d["isotropic"] == pytest.approx(56.380, abs=0.0005)
    assert d["circumsolar"] == pytest.approx(153.663, abs=0.0005)
    assert d["horizon"] == pytest.approx(11.839, abs=0.0005)
    assert d["sky_diffuse"] == pytest.approx(221.881, abs=0.0005)
    ref = irr.perez(TILT, SAZ, running["dhi"], running["dni"], running["e0n"], ZEN, AZ, running["am"],
                    return_components=True)
    for ours, theirs in (("sky_diffuse", "poa_sky_diffuse"), ("isotropic", "poa_isotropic"),
                         ("circumsolar", "poa_circumsolar"), ("horizon", "poa_horizon")):
        assert float(d[ours]) == pytest.approx(float(ref[theirs]), rel=REL)


def test_irr08_intermediates(running):
    z = np.radians(ZEN)
    eps = ((running["dhi"] + running["dni"]) / running["dhi"] + 1.041 * z**3) / (1 + 1.041 * z**3)
    assert eps == pytest.approx(4.0857, abs=1e-4)
    assert int(perez_bin(eps)) == 5                                     # bin 6
    assert running["dhi"] * running["am"] / running["e0n"] == pytest.approx(0.17150, abs=1e-5)


def test_irr08_coefficient_table_is_pvlibs():
    f1, f2 = irr._get_perez_coefficients("allsitescomposite1990")
    assert np.array_equal(PEREZ_COEFFICIENTS[:, :3], np.asarray(f1))
    assert np.array_equal(PEREZ_COEFFICIENTS[:, 3:], np.asarray(f2))


def test_irr08_bin_edges():
    edges = [1.0, 1.065, 1.230, 1.500, 1.950, 2.800, 4.500, 6.200]
    for k, e in enumerate(edges):
        assert int(perez_bin(e)) == k                                   # 'from' is inclusive
        if k:
            assert int(perez_bin(np.nextafter(e, 0))) == k - 1         # 'to' is exclusive
    assert int(perez_bin(50.0)) == 7


def test_irr08_zero_outside_validity(running):
    for dhi, zen in ((0.0, 30.0), (100.0, 90.0), (100.0, 95.0)):
        d = sky_diffuse_perez(dhi, 300.0, running["e0n"], TILT, 20.0, zen, relative_air_mass(zen))
        assert all(float(v) == 0.0 for v in d.values())


def test_irr09_ground(running):
    e = float(poa_ground_reflected(GHI, RHO, TILT))
    assert e == pytest.approx(4.825, abs=0.0005)
    assert e == pytest.approx(float(irr.get_ground_diffuse(TILT, GHI, albedo=RHO)), rel=REL)


def test_irr10_total(running):
    p = plane_of_array_irradiance(GHI, running["dni"], running["dhi"], DOY, ZEN, AZ, TILT, SAZ, RHO)
    assert float(p["poa_global"]) == pytest.approx(897.04, abs=0.005)
    assert float(p["poa_beam"]) == pytest.approx(670.332, abs=0.0005)
    ref = irr.get_total_irradiance(TILT, SAZ, ZEN, AZ, running["dni"], GHI, running["dhi"],
                                   dni_extra=running["e0n"], airmass=running["am"], albedo=RHO,
                                   model="perez")
    for ours, theirs in (("poa_global", "poa_global"), ("poa_beam", "poa_direct"),
                         ("poa_sky_diffuse", "poa_sky_diffuse"), ("poa_ground", "poa_ground_diffuse")):
        assert float(p[ours]) == pytest.approx(float(ref[theirs]), rel=REL)


def test_irr10_night_is_zero():
    p = plane_of_array_irradiance(5.0, 10.0, 5.0, DOY, 92.0, 280.0, TILT, SAZ)
    assert all(float(v) == 0.0 for k, v in p.items() if k != "incidence_deg")


# ---------- one year of real weather (the weather sample), section 7 IRR-08 row ----------

WEATHER = Path(__file__).resolve().parents[5] / "specs" / "examples" / "weather"
SITES = {
    "la": (34.0934917, -118.3171, "America/Los_Angeles", "typical_year_hourly.csv"),
    "houston": (29.7452, -95.4567, "America/Chicago", "typical_year_hourly_houston.csv"),
}


@pytest.fixture(scope="module", params=sorted(SITES))
def year(request):
    from backend.analysis.physics.climate.hourly import load_climate
    from backend.schema import ClimateSite
    lat, lon, tz, name = SITES[request.param]
    site = ClimateSite(lat=lat, lon=lon, timezone=tz, weather_path=str(WEATHER / name),
                       weather_source="Open-Meteo archive 2024", weather_time_convention="hour_end")
    return load_climate(site)


@pytest.mark.parametrize("tilt", [20.0, 40.0])
@pytest.mark.parametrize("saz", [90.0, 180.0, 270.0])
def test_irr08_year_against_pvlib(year, tilt, saz):
    h = year
    d = sky_diffuse_perez(h.dhi_w_m2, h.dni_w_m2, h.e0n_w_m2, tilt,
                          incidence_angle(tilt, saz, h.apparent_zenith_deg, h.sun_azimuth_deg),
                          h.apparent_zenith_deg, h.air_mass)
    ref = irr.perez(tilt, saz, h.dhi_w_m2, h.dni_w_m2, h.e0n_w_m2, h.apparent_zenith_deg,
                    h.sun_azimuth_deg, h.air_mass, return_components=True)
    valid = (h.dhi_w_m2 > 0) & (h.apparent_zenith_deg < 90)
    assert valid.sum() > 4000
    for ours, theirs in (("sky_diffuse", "poa_sky_diffuse"), ("isotropic", "poa_isotropic"),
                         ("circumsolar", "poa_circumsolar"), ("horizon", "poa_horizon")):
        diff = np.abs(np.asarray(d[ours])[valid] - np.asarray(ref[theirs])[valid])
        assert diff.max() < 1e-6, ours
    assert np.all(np.asarray(d["sky_diffuse"])[~valid] == 0.0)


@pytest.mark.parametrize("tilt,saz", [(20.0, 180.0), (40.0, 270.0), (90.0, 90.0)])
def test_irr10_year_against_pvlib(year, tilt, saz):
    from backend.analysis.physics.climate.hourly import plane_irradiance
    h = year
    p = plane_irradiance(h, tilt, saz)
    ref = irr.get_total_irradiance(tilt, saz, h.apparent_zenith_deg, h.sun_azimuth_deg, h.dni_w_m2,
                                   h.ghi_w_m2, h.dhi_w_m2, dni_extra=h.e0n_w_m2, airmass=h.air_mass,
                                   albedo=0.2, model="perez")
    ref_global = np.nan_to_num(np.asarray(ref["poa_global"]))
    assert np.max(np.abs(p["poa_global"] - ref_global)) < 1e-6
