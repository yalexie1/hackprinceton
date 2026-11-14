"""A15: SHD-01 analytic wall thresholds, SHD-02 closed forms, SHD-03 and SHD-05 worked examples."""
from __future__ import annotations

import math
import socket

import numpy as np
import pytest

from backend.analysis.solar.shading import (annual_shading_loss, beam_shading_fraction,
                                            diffuse_shading_factor, plane_normal, rays_blocked,
                                            shaded_poa_components, sky_view_factor, sun_vectors)
from backend.analysis.solar.shading.raycast import LIFT_M


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def wall(y: float, h: float, half_len: float = 1e4) -> np.ndarray:
    """Vertical wall in the plane y = const, from x = -half_len to +half_len, z 0..h (two triangles)."""
    a, b = np.array([-half_len, y, 0.0]), np.array([half_len, y, 0.0])
    c, d = np.array([half_len, y, h]), np.array([-half_len, y, h])
    return np.array([[a, b, c], [a, c, d]])


def sun(el_deg: float, az_deg: float) -> np.ndarray:
    return sun_vectors([90.0 - el_deg], [az_deg])[0]


@pytest.mark.parametrize("az, threshold", [(180.0, 21.8014), (150.0, 19.1066)])
def test_shd01_analytic_wall_threshold(az, threshold):
    # SHD-01 worked example: point at the origin, wall 4 m high 10 m to the south.
    assert math.degrees(math.atan(4 * math.cos(math.radians(az - 180)) / 10)) == pytest.approx(threshold, abs=1e-4)
    scene = wall(-10.0, 4.0)
    o = np.zeros((1, 3))
    assert rays_blocked(o, sun(threshold - 0.05, az)[None], scene)[0]
    assert not rays_blocked(o, sun(threshold + 0.05, az)[None], scene)[0]
    # through the tool function (sample point placed so the lifted origin is the origin)
    pt = np.array([[0.0, 0.0, -LIFT_M]])
    n = np.array([0.0, 0.0, 1.0])
    assert beam_shading_fraction(pt, n, sun(threshold - 0.05, az), scene) == 1.0
    assert beam_shading_fraction(pt, n, sun(threshold + 0.05, az), scene) == 0.0


def test_shd01_fraction_counts_points_and_skips_night():
    scene = wall(-10.0, 4.0, half_len=1.0)            # short wall: shades points near x = 0 only
    pts = np.array([[x, 0.0, 0.0] for x in (-3.0, 0.0, 3.0)])
    n = np.array([0.0, 0.0, 1.0])
    assert beam_shading_fraction(pts, n, sun(10.0, 180.0), scene) == pytest.approx(1 / 3)
    assert beam_shading_fraction(pts, n, sun(-5.0, 180.0), scene) == 0.0      # sun below horizon
    # sun behind a south-facing 30 deg panel (low northern sun)
    assert beam_shading_fraction(pts, plane_normal(30, 180), sun(5.0, 0.0), wall(10.0, 50.0)) == 0.0


def test_shd02_closed_forms():
    origin = np.array([0.0, 0.0, -LIFT_M])
    psi = 30.0
    w = wall(-10.0, 10.0 * math.tan(math.radians(psi)))
    # open sky, beta = 20: (1 + cos beta) / 2
    assert sky_view_factor(origin, plane_normal(20, 180), np.zeros((0, 3, 3))) == pytest.approx(
        (1 + math.cos(math.radians(20))) / 2, abs=0.002)
    # horizontal, wall psi = 30: (1 + cos psi) / 2 = 0.933013
    svf_h = sky_view_factor(origin, plane_normal(0, 180), w)
    assert svf_h == pytest.approx(0.933013, abs=0.002)
    # beta = 20 facing the wall: (1 + cos(beta + psi)) / 2 = 0.821394
    svf_t = sky_view_factor(origin, plane_normal(20, 180), w)
    assert svf_t == pytest.approx(0.821394, abs=0.002)
    assert diffuse_shading_factor(0.821394, 20.0) == pytest.approx(0.84693, abs=1e-5)


def test_shd02_against_pvlib_passias():
    pvlib = pytest.importorskip("pvlib")
    origin = np.array([0.0, 0.0, -LIFT_M])
    w = wall(-10.0, 5.7735)
    loss = 1.0 - sky_view_factor(origin, plane_normal(0, 180), w)
    assert loss == pytest.approx(float(pvlib.shading.sky_diffuse_passias(30.0)), abs=0.002)


def test_shd03_worked_example():
    # Running example: Eb 670.332, Ecirc 153.663, Eiso 56.380, Ehor 11.839, Eg 4.825
    sh = shaded_poa_components(670.332, 153.663 + 56.380 + 11.839, 4.825, 3 / 9, 0.84693,
                               poa_sky_circumsolar=153.663)
    assert float(sh["poa_global_shaded"]) == pytest.approx(611.93, abs=0.01)
    assert float(sh["poa_global"]) == pytest.approx(897.04, abs=0.01)
    assert float(sh["shading_factor"]) == pytest.approx(0.3178, abs=1e-4)
    # SAM rule (no circumsolar split): 639.63
    sam = shaded_poa_components(670.332, 153.663 + 56.380 + 11.839, 4.825, 3 / 9, 0.84693)
    assert float(sam["poa_global_shaded"]) == pytest.approx(639.63, abs=0.01)
    # f_b = 0 and S_d = 1 give back the unshaded total (IRR-10)
    un = shaded_poa_components(670.332, 221.882, 4.825, 0.0, 1.0, 153.663)
    assert float(un["poa_global_shaded"]) == pytest.approx(897.039, abs=1e-9)
    assert float(un["shading_factor"]) == 0.0


def test_shd05_worked_example():
    assert annual_shading_loss([1900.0], [1750.0]) == pytest.approx(0.0789, abs=1e-4)
    assert annual_shading_loss([0.0, 0.0], [0.0, 0.0]) == 0.0
