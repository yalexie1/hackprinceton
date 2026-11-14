"""Thermal comfort near glazing: physics 03 CMF-01 to CMF-07.

PMV and PPD follow the ISO 7730 equations as coded in the reference implementation named in
physics 03 (S11); this module does not import it. SolarCal follows Arens et al. 2015 (S12).
All functions are vectorised over hours where that makes sense.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from . import constants as C


# ---------------------------------------------------------------- CMF-01, CMF-02

def pmv_ppd(t_air_c, t_mrt_c, v_rel_m_s, rh_percent, met, clo, wme: float = 0.0,
            max_iter: int = 300, tol: float = 1.5e-5) -> dict:
    """CMF-01 PMV and CMF-02 PPD. Inputs broadcast; returns arrays (or floats for scalar input).

    t_cl is found by the fixed-point iteration of the reference implementation (constants as in
    CMF-01, 308.7 = 35.7 + 273). No input limits are applied; the caller warns outside them.
    """
    ta, tr, vr, rh, met_, clo_ = np.broadcast_arrays(*(np.asarray(a, dtype=float) for a in
                                                       (t_air_c, t_mrt_c, v_rel_m_s, rh_percent, met, clo)))
    scalar = ta.ndim == 0
    ta, tr, vr, rh, met_, clo_ = (np.atleast_1d(a).astype(float) for a in (ta, tr, vr, rh, met_, clo_))
    pa = rh * 10.0 * np.exp(16.6536 - 4030.183 / (ta + 235.0))
    icl = 0.155 * clo_
    m = met_ * 58.15
    w = wme * 58.15
    mw = m - w
    fcl = np.where(icl <= 0.078, 1.0 + 1.29 * icl, 1.05 + 0.645 * icl)
    hcf = 12.1 * np.sqrt(vr)
    taa, tra = ta + 273.0, tr + 273.0
    tcla = taa + (35.5 - ta) / (3.5 * icl + 0.1)
    p1 = icl * fcl
    p2 = p1 * 3.96
    p3 = p1 * 100.0
    p4 = p1 * taa
    p5 = 308.7 - 0.028 * mw + p2 * (tra / 100.0) ** 4
    xn = tcla / 100.0
    xf = tcla / 50.0
    hc = hcf.copy()
    active = np.ones(ta.shape, dtype=bool)
    for _ in range(max_iter):
        # each element iterates until its own convergence, so a vector call equals scalar calls
        xf = np.where(active, (xf + xn) / 2.0, xf)
        hcn = 2.38 * np.abs(100.0 * xf - taa) ** 0.25
        hc = np.where(active, np.maximum(hcf, hcn), hc)
        xn = np.where(active, (p5 + p4 * hc - p2 * xf ** 4) / (100.0 + p3 * hc), xn)
        active = active & (np.abs(xn - xf) >= tol)
        if not active.any():
            break
    tcl = 100.0 * xn - 273.0
    hl1 = 3.05e-3 * (5733.0 - 6.99 * mw - pa)
    hl2 = np.where(mw > 58.15, 0.42 * (mw - 58.15), 0.0)
    hl3 = 1.7e-5 * m * (5867.0 - pa)
    hl4 = 0.0014 * m * (34.0 - ta)
    hl5 = 3.96 * fcl * (xn ** 4 - (tra / 100.0) ** 4)
    hl6 = fcl * hc * (tcl - ta)
    ts = 0.303 * np.exp(-0.036 * m) + 0.028
    pmv = ts * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6)
    ppd = ppd_from_pmv(pmv)
    if scalar:
        return dict(pmv=float(pmv[0]), ppd=float(ppd[0]), t_cl=float(tcl[0]))
    return dict(pmv=pmv, ppd=ppd, t_cl=tcl)


def ppd_from_pmv(pmv):
    """CMF-02: PPD = 100 - 95 exp(-0.03353 PMV^4 - 0.2179 PMV^2), percent."""
    p = np.asarray(pmv, dtype=float)
    return 100.0 - 95.0 * np.exp(-0.03353 * p ** 4 - 0.2179 * p ** 2)


# ---------------------------------------------------------------- CMF-03

def operative_temperature(t_air_c, t_mrt_c, v_m_s, form: str = "ashrae"):
    """CMF-03. ASHRAE: A t_a + (1 - A) t_r, A by air speed; ISO 7726: (t_a sqrt(10 v) + t_r) / (1 + sqrt(10 v))."""
    ta, tr, v = (np.asarray(a, dtype=float) for a in (t_air_c, t_mrt_c, v_m_s))
    if form == "ashrae":
        A = np.where(v < 0.2, 0.5, np.where(v < 0.6, 0.6, 0.7))
        return A * ta + (1.0 - A) * tr
    if form == "iso":
        s = np.sqrt(10.0 * v)
        return (ta * s + tr) / (1.0 + s)
    raise ValueError("form must be 'ashrae' or 'iso'")


# ---------------------------------------------------------------- CMF-04

def glass_inside_surface_temperature(t_in_c, t_out_c, u_w: float, h_i: float = C.H_I_W_M2K):
    """CMF-04: T_gi = T_i - U_w (T_i - T_out) / h_i. h_i from physics 02 ENV-06 (7.69 W/m2K)."""
    ti = np.asarray(t_in_c, dtype=float)
    return ti - u_w * (ti - np.asarray(t_out_c, dtype=float)) / h_i


# ---------------------------------------------------------------- CMF-05

def omega_corner(a: float, b: float, c: float) -> float:
    """Solid angle of an a x b rectangle seen from distance c on the normal through a corner."""
    if a <= 0 or b <= 0:
        return 0.0
    return math.atan(a * b / (c * math.sqrt(a * a + b * b + c * c)))


def _superpose(fn, point_udz, window_rect) -> float:
    u_p, d_p, z_p = point_udz
    u1, u2, z1, z2 = window_rect
    if d_p <= 0:
        return 0.0

    def G(u, z):
        du, dz = u - u_p, z - z_p
        return math.copysign(1.0, du) * math.copysign(1.0, dz) * fn(abs(du), abs(dz), d_p)

    return G(u2, z2) - G(u1, z2) - G(u2, z1) + G(u1, z1)


def window_solid_angle(point_udz, window_rect) -> float:
    """CMF-05: solid angle of the window seen from the point, by four corner terms (sr)."""
    return _superpose(omega_corner, point_udz, window_rect)


def window_angle_factor(point_udz, window_rect) -> float:
    """CMF-05: F_w = Omega / (4 pi), the person treated as a small sphere."""
    return window_solid_angle(point_udz, window_rect) / (4.0 * math.pi)


def mean_radiant_temperature(f_windows: Sequence[float], t_gi_c: Sequence, t_surfaces_c):
    """CMF-05 two-temperature form: T_r^4 = sum F_w T_gi^4 + (1 - sum F_w) T_s^4 (K)."""
    ts = np.asarray(t_surfaces_c, dtype=float) + 273.15
    f_tot = float(sum(f_windows))
    acc = (1.0 - f_tot) * ts ** 4
    for f, t in zip(f_windows, t_gi_c):
        acc = acc + f * (np.asarray(t, dtype=float) + 273.15) ** 4
    return acc ** 0.25 - 273.15


# ---------------------------------------------------------------- CMF-06

def config_factor_b3(a: float, b: float, c: float) -> float:
    """Howell B-3: plane element to a parallel a x b rectangle at distance c, on the corner normal."""
    if a <= 0 or b <= 0:
        return 0.0
    A, B = a / c, b / c
    sa, sb = math.sqrt(1.0 + A * A), math.sqrt(1.0 + B * B)
    return (A / sa * math.atan(B / sa) + B / sb * math.atan(A / sb)) / (2.0 * math.pi)


def plane_factor_to_window(point_udz, window_rect) -> float:
    """CMF-06: vertical plane element facing the window, B-3 by corner superposition."""
    return _superpose(config_factor_b3, point_udz, window_rect)


def radiant_asymmetry_window(f_planes: Sequence[float], t_gi_c: Sequence, t_surfaces_c) -> np.ndarray:
    """CMF-06: dt_pr = T_pr(room side) - T_pr(window side); room side at t_surfaces (K)."""
    ts = np.asarray(t_surfaces_c, dtype=float)
    t_win = mean_radiant_temperature(f_planes, t_gi_c, ts)
    return ts - t_win


def pd_cool_wall(dt_pr_k):
    """CMF-06, informative [P]: PD = 100 / (1 + exp(6.61 - 0.345 dt_pr)), dt_pr < 15 K."""
    return 100.0 / (1.0 + np.exp(6.61 - 0.345 * np.asarray(dt_pr_k, dtype=float)))


# ---------------------------------------------------------------- CMF-07

def sky_vault_fraction(body_udz, window_rect) -> float:
    """CMF-07: f_svv = d_az d_el / (180 * 360), angles in degrees subtended at the body centre."""
    u_b, d_b, z_b = body_udz
    u1, u2, z1, z2 = window_rect
    if d_b <= 0:
        return 0.0
    d_az = math.degrees(math.atan((u2 - u_b) / d_b) - math.atan((u1 - u_b) / d_b))
    d_el = math.degrees(math.atan((z2 - z_b) / d_b) - math.atan((z1 - z_b) / d_b))
    return d_az * d_el / (180.0 * 360.0)


def projected_area_factor(sun_alt_deg, sharp_deg):
    """CMF-07: seated f_p by bilinear interpolation in the S11 table (SHARP 0..180, altitude 0..90)."""
    alt = np.clip(np.asarray(sun_alt_deg, dtype=float), 0.0, 90.0)
    sh = np.clip(np.abs(np.asarray(sharp_deg, dtype=float)), 0.0, 180.0)
    tab = np.asarray(C.FP_SEATED)
    i = np.minimum((sh // 15).astype(int), 11)
    j = np.minimum((alt // 15).astype(int), 5)
    fs = (sh - 15.0 * i) / 15.0
    fa = (alt - 15.0 * j) / 15.0
    return ((1 - fs) * (1 - fa) * tab[i, j] + (1 - fs) * fa * tab[i, j + 1]
            + fs * (1 - fa) * tab[i + 1, j] + fs * fa * tab[i + 1, j + 1])


def solar_gain_delta_mrt(sun_alt_deg, sharp_deg, i_dir, i_diff, t_sol, f_svv, f_bes, alpha_sw: float,
                         r_floor: float, posture: str = "seated") -> dict:
    """CMF-07 SolarCal: ERF_sol = (E_diff + E_refl + E_dir) alpha_SW / alpha_LW; dMRT = ERF / (f_eff h_r).

    `t_sol` may be a scalar or `(t_sol_diffuse_weighted, t_sol_direct)`; `f_svv` is the sum over
    windows. Only the seated projected-area table is in physics 03, so posture must be "seated".
    """
    if posture not in ("seated", "sitting"):
        raise NotImplementedError("physics 03 tabulates f_p for a seated person only")
    f_eff = C.F_EFF["seated"]
    if isinstance(t_sol, tuple):
        t_diff, t_dir = t_sol
    else:
        t_diff = t_dir = t_sol
    alt = np.asarray(sun_alt_deg, dtype=float)
    beta = np.radians(np.clip(alt, 0.0, 90.0))
    i_dir = np.asarray(i_dir, dtype=float)
    i_diff = np.asarray(i_diff, dtype=float)
    i_th = i_dir * np.sin(beta) + i_diff
    e_diff = 0.5 * f_eff * np.asarray(f_svv) * np.asarray(t_diff) * i_diff
    e_refl = 0.5 * f_eff * np.asarray(f_svv) * np.asarray(t_diff) * i_th * r_floor
    f_p = projected_area_factor(alt, sharp_deg)
    e_dir = f_eff * f_p * np.asarray(f_bes) * np.asarray(t_dir) * i_dir
    erf = (e_diff + e_refl + e_dir) * alpha_sw / C.ALPHA_LW
    d_mrt = erf / (f_eff * C.H_R_W_M2K)
    return dict(erf_w_m2=erf, delta_mrt_k=d_mrt, f_p=f_p)
