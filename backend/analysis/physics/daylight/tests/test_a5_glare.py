"""A5 glare entries GLR-01, GLR-02, GLR-04, GLR-05 against physics 03 (test plan 5)."""
import math
import socket

import numpy as np
import pytest

from backend.analysis.physics.daylight.comfort import plane_factor_to_window
from backend.analysis.physics.daylight.glare import (
    cos_sun_view, dgp_simplified, dgp_simplified_inverse, glare_hours, glare_rating, glare_risk,
    sun_visible_through_window, vertical_eye_illuminance, vertical_window_factors)

R0 = (-1.0, 1.0, 0.9, 2.4)
EYE = (0.0, 2.0, 1.2)
TAU_EFF = 0.4896
IRC_SKY, IRC_GND = 0.003738, 0.001620


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A5 tests must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


# ---- T-GLR-1 (GLR-01)
@pytest.mark.parametrize("view, sc_v, gc_v, v_sky, v_gnd", [
    ((1.0, 0.0), 0.010104, 0.000942, 0.008685, 0.002081),
    ((-1.0, 0.0), 0.010104, 0.000942, 0.008685, 0.002081),
    ((0.0, 1.0), 0.087119, 0.008134, 0.046392, 0.005602),
    ((0.0, -1.0), 0.0, 0.0, 0.003738, 0.001620),
])
def test_view_factors_r0(view, sc_v, gc_v, v_sky, v_gnd):
    f = vertical_window_factors(EYE, view, R0)
    assert f["sc_v"] == pytest.approx(sc_v, rel=1e-3, abs=1e-9)
    assert f["gc_v"] == pytest.approx(gc_v, rel=1e-3, abs=1e-9)
    assert TAU_EFF * f["sc_v"] + IRC_SKY == pytest.approx(v_sky, rel=1e-3)
    assert TAU_EFF * f["gc_v"] + IRC_GND == pytest.approx(v_gnd, rel=1e-3)


def test_view_factors_midpoint_sum():
    """Second computation of the facing view by a 1500 x 1500 midpoint sum."""
    n = 1500
    u = -1 + (np.arange(n) + 0.5) * 2 / n
    z = 0.9 + (np.arange(n) + 0.5) * 1.5 / n
    U, Z = np.meshgrid(u, z)
    d, dz = 2.0, Z - 1.2
    D = np.sqrt(U ** 2 + d ** 2 + dz ** 2)
    kern = (d / D) * d / D ** 3 * (2 / n) * (1.5 / n)
    sky = np.sum(np.where(dz > 0, 9 / (7 * math.pi) * (1 + 2 * dz / D) / 3 * kern, 0))
    gnd = np.sum(np.where(dz <= 0, 0.2 / math.pi * kern, 0))
    f = vertical_window_factors(EYE, (0.0, 1.0), R0)
    assert f["sc_v"] == pytest.approx(sky, rel=1e-4)
    assert f["gc_v"] == pytest.approx(gnd, rel=1e-4)
    # uniform luminance: numeric configuration factor against Howell B-3 by superposition
    uniform = np.sum(kern) / math.pi
    assert uniform == pytest.approx(0.177116, abs=1e-5)
    assert plane_factor_to_window(EYE, R0) == pytest.approx(0.177116, abs=1e-5)


def test_eye_illuminance_two_hours():
    views = {"parallel": (1.0, 0.0), "facing": (0.0, 1.0), "back": (0.0, -1.0)}
    want = {"parallel": (188, 321), "facing": (908, 1228), "back": (94, 202)}
    for k, v in views.items():
        f = vertical_window_factors(EYE, v, R0)
        vs, vg = TAU_EFF * f["sc_v"] + IRC_SKY, TAU_EFF * f["gc_v"] + IRC_GND
        over = vertical_eye_illuminance(vs, vg, 17463, 17463)
        clear = vertical_eye_illuminance(vs, vg, 15831, 88127)
        assert float(over) == pytest.approx(want[k][0], abs=1.0)
        assert float(clear) == pytest.approx(want[k][1], abs=1.0)


# ---- T-GLR-2 (GLR-02)
def test_dgps():
    assert float(dgp_simplified(908)) == pytest.approx(0.2405, abs=1e-4)
    assert float(dgp_simplified(1228)) == pytest.approx(0.2604, abs=1e-4)
    assert float(dgp_simplified(3473)) == pytest.approx(0.4000, abs=1e-4)
    assert dgp_simplified_inverse(0.40) == pytest.approx(3473, abs=1)
    assert [round(dgp_simplified_inverse(x)) for x in (0.35, 0.40, 0.45)] == [2669, 3473, 4277]
    assert glare_rating(0.2405) == "imperceptible" and glare_rating(0.42) == "disturbing"


# ---- T-GLR-3 (GLR-04)
SUN_CASES = [(20, 25, 0.728, 2.192, True, 0.310), (20, 40, 0.728, 2.986, False, 0.262),
             (-60, 10, -3.464, 1.905, False, -0.853), (100, 30, None, None, False, 0.853)]


@pytest.mark.parametrize("delta, h, u_hit, z_hit, visible, cos_sv", SUN_CASES)
def test_sun_through_window(delta, h, u_hit, z_hit, visible, cos_sv):
    a_w = 210.0                      # any window azimuth; the sun is at a_w + delta
    r = sun_visible_through_window(EYE, R0, a_w, [h], [a_w + delta])
    assert bool(r["visible"][0]) is visible
    if u_hit is None:
        assert np.isnan(r["u_hit"][0])
    else:
        assert r["u_hit"][0] == pytest.approx(u_hit, abs=1e-3)
        assert r["z_hit"][0] == pytest.approx(z_hit, abs=1e-3)
        # second computation: intersect the sun vector with the glass plane in Cartesian form
        hr, dr = math.radians(h), math.radians(delta)
        s = np.array([math.cos(hr) * math.sin(dr), math.cos(hr) * math.cos(dr), math.sin(hr)])  # (e_t, e_n, z)
        t = EYE[1] / s[1]
        assert EYE[0] + t * s[0] == pytest.approx(r["u_hit"][0], abs=1e-6)
        assert EYE[2] + t * s[2] == pytest.approx(r["z_hit"][0], abs=1e-6)
    # view parallel to the wall along +e_t has azimuth a_w + 90
    assert float(cos_sun_view(h, a_w + delta, a_w + 90.0)) == pytest.approx(cos_sv, abs=1e-3)


def test_obstruction_blocks_low_sun():
    r = sun_visible_through_window(EYE, R0, 0.0, [25.0], [20.0], theta_o_deg=30.0)
    assert not r["visible"][0]


# ---- T-GLR-4 and GLR-05
def test_glare_toy_hours_and_orderings():
    f_par = vertical_window_factors(EYE, (1.0, 0.0), R0)
    vs, vg = TAU_EFF * f_par["sc_v"] + IRC_SKY, TAU_EFF * f_par["gc_v"] + IRC_GND
    e_dh = np.array([4000, 9000, 15831, 22000, 12000, 2500.0])
    e_gh = np.array([4000, 12000, 88127, 30000, 15000, 2500.0])
    e_v = vertical_eye_illuminance(vs, vg, e_dh, e_gh)
    assert np.allclose(e_v, [43, 103, 321, 254, 135, 27], atol=1.0)
    assert e_v[2] == pytest.approx(320.9, abs=0.1)
    occ = np.ones(6, bool)
    none = glare_hours(e_v, np.zeros(6, bool), np.ones(6))
    assert glare_risk(none, occ) == 0.0
    vis = np.array([True, False, False, False, False, False])
    one = glare_hours(e_v, vis, np.full(6, 0.310))
    assert glare_risk(one, occ) == pytest.approx(1 / 6)

    # a year of sun positions in front of a south window: back to the window never sees the sun,
    # facing sees it at least as often as parallel
    rng = np.random.default_rng(1)
    h = rng.uniform(-10, 80, 2000)
    az = rng.uniform(0, 360, 2000)
    a_w = 180.0
    vis = sun_visible_through_window(EYE, R0, a_w, h, az)["visible"]
    back = vis & (cos_sun_view(h, az, a_w + 180) > 0)
    facing = vis & (cos_sun_view(h, az, a_w) > 0)
    par = vis & (cos_sun_view(h, az, a_w + 90) > 0)
    assert not back.any()
    assert facing.sum() >= par.sum() > 0
