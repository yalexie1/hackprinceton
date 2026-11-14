"""A5 comfort entries CMF-01 to CMF-08 against physics 03 and the published table rows.

`pythermalcomfort` is not installed in the lane environment, so T-CMF-2 is skipped and the
reference is the 12 "ISO 7730 2005" rows of `ts_pmv_ppd.json` and the 26 seated "ASHRAE 55 2017"
rows of `ts_solar_gain.json` (FedericoTartarini/validation-data-comfort-models, MIT), copied below
with the files' own tolerances.
"""
import math
import socket

import numpy as np
import pytest

from backend.analysis.physics.daylight import constants as C
from backend.analysis.physics.daylight.comfort import (
    config_factor_b3, glass_inside_surface_temperature, mean_radiant_temperature, omega_corner,
    operative_temperature, pd_cool_wall, plane_factor_to_window, pmv_ppd, ppd_from_pmv,
    projected_area_factor, radiant_asymmetry_window, sky_vault_fraction, solar_gain_delta_mrt,
    window_angle_factor, window_solid_angle)

R0 = (-1.0, 1.0, 0.9, 2.4)
BODY = (0.0, 1.0, 0.6)

# tdb, tr, vr, rh, met, clo, pmv, ppd  (ISO 7730 2005 rows; tolerance 0.1 PMV, 1 PPD)
ISO_ROWS = [
    (22, 22, 0.1, 60, 1.2, 0.5, -0.8, 16.9),
    (27, 27, 0.1, 60, 1.2, 0.5, 0.8, 17.3),
    (27, 27, 0.3, 60, 1.2, 0.5, 0.4, 8.9),
    (23.5, 25.5, 0.1, 60, 1.2, 0.5, -0.0, 5.0),
    (23.5, 25.5, 0.3, 60, 1.2, 0.5, -0.6, 11.4),
    (19, 19, 0.1, 40, 1.2, 1.0, -0.6, 12.5),
    (23.5, 23.5, 0.3, 40, 1.2, 1.0, 0.1, 5.3),
    (23.0, 21.0, 0.1, 40, 1.2, 1.0, 0.1, 5.1),
    (23.0, 21.0, 0.3, 40, 1.2, 1.0, -0.2, 5.6),
    (22.0, 22.0, 0.1, 60, 1.6, 0.5, 0.1, 5.0),
    (27.0, 27.0, 0.1, 60, 1.6, 0.5, 1.2, 33.9),
    (27.0, 27.0, 0.3, 60, 1.6, 0.5, 0.9, 24.1),
]

# altitude, sharp, I_dir, T_sol, f_svv, f_bes, asw, erf, dmrt  (ASHRAE 55 2017, seated; 0.1, 0.1)
SOLAR_ROWS = [
    (45, 0, 700, 0.8, 0.2, 0.5, 0.7, 64.9, 15.5),
    (0, 120, 800, 0.5, 0.5, 0.5, 0.7, 43.3, 10.4),
    (60, 120, 800, 0.5, 0.5, 0.5, 0.7, 63.2, 15.1),
    (90, 120, 800, 0.5, 0.5, 0.5, 0.7, 65.3, 15.6),
    (30, 0, 800, 0.5, 0.5, 0.5, 0.7, 63.1, 15.1),
    (30, 30, 800, 0.5, 0.5, 0.5, 0.7, 62.4, 14.9),
    (30, 60, 800, 0.5, 0.5, 0.5, 0.7, 60.5, 14.5),
    (30, 90, 800, 0.5, 0.5, 0.5, 0.7, 57.2, 13.7),
    (30, 150, 800, 0.5, 0.5, 0.5, 0.7, 51.7, 12.4),
    (30, 180, 800, 0.5, 0.5, 0.5, 0.7, 49.0, 11.7),
    (30, 120, 400, 0.5, 0.5, 0.5, 0.7, 27.4, 6.6),
    (30, 120, 600, 0.5, 0.5, 0.5, 0.7, 41.1, 9.8),
    (30, 120, 1000, 0.5, 0.5, 0.5, 0.7, 68.5, 16.4),
    (30, 120, 800, 0.1, 0.5, 0.5, 0.7, 11.0, 2.6),
    (30, 120, 800, 0.3, 0.5, 0.5, 0.7, 32.9, 7.9),
    (30, 120, 800, 0.7, 0.5, 0.5, 0.7, 76.7, 18.4),
    (30, 120, 800, 0.5, 0.1, 0.5, 0.7, 29.3, 7.0),
    (30, 120, 800, 0.5, 0.3, 0.5, 0.7, 42.1, 10.1),
    (30, 120, 800, 0.5, 0.7, 0.5, 0.7, 67.5, 16.2),
    (30, 120, 800, 0.5, 0.5, 0.1, 0.7, 36.4, 8.7),
    (30, 120, 800, 0.5, 0.5, 0.3, 0.7, 45.6, 10.9),
    (30, 120, 800, 0.5, 0.5, 0.7, 0.7, 64.0, 15.3),
    (30, 120, 800, 0.5, 0.5, 0.5, 0.3, 23.5, 5.6),
    (30, 120, 800, 0.5, 0.5, 0.5, 0.5, 39.1, 9.4),
    (30, 120, 800, 0.5, 0.5, 0.5, 0.9, 70.4, 16.9),
    (30, 120, 800, 0.5, 0.5, 0.5, 0.7, 54.8, 13.1),
]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A5 tests must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


# ---- T-CMF-1 (CMF-01, CMF-02)
@pytest.mark.parametrize("ta, tr, vr, rh, met, clo, pmv, ppd", ISO_ROWS)
def test_iso_7730_table_rows(ta, tr, vr, rh, met, clo, pmv, ppd):
    r = pmv_ppd(ta, tr, vr, rh, met, clo)
    assert abs(r["pmv"] - pmv) <= 0.1
    assert abs(r["ppd"] - ppd) <= 1.0


def test_pmv_vectorised_matches_scalar():
    rows = np.array(ISO_ROWS)
    r = pmv_ppd(rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3], rows[:, 4], rows[:, 5])
    for i, row in enumerate(ISO_ROWS):
        assert r["pmv"][i] == pytest.approx(pmv_ppd(*row[:6])["pmv"], abs=1e-6)


def test_pmv_worked_example():
    r = pmv_ppd(21, 20.360, 0.1, 40, 1.2, 1.0)
    assert r["t_cl"] == pytest.approx(26.081, abs=2e-3)
    assert r["pmv"] == pytest.approx(-0.240, abs=1e-3)
    assert r["ppd"] == pytest.approx(6.20, abs=0.01)
    assert pmv_ppd(21, 21, 0.1, 40, 1.2, 1.0)["pmv"] == pytest.approx(-0.177, abs=2e-3)
    assert pmv_ppd(24, 24, 0.1, 50, 1.2, 0.5)["pmv"] == pytest.approx(-0.215, abs=1e-3)
    assert pmv_ppd(24, 24 + 9.02, 0.1, 50, 1.2, 0.5)["pmv"] == pytest.approx(1.079, abs=1e-3)


def test_ppd_anchors():
    assert [round(float(ppd_from_pmv(p)), 2) for p in (0, 0.5, 1, 2)] == [5.0, 10.23, 26.12, 76.76]
    assert float(ppd_from_pmv(-1)) == float(ppd_from_pmv(1))


# ---- T-CMF-2 (needs the reference implementation, a test-only dependency)
def test_against_pythermalcomfort():
    ptc = pytest.importorskip("pythermalcomfort.models")
    rng = np.random.default_rng(7)
    for _ in range(200):
        ta, tr = rng.uniform(10, 30), rng.uniform(10, 40)
        vr, rh = rng.uniform(0, 1), rng.uniform(10, 90)
        met, clo = rng.uniform(0.8, 4), rng.uniform(0, 2)
        ref = ptc.pmv_ppd_iso(tdb=ta, tr=tr, vr=vr, rh=rh, met=met, clo=clo, model="7730-2005",
                              limit_inputs=False, round_output=False)
        own = pmv_ppd(ta, tr, vr, rh, met, clo)
        assert abs(own["pmv"] - float(ref.pmv)) < 0.01
        assert abs(own["ppd"] - float(ref.ppd)) < 0.1


# ---- T-CMF-3 (CMF-03)
def test_operative_temperature():
    assert float(operative_temperature(21, 20.360, 0.1)) == pytest.approx(20.68, abs=0.01)
    assert float(operative_temperature(21, 20.360, 0.1, "iso")) == pytest.approx(20.68, abs=0.01)
    assert float(operative_temperature(24, 30, 0.3)) == pytest.approx(26.40, abs=0.01)
    assert float(operative_temperature(24, 30, 0.3, "iso")) == pytest.approx(26.20, abs=0.01)


# ---- T-CMF-4 (CMF-04)
def test_glass_temperature():
    t = float(glass_inside_surface_temperature(21, -5, 2.8, 8.0))
    assert t == pytest.approx(11.90, abs=0.01)
    divider = -5 + (21 - -5) * (1 / 2.8 - 1 / 8.0) / (1 / 2.8)
    assert t == pytest.approx(divider, abs=1e-9)
    # the implementation default is ENV-06's 7.69 W/m2K, not the example's 8.0
    assert C.H_I_W_M2K == 7.69
    assert float(glass_inside_surface_temperature(21, -5, 2.8)) == pytest.approx(21 - 72.8 / 7.69, abs=1e-9)


# ---- T-CMF-5 (CMF-05)
def test_solid_angle_and_mrt():
    om = window_solid_angle(BODY, R0)
    n = 1500
    u = -1 + (np.arange(n) + 0.5) * 2 / n
    z = 0.9 + (np.arange(n) + 0.5) * 1.5 / n
    U, Z = np.meshgrid(u, z)
    D = np.sqrt(U ** 2 + 1.0 + (Z - 0.6) ** 2)
    assert om == pytest.approx(np.sum(1.0 / D ** 3) * (2 / n) * (1.5 / n), abs=1e-6)
    assert om == pytest.approx(0.923483, abs=1e-6)
    fw = window_angle_factor(BODY, R0)
    assert fw == pytest.approx(0.07349, abs=1e-5)
    assert float(mean_radiant_temperature([fw], [11.90], 21)) == pytest.approx(20.360, abs=1e-3)
    f2 = window_angle_factor((0.0, 2.0, 0.6), R0)
    assert f2 == pytest.approx(0.03779, abs=1e-5)
    assert float(mean_radiant_temperature([f2], [11.90], 21)) == pytest.approx(20.671, abs=1e-3)


def test_closure_over_a_box():
    rng = np.random.default_rng(3)
    W, Dp, H = 4.0, 6.0, 2.8
    for _ in range(5):
        x, y, z = rng.uniform(0.2, W - 0.2), rng.uniform(0.2, Dp - 0.2), rng.uniform(0.2, H - 0.2)
        faces = [
            ((x - W, x, z - H, z), y),          # wall y = 0 seen from distance y: rect in (x, z)
            ((x - W, x, z - H, z), Dp - y),
            ((y - Dp, y, z - H, z), x),
            ((y - Dp, y, z - H, z), W - x),
            ((x - W, x, y - Dp, y), z),
            ((x - W, x, y - Dp, y), H - z),
        ]
        tot = sum(window_solid_angle((0.0, c, 0.0), r) for r, c in faces) / (4 * math.pi)
        assert tot == pytest.approx(1.0, abs=1e-6)
    assert omega_corner(0, 1, 1) == 0.0


# ---- T-CMF-6 (CMF-06)
def test_radiant_asymmetry():
    F = plane_factor_to_window(BODY, R0)
    n = 1500
    u = -1 + (np.arange(n) + 0.5) * 2 / n
    z = 0.9 + (np.arange(n) + 0.5) * 1.5 / n
    U, Z = np.meshgrid(u, z)
    D = np.sqrt(U ** 2 + 1.0 + (Z - 0.6) ** 2)
    quad = np.sum(1.0 / D ** 4) * (2 / n) * (1.5 / n) / math.pi
    assert F == pytest.approx(quad, abs=1e-4)
    assert F == pytest.approx(0.212544, abs=1e-6)
    dt = float(radiant_asymmetry_window([F], [11.90], 21.0))
    assert dt == pytest.approx(1.86, abs=0.05)
    assert float(pd_cool_wall(dt)) == pytest.approx(0.3, abs=0.05)
    # severe case: single glazing, -10 C, glass wall 4.0 x 2.8 m, element 0.6 m away
    tg = float(glass_inside_surface_temperature(21, -10, 5.8, 8.0))
    assert tg == pytest.approx(-1.47, abs=0.01)
    Fs = plane_factor_to_window((0.0, 0.6, 0.6), (-2.0, 2.0, 0.0, 2.8))
    assert Fs == pytest.approx(0.8171, abs=1e-4)
    assert float(radiant_asymmetry_window([Fs], [tg], 21.0)) == pytest.approx(17.9, abs=0.05)
    assert float(pd_cool_wall(10.0)) == pytest.approx(4.1, abs=0.1)
    assert config_factor_b3(0, 1, 1) == 0.0


# ---- T-CMF-7 (CMF-07, ASHRAE 55 rows with I_diff = 0.2 I_dir and R_floor = 0.6)
@pytest.mark.parametrize("alt, sharp, idir, tsol, fsvv, fbes, asw, erf, dmrt", SOLAR_ROWS)
def test_ashrae_55_solar_rows(alt, sharp, idir, tsol, fsvv, fbes, asw, erf, dmrt):
    r = solar_gain_delta_mrt(alt, sharp, idir, 0.2 * idir, tsol, fsvv, fbes, asw, 0.6)
    assert abs(float(r["erf_w_m2"]) - erf) <= 0.1
    assert abs(float(r["delta_mrt_k"]) - dmrt) <= 0.1


# ---- T-CMF-8 (CMF-07 worked example and the Arens skylight example)
def test_solar_gain_worked_example():
    fs = sky_vault_fraction(BODY, R0)
    assert fs == pytest.approx(0.06145, abs=1e-5)
    assert float(projected_area_factor(25, 70)) == pytest.approx(0.2756, abs=1e-4)
    r = solar_gain_delta_mrt(25, 70, 800, 120, 0.6, fs, 0.5, 0.7, 0.6)
    assert float(r["erf_w_m2"]) == pytest.approx(37.65, rel=1e-3)
    assert float(r["delta_mrt_k"]) == pytest.approx(9.02, rel=1e-3)
    r2 = solar_gain_delta_mrt(25, 70, 800, 160, 0.6, 0.06145, 0.5, 0.7, 0.6)
    assert float(r2["erf_w_m2"]) == pytest.approx(38.254, abs=2e-3)
    assert float(r2["delta_mrt_k"]) == pytest.approx(9.161, abs=1e-3)
    sky = solar_gain_delta_mrt(87, 0, 925, 0.2 * 925, 0.2, 0.0122, 0.9, 0.7, 0.5)
    assert float(sky["erf_w_m2"]) == pytest.approx(16.5, rel=0.02)
    assert float(sky["delta_mrt_k"]) == pytest.approx(3.9, rel=0.02)
    with pytest.raises(NotImplementedError):
        solar_gain_delta_mrt(25, 70, 800, 120, 0.6, fs, 0.5, 0.7, 0.6, posture="standing")


def test_cmf08_three_toy_hours():
    """CMF-08 worked example: winter night, summer hour without sun, summer hour with sun."""
    p1 = pmv_ppd(21, 20.360, 0.1, 40, 1.2, 1.0)["ppd"]
    p2 = pmv_ppd(24, 24, 0.1, 50, 1.2, 0.5)["ppd"]
    p3 = pmv_ppd(24, 24 + 9.02, 0.1, 50, 1.2, 0.5)["ppd"]
    assert (p1, p2, p3) == pytest.approx((6.20, 5.96, 29.55), abs=0.05)
    assert np.mean([p1, p2, p3]) == pytest.approx(13.90, abs=0.02)
