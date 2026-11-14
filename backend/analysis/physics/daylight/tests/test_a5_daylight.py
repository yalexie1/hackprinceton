"""A5 daylight entries DAY-02 to DAY-10 against the worked examples of physics 03 (test plan 5)."""
import math
import socket

import numpy as np
import pytest

from backend.analysis.physics.daylight import constants as C
from backend.analysis.physics.daylight.daylight import (
    IRCWindow, average_daylight_factor, cie_overcast_luminance, config_factor_horizontal_to_window,
    daylight_autonomy, externally_reflected_component, indoor_illuminance_hourly,
    internally_reflected_component, perez_luminous_efficacy, sky_component, sky_window_factor,
    sky_window_factor_obstructed, target_daylight_factor)

R0 = (-1.0, 1.0, 0.9, 2.4)                 # window rectangle (u1, u2, z1, z2), section 0.6
TAU_EFF = 0.68 * 0.9 * 0.8                 # 0.4896
P, F = (0.0, 2.0, 0.85), (0.0, 5.0, 0.85)
REFL = dict(floor=0.2, ceiling=0.7, walls=0.5, glass=0.1)
R0_WIN = [IRCWindow(area_m2=3.0, mid_height_m=1.65, tau=0.68, wall_id="w", wall_length_m=4.0)]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A5 tests must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def rel(a, b):
    return abs(a - b) / abs(b)


# ---- T-DAY-1 (DAY-02)
def test_overcast_sky_integrals_by_quadrature():
    x, w = np.polynomial.legendre.leggauss(200)
    g = (x + 1) * math.pi / 4                         # altitude 0 .. pi/2
    wg = w * math.pi / 4
    lum = (1 + 2 * np.sin(g)) / 3                     # L / L_z
    e_h = 2 * math.pi * np.sum(wg * lum * np.sin(g) * np.cos(g))
    e_v = 2 * np.sum(wg * lum * np.cos(g) * np.cos(g))  # integral of cos(alpha) over -pi/2..pi/2 is 2
    assert abs(e_h - 7 * math.pi / 9) < 1e-6
    assert abs(e_v / e_h - (3 * math.pi + 8) / (14 * math.pi)) < 1e-6
    assert abs(C.F_S0 - 0.396177) < 1e-6
    assert cie_overcast_luminance(0.0, 10000) == pytest.approx(1364.2, abs=0.1)
    assert cie_overcast_luminance(math.radians(30), 10000) == pytest.approx(2728.4, abs=0.1)


# ---- T-DAY-2 (DAY-03)
def test_sky_component_r0():
    assert rel(sky_component(P, R0, 1.0), 0.040734) < 1e-4
    assert rel(sky_component(P, R0, TAU_EFF), 0.019944) < 1e-3
    assert rel(sky_component(F, R0, 1.0), 0.003246) < 1e-3
    assert rel(sky_component(F, R0, TAU_EFF), 0.001589) < 1e-3


def test_sky_component_midpoint_sum():
    """Second computation: 400 x 400 midpoint sum over the window of L sin(gamma) dOmega / E_h."""
    n = 400
    u = -1 + (np.arange(n) + 0.5) * 2 / n
    z = 0.9 + (np.arange(n) + 0.5) * 1.5 / n
    U, Z = np.meshgrid(u, z)
    d, dz = 2.0, Z - 0.85
    D = np.sqrt(U ** 2 + d ** 2 + dz ** 2)
    integrand = (1 + 2 * dz / D) / 3 * (dz / D) * (d / D) / D ** 2
    sc = 9 / (7 * math.pi) * integrand.sum() * (2 / n) * (1.5 / n)
    assert rel(sc, sky_component(P, R0, 1.0)) < 1e-4


# ---- T-DAY-3 (DAY-03 with a uniform sky against Howell B-4)
def test_uniform_sky_kernel_against_b4():
    # uniform sky of luminance L: E / (pi L) = configuration factor; numeric by the DAY-03 single
    # integral with the uniform kernel  integral (1/pi) sin(gamma) dOmega
    u_p, d_p, z_p = P
    x, w = np.polynomial.legendre.leggauss(200)
    phi1, phi2 = math.atan((-1 - u_p) / d_p), math.atan((1 - u_p) / d_p)
    phi = phi1 + (x + 1) * (phi2 - phi1) / 2
    wp = w * (phi2 - phi1) / 2
    r = d_p / np.cos(phi)
    s = lambda z: (z - z_p) / np.sqrt(r ** 2 + (z - z_p) ** 2)
    num = np.sum(wp * (s(2.4) ** 2 - s(0.9) ** 2) / 2) / math.pi
    assert abs(num - 0.052805) < 1e-5
    assert abs(config_factor_horizontal_to_window(P, -1, 1, 0.9, 2.4) - num) < 1e-5


# ---- T-DAY-4 (flux conservation)
def test_flux_conservation_over_a_large_plane():
    x, w = np.polynomial.legendre.leggauss(16)
    def pieces(edges):
        for a, b in zip(edges[:-1], edges[1:]):
            yield a + (x + 1) * (b - a) / 2, w * (b - a) / 2
    d_edges = [1e-4, 0.01, 0.1, 0.5, 1, 2, 5, 10, 30, 100, 400]
    u_half = [0, 0.5, 1.0, 1.5, 3, 10, 30, 100, 200]
    u_edges = sorted({-e for e in u_half} | set(u_half))
    total = 0.0
    for dd, wd in pieces(d_edges):
        for uu, wu in pieces(u_edges):
            for di, wdi in zip(dd, wd):
                for ui, wui in zip(uu, wu):
                    total += wdi * wui * sky_component((ui, di, 0.9), R0, 1.0, n=32)
    assert abs(total - 3.0 * C.F_S0) / (3.0 * C.F_S0) < 2e-3


# ---- T-DAY-5 (ordering; workplan A5 acceptance)
def test_sky_component_falls_with_distance_and_window_beats_deep_point():
    ds = [0.6, 1, 2, 3, 4, 5, 6]
    vals = [sky_component((0.0, d, 0.85), R0, TAU_EFF) for d in ds]
    assert all(a > b for a, b in zip(vals, vals[1:]))
    beside = sky_component((0.0, 0.6, 0.85), R0, TAU_EFF)
    deep = sky_component((0.0, 6.0, 0.85), R0, TAU_EFF)
    assert beside > 10 * deep


# ---- T-DAY-6 (DAY-04)
@pytest.mark.parametrize("theta, sc, erc", [(0, 0.019944, 0.0), (10, 0.018896, 0.000198),
                                            (20, 0.015059, 0.000783), (30, 0.007871, 0.001693),
                                            (40, 0.0, 0.002566)])
def test_obstruction_table(theta, sc, erc):
    assert sky_component(P, R0, TAU_EFF, theta) == pytest.approx(sc, rel=1e-3, abs=1e-9)
    # printed to six decimals, so the rounding (5e-7) is the tolerance
    assert externally_reflected_component(P, R0, TAU_EFF, theta, 0.2, 0.2) == pytest.approx(erc, abs=5e-7)


def test_obstruction_ray_grid_second_computation():
    """ERC + SC at 20 deg by a ray-by-ray grid with the per-ray blocking test (DAY-04)."""
    theta, n = 20.0, 600
    u = -1 + (np.arange(n) + 0.5) * 2 / n
    z = 0.9 + (np.arange(n) + 0.5) * 1.5 / n
    U, Z = np.meshgrid(u, z)
    d, dz = 2.0, Z - 0.85
    D = np.sqrt(U ** 2 + d ** 2 + dz ** 2)
    dA = (2 / n) * (1.5 / n)
    dom = d / D ** 3 * dA
    blocked = dz < d * math.tan(math.radians(theta))
    k_obs = 0.2 * (C.F_S0 + 0.1)
    sky = 9 / (7 * math.pi) * (1 + 2 * dz / D) / 3
    sc = TAU_EFF * np.sum(np.where(~blocked, sky, 0) * (dz / D) * dom)
    erc = TAU_EFF * np.sum(np.where(blocked, k_obs / math.pi, 0) * (dz / D) * dom)
    assert abs(sc - sky_component(P, R0, TAU_EFF, theta)) < 2e-5
    assert abs(erc - externally_reflected_component(P, R0, TAU_EFF, theta, 0.2, 0.2)) < 2e-5


# ---- T-DAY-7 (DAY-05)
def test_irc_r0_and_lumen_balance():
    r = internally_reflected_component(24, 20, 2.8, R0_WIN, REFL, 0.9, 0.8, 0.2)
    assert r["A"] == pytest.approx(104.0)
    assert r["R"] == pytest.approx(0.4654, abs=1e-4)
    assert r["R_fw"] == pytest.approx(0.3571, abs=1e-4)
    assert r["R_cw"] == pytest.approx(0.6132, abs=1e-4)
    assert rel(r["irc_sky"], 0.003738) < 1e-3
    assert rel(r["irc_ground"], 0.001620) < 1e-3
    # lumen balance for E_h = 10 000 lx
    phi_sky = 0.68 * 0.9 * 2.4 * C.F_S0 * 10000
    phi_gnd = 0.68 * 0.9 * 2.4 * 0.1 * 10000
    e_r = (phi_sky * r["R_fw"] + phi_gnd * r["R_cw"]) / (104 * (1 - r["R"]))
    assert e_r == pytest.approx(53.58, abs=0.01)
    assert rel(e_r / 10000, r["irc_sky"] + r["irc_ground"]) < 1e-9


def test_window_factor_with_obstruction():
    assert [round(sky_window_factor_obstructed(t), 4) for t in (10, 20, 30, 40, 50)] == \
        [0.3535, 0.3016, 0.2436, 0.1833, 0.1253]
    assert [round(100 * sky_window_factor(t, 0.2, 0.2), 1) for t in (0, 10, 20, 30, 40, 50)] == \
        [39.6, 36.2, 31.9, 26.8, 21.5, 16.3]


# ---- T-DAY-8 (BRE numeric form)
def test_bre_numeric_form():
    g = internally_reflected_component(24, 20, 2.8, R0_WIN, REFL, 1.0, 0.8, 0.1)
    w_glazed = 2.4
    # general form with T = 0.85 (tau 0.85, M 1) and ground 0.1
    general = internally_reflected_component(24, 20, 2.8, [IRCWindow(3.0, 1.65, 0.85, "w", 4.0)],
                                             REFL, 1.0, 0.8, 0.1)
    bre = 0.85 * w_glazed / (104 * (1 - g["R"])) * (39 * g["R_fw"] + 5 * g["R_cw"])
    assert bre == pytest.approx(0.6235, abs=1e-4)
    gen_pct = 100 * (general["irc_sky"] + general["irc_ground"])
    assert gen_pct == pytest.approx(0.6316, abs=1e-4)
    assert abs(bre - gen_pct) / gen_pct < 0.02


# ---- T-DAY-9 (DAY-06)
def test_adf_and_guard_ratio():
    adf = average_daylight_factor(24, 20, 2.8, R0_WIN, REFL, 0.9, 0.8)
    assert adf == pytest.approx(1.62, abs=1e-2)
    irc = internally_reflected_component(24, 20, 2.8, R0_WIN, REFL, 0.9, 0.8, 0.2)
    # interior nodes of a 0.25 m grid on the work plane (walls excluded)
    us = np.linspace(-1.75, 1.75, 15)
    ds = 0.25 * np.arange(1, 24)
    grid = [100 * (sky_component((u, d, 0.85), R0, TAU_EFF) + irc["irc_sky"] + irc["irc_ground"])
            for u in us for d in ds]
    mean = float(np.mean(grid))
    assert mean == pytest.approx(2.48, abs=0.01)
    assert float(np.median(grid)) == pytest.approx(1.10, abs=0.01)
    assert min(grid) == pytest.approx(0.62, abs=0.01) and max(grid) == pytest.approx(19.2, abs=0.05)
    assert 0.5 <= mean / adf <= 2.0


# ---- T-DAY-10 and T-DAY-11 (DAY-07)
CASES = [  # I, Dh, Z, Td, day: spec E_dh, E_dn; EnergyPlus transliteration values printed in DAY-07
    (800, 120, 30, 15, 172, 15831, 83479, 15830, 83478),
    (0, 150, 60, 5, 15, 17463, 0, 17458, 0),
    (300, 250, 45, 8, 74, 30124, 29543, 30130, 29543),
]


def _perez_scalar(I, Dh, Zdeg, Td, I0):
    """Second, independent scalar transcription of Perez 1990 for the test."""
    Z = math.radians(Zdeg)
    eps = ((Dh + I) / Dh + 1.041 * Z ** 3) / (1 + 1.041 * Z ** 3)
    m = 1 / (math.cos(Z) + 0.15 * (93.885 - Zdeg) ** -1.253)
    delta = Dh * m / I0
    W = math.exp(0.07 * Td - 0.075)
    bounds = [1.000, 1.065, 1.230, 1.500, 1.950, 2.800, 4.500, 6.200]
    b = max(i for i, lo in enumerate(bounds) if eps >= lo)
    a, bb, c, d = PEREZ_TABLE[b][:4]
    e_dh = Dh * (a + bb * W + c * math.cos(Z) + d * math.log(delta))
    a, bb, c, d = PEREZ_TABLE[b][4:]
    e_dn = max(0.0, I * (a + bb * W + c * math.exp(5.73 * Z - 5) + d * delta))
    return e_dh, e_dn, b + 1, eps


PEREZ_TABLE = [  # Perez 1990 Table 4, typed from physics 03 DAY-07
    (97.24, -0.46, 12.00, -8.91, 57.20, -4.55, -2.98, 117.12),
    (107.22, 1.15, 0.59, -3.95, 98.99, -3.46, -1.21, 12.38),
    (104.97, 2.96, -5.53, -8.77, 109.83, -4.90, -1.71, -8.81),
    (102.39, 5.59, -13.95, -13.90, 110.34, -5.84, -1.99, -4.56),
    (100.71, 5.94, -22.75, -23.74, 106.36, -3.97, -1.75, -6.16),
    (106.42, 3.83, -36.15, -28.83, 107.19, -1.25, -1.51, -26.73),
    (141.88, 1.90, -53.24, -14.03, 105.75, 0.77, -1.26, -34.44),
    (152.23, 0.35, -45.27, -7.98, 101.18, 1.58, -1.10, -8.29),
]


@pytest.mark.parametrize("I, Dh, Z, Td, day, e_dh, e_dn, ep_dh, ep_dn", CASES)
def test_perez_three_cases(I, Dh, Z, Td, day, e_dh, e_dn, ep_dh, ep_dn):
    i0 = 1361 * (1 + 0.033 * math.cos(2 * math.pi * day / 365))
    r = perez_luminous_efficacy([I], [Dh], [Z], [Td], [i0])
    assert abs(r["e_dh_lux"][0] - e_dh) <= 1e-3 * e_dh
    assert abs(r["e_dn_lux"][0] - e_dn) <= max(1e-3 * e_dn, 1.0)
    assert abs(r["e_dh_lux"][0] - ep_dh) <= 2e-3 * ep_dh
    assert abs(r["e_dn_lux"][0] - ep_dn) <= max(2e-3 * ep_dn, 1.0)
    s_dh, s_dn, b, _ = _perez_scalar(I, Dh, Z, Td, i0)
    assert r["bin"][0] == b
    assert r["e_dh_lux"][0] == pytest.approx(s_dh, rel=1e-9)
    assert r["e_dn_lux"][0] == pytest.approx(s_dn, rel=1e-9, abs=1e-9)


def test_perez_clear_hour_details():
    i0 = 1361 * (1 + 0.033 * math.cos(2 * math.pi * 172 / 365))
    r = perez_luminous_efficacy(800, 120, 30, 15, i0)
    assert r["epsilon"][0] == pytest.approx(6.800, abs=1e-3)
    assert r["delta"][0] == pytest.approx(0.1051, abs=1e-4)
    assert r["e_gh_lux"][0] == pytest.approx(88127, rel=1e-3)
    # below 2 degrees of altitude everything is zero
    low = perez_luminous_efficacy(100, 50, 89, 10, 1361)
    assert low["e_dh_lux"][0] == low["e_dn_lux"][0] == low["e_gh_lux"][0] == 0.0


def test_perez_coefficients_exact():
    for i, row in enumerate(PEREZ_TABLE):
        assert tuple(C.PEREZ_DIFFUSE[i]) == row[:4]
        assert tuple(C.PEREZ_DIRECT[i]) == row[4:]
    assert C.PEREZ_EPS_BOUNDS == (1.000, 1.065, 1.230, 1.500, 1.950, 2.800, 4.500, 6.200)
    assert C.PEREZ_KAPPA == 1.041


# ---- T-DAY-12 (DAY-08, DAY-09)
TOY_EDH = [4000, 9000, 15831, 22000, 12000, 2500]
TOY_EGH = [4000, 12000, 88127, 30000, 15000, 2500]
TOY_EIN = [101.2, 232.6, 517.7, 569.6, 308.5, 63.3]


def test_toy_day_illuminance_and_autonomy():
    df_sky = 0.019944 + 0 + 0.003738
    e_in = indoor_illuminance_hourly(df_sky, 0.001620, TOY_EDH, TOY_EGH)
    assert np.allclose(e_in, TOY_EIN, atol=0.15)
    occ = np.ones(6, bool)
    a300 = daylight_autonomy(e_in, occ, 300)
    assert a300["da"] == pytest.approx(0.5)
    assert a300["cda"] == pytest.approx(0.7206, abs=1e-3)
    a500 = daylight_autonomy(e_in, occ, 500)
    assert a500["da"] == pytest.approx(1 / 3)
    assert a500["cda"] == pytest.approx(0.5685, abs=1e-3)
    # components of row 3
    assert 0.019944 * 15831 == pytest.approx(315.7, abs=0.1)
    assert 0.001620 * 88127 == pytest.approx(142.8, abs=0.1)


# ---- T-DAY-13 (DAY-10)
def test_target_daylight_factor():
    assert 100 * target_daylight_factor(300, 14900)["d_t"] == pytest.approx(2.01, abs=1e-2)
    assert 100 * target_daylight_factor(100, 14900)["d_t"] == pytest.approx(0.67, abs=1e-2)
    # median over the 4380 brightest hours of a series
    e = np.concatenate([np.zeros(4380), np.full(4380, 14900.0)])
    assert target_daylight_factor(300, e)["e_vd_med_lux"] == 14900.0
