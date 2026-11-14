"""Glare risk for a seated viewer: physics 03 GLR-01, GLR-02, GLR-04, GLR-05.

GLR-01 and GLR-04 are this project's geometric simplifications (section 2 of physics 03); GLR-02
is Wienold's published DGPs. GLR-03 (full DGP) is reference only and not computed.
"""
from __future__ import annotations

import math

import numpy as np

from . import constants as C
from .daylight import _gl_interval, obstruction_luminance_factor
from .geometry import wrap180


# ---------------------------------------------------------------- GLR-01

def _pieces(a: float, b: float, cuts) -> list[tuple[float, float]]:
    pts = sorted({a, b, *[c for c in cuts if a < c < b]})
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1) if pts[i + 1] > pts[i]]


def vertical_window_factors(eye_udz, view_tn, window_rect, theta_o_deg: float = 0.0,
                            rho_o: float = 0.2, rho_g: float = 0.2, n: int = 24) -> dict:
    """GLR-01 integrals for one window, unglazed: SC_v (sky above eye level, obstruction luminance
    `L_obs` below the profile angle) and GC_v (ground below eye level).

    `view_tn` is the horizontal view vector as (component along e_t, component along e_n); e_n
    points out through the glass. Integrated by Gauss-Legendre on pieces split at the kinks
    (eye level, obstruction line, and the line where r.v = 0).
    """
    u_e, d_e, z_e = eye_udz
    v_t, v_n = view_tn
    u1, u2, z1, z2 = window_rect
    if d_e <= 0:
        return dict(sc_v=0.0, gc_v=0.0)
    z_obs = z_e + d_e * math.tan(math.radians(theta_o_deg)) if theta_o_deg > 0 else z_e
    k_obs = obstruction_luminance_factor(rho_o, rho_g)
    u_cuts = [u_e]
    if abs(v_t) > 1e-12:
        u_cuts.append(u_e - v_n * d_e / v_t)
    sc = gc = 0.0
    for ua, ub in _pieces(u1, u2, u_cuts):
        uu, wu = _gl_interval(ua, ub, n)
        for za, zb in _pieces(z1, z2, [z_e, z_obs]):
            zz, wz = _gl_interval(za, zb, n)
            U, Z = np.meshgrid(uu, zz, indexing="ij")
            W = np.outer(wu, wz)
            du, dz = U - u_e, Z - z_e
            D = np.sqrt(du * du + d_e * d_e + dz * dz)
            rv = np.maximum(0.0, (v_t * du + v_n * d_e) / D)
            kern = rv * d_e / D ** 3                      # max(0, r.v) dOmega / dA
            zm = (za + zb) / 2.0
            if zm > z_obs:
                lum = 9.0 / (7.0 * math.pi) * (1.0 + 2.0 * dz / D) / 3.0
                sc += float(np.sum(W * lum * kern))
            elif zm > z_e:
                sc += float(np.sum(W * kern)) * k_obs / math.pi
            else:
                gc += float(np.sum(W * kern)) * rho_g / math.pi
    return dict(sc_v=sc, gc_v=gc)


def vertical_eye_illuminance(v_sky: float, v_gnd: float, e_dh_lux, e_gh_lux) -> np.ndarray:
    """GLR-01: E_v = V_sky E_dh + V_gnd E_gh."""
    return v_sky * np.asarray(e_dh_lux, dtype=float) + v_gnd * np.asarray(e_gh_lux, dtype=float)


# ---------------------------------------------------------------- GLR-02

def dgp_simplified(e_v_lux):
    """GLR-02: DGPs = 6.22e-5 E_v + 0.184 (Wienold 2009 eq. 1)."""
    return C.DGPS_SLOPE * np.asarray(e_v_lux, dtype=float) + C.DGPS_INTERCEPT


def dgp_simplified_inverse(dgps: float) -> float:
    return (dgps - C.DGPS_INTERCEPT) / C.DGPS_SLOPE


def glare_rating(dgp: float) -> str:
    """GLR-02 table (Wienold 2009 Table 5)."""
    if dgp <= 0.35:
        return "imperceptible"
    if dgp <= 0.40:
        return "perceptible"
    if dgp <= 0.45:
        return "disturbing"
    return "intolerable"


# ---------------------------------------------------------------- GLR-04

def sun_visible_through_window(point_udz, window_rect, a_w_deg: float, sun_alt_deg, sun_az_deg,
                               theta_o_deg: float = 0.0) -> dict:
    """GLR-04: is the sun seen from the point through the window rectangle? Vectorised over hours.

    Delta = wrap180(A_s - A_w); in front when h > 0 and cos(Delta) > 0;
    u_hit = u + d tan(Delta); z_hit = z + d tan(h) / cos(Delta);
    visible = in front, hit inside the rectangle, and tan(h) > tan(theta_o) cos(Delta).
    """
    u, d, z = point_udz
    u1, u2, z1, z2 = window_rect
    h = np.radians(np.asarray(sun_alt_deg, dtype=float))
    delta = np.radians(wrap180(np.asarray(sun_az_deg, dtype=float) - a_w_deg))
    cosd = np.cos(delta)
    front = (h > 0) & (cosd > 1e-9) & (d > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        u_hit = np.where(front, u + d * np.tan(delta), np.nan)
        z_hit = np.where(front, z + d * np.tan(h) / np.where(front, cosd, 1.0), np.nan)
        vis = (front & (u_hit >= u1) & (u_hit <= u2) & (z_hit >= z1) & (z_hit <= z2)
               & (np.tan(h) > math.tan(math.radians(theta_o_deg)) * cosd))
    return dict(visible=vis, u_hit=u_hit, z_hit=z_hit)


def cos_sun_view(sun_alt_deg, sun_az_deg, view_az_deg: float):
    """GLR-04: cos_sv = cos(h) cos(A_s - A_v)."""
    return np.cos(np.radians(sun_alt_deg)) * np.cos(np.radians(np.asarray(sun_az_deg) - view_az_deg))


# ---------------------------------------------------------------- GLR-05

def glare_hours(e_v_lux, sun_visible, cos_sv) -> np.ndarray:
    """GLR-05: glare_hour = sun_in_view or DGPs(E_v) > 0.40, with sun_in_view = visible and cos_sv > 0."""
    sun_in_view = np.asarray(sun_visible, dtype=bool) & (np.asarray(cos_sv) > 0)
    return sun_in_view | (dgp_simplified(e_v_lux) > C.DGP_GLARE_LIMIT)


def glare_risk(glare_hour, occupied_mask) -> float:
    """GLR-05: share of occupied hours that are glare hours."""
    occ = np.asarray(occupied_mask, dtype=bool)
    if not occ.any():
        return 0.0
    return float(np.mean(np.asarray(glare_hour, dtype=bool)[occ]))
