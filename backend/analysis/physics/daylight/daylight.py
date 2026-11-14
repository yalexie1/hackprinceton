"""Daylight at a point: physics 03 DAY-02 to DAY-10.

Points and windows are in the wall frame of section 0.2: a window is `(u1, u2, z1, z2)`, a point
`(u, d, z)` with `d > 0` inside the room. Fractions are fractions (DF of 0.025 is 2.5 %).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from . import constants as C

_GL_CACHE: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def gauss_legendre(n: int) -> tuple[np.ndarray, np.ndarray]:
    if n not in _GL_CACHE:
        _GL_CACHE[n] = np.polynomial.legendre.leggauss(n)
    return _GL_CACHE[n]


def _gl_interval(a: float, b: float, n: int) -> tuple[np.ndarray, np.ndarray]:
    x, w = gauss_legendre(n)
    half = (b - a) / 2.0
    return a + half * (x + 1.0), w * half


# ---------------------------------------------------------------- DAY-02

def cie_overcast_luminance(gamma_rad, e_h_lux):
    """DAY-02: L(gamma) = L_z (1 + 2 sin gamma) / 3 with E_h = (7 pi / 9) L_z. cd/m2."""
    l_z = np.asarray(e_h_lux, dtype=float) / C.EH_OVER_LZ
    return l_z * (1.0 + 2.0 * np.sin(gamma_rad)) / 3.0


# ---------------------------------------------------------------- DAY-03

def _G(s):
    return s * s / 6.0 + 2.0 * s ** 3 / 9.0


def sky_component(point_udz, window_rect, tau_eff: float, obstruction_angle_deg: float = 0.0,
                  n: int = 64) -> float:
    """DAY-03 (with DAY-04's z_b): sky component of a vertical window under the CIE overcast sky.

    SC = tau_eff (9 / 7 pi) * integral over phi of [G(s_hi) - G(s_lo)], exact in altitude.
    """
    u_p, d_p, z_p = point_udz
    u1, u2, z1, z2 = window_rect
    if d_p <= 0:
        return 0.0
    z_b = z_p + d_p * math.tan(math.radians(obstruction_angle_deg))
    z_lo = max(z1, z_b, z_p)
    if z2 <= z_lo:
        return 0.0
    phi1, phi2 = math.atan((u1 - u_p) / d_p), math.atan((u2 - u_p) / d_p)
    phi, w = _gl_interval(phi1, phi2, n)
    r = d_p / np.cos(phi)

    def s(z):
        dz = max(0.0, z - z_p)
        return dz / np.sqrt(r * r + dz * dz)

    return float(tau_eff * 9.0 / (7.0 * math.pi) * np.sum(w * (_G(s(z2)) - _G(s(z_lo)))))


# ---------------------------------------------------------------- DAY-04 and CMF-06 B-4

def config_factor_b4(a: float, b: float, c: float) -> float:
    """Howell B-4 (CMF-06): horizontal element to a perpendicular rectangle of height a and width b,
    at distance c from the rectangle's plane, level with its base and in line with a corner."""
    if a <= 0 or b <= 0:
        return 0.0
    A, Cc = a / b, c / b
    Y = math.hypot(A, Cc)
    return (math.atan(1.0 / Cc) - (Cc / Y) * math.atan(1.0 / Y)) / (2.0 * math.pi)


def config_factor_horizontal_to_window(point_udz, u1: float, u2: float, za: float, zb: float) -> float:
    """B-4 by corner superposition: horizontal element at the point to the window part
    [u1, u2] x [za, zb] with za, zb >= z_p (only the part above the element is seen)."""
    u_p, d_p, z_p = point_udz
    lo, hi = max(za, z_p) - z_p, max(zb, z_p) - z_p
    if hi <= lo or d_p <= 0:
        return 0.0

    def strip(h):
        tot = 0.0
        for u, sgn in ((u2, 1.0), (u1, -1.0)):
            du = u - u_p
            tot += sgn * math.copysign(1.0, du) * config_factor_b4(h, abs(du), d_p)
        return tot

    return strip(hi) - strip(lo)


def obstruction_luminance_factor(rho_o: float, rho_g: float) -> float:
    """DAY-04 [P]: k_obs = rho_o (f_s0 + 0.5 rho_g), so L_obs = k_obs E_h / pi."""
    return rho_o * (C.F_S0 + 0.5 * rho_g)


def externally_reflected_component(point_udz, window_rect, tau_eff: float, theta_o_deg: float,
                                   rho_o: float, rho_g: float) -> float:
    """DAY-04: ERC = tau_eff k_obs F_B4(blocked part z1 .. min(z2, z_b), above the work plane)."""
    u_p, d_p, z_p = point_udz
    u1, u2, z1, z2 = window_rect
    if theta_o_deg <= 0 or d_p <= 0:
        return 0.0
    z_b = z_p + d_p * math.tan(math.radians(theta_o_deg))
    F = config_factor_horizontal_to_window(point_udz, u1, u2, max(z1, z_p), min(z2, z_b))
    return tau_eff * obstruction_luminance_factor(rho_o, rho_g) * F


# ---------------------------------------------------------------- DAY-05

def sky_window_factor_obstructed(theta_o_deg: float, n: int = 96) -> float:
    """f_sky(theta_o): DAY-02 vertical integral restricted to tan(gamma) > tan(theta_o) cos(alpha).
    Inner integral in altitude is analytic; outer by Gauss-Legendre in azimuth."""
    if theta_o_deg <= 0:
        return C.F_S0
    t = math.tan(math.radians(theta_o_deg))
    alpha, w = _gl_interval(-math.pi / 2.0, math.pi / 2.0, n)
    g0 = np.arctan(t * np.cos(alpha))

    def I(g):
        return g / 2.0 + np.sin(2.0 * g) / 4.0 - (2.0 / 3.0) * np.cos(g) ** 3

    inner = I(math.pi / 2.0) - I(g0)
    return float(9.0 / (7.0 * math.pi) / 3.0 * np.sum(w * np.cos(alpha) * inner))


def sky_window_factor(theta_o_deg: float, rho_o: float, rho_g: float) -> float:
    """DAY-05: f_s = f_sky(theta_o) + k_obs sin(theta_o) / 2; f_s0 = 0.39618 unobstructed."""
    if theta_o_deg <= 0:
        return C.F_S0
    return (sky_window_factor_obstructed(theta_o_deg)
            + obstruction_luminance_factor(rho_o, rho_g) * math.sin(math.radians(theta_o_deg)) / 2.0)


@dataclass(frozen=True)
class IRCWindow:
    """What DAY-05 and DAY-06 need of one window."""
    area_m2: float          # opening area (width x height)
    mid_height_m: float
    tau: float
    wall_id: Optional[str] = None
    wall_length_m: float = 0.0


def _room_reflectances(floor_area: float, perimeter: float, height: float,
                       windows: Sequence[IRCWindow], refl: dict) -> dict:
    A = 2.0 * floor_area + perimeter * height
    open_area = sum(w.area_m2 for w in windows)
    walls = perimeter * height
    R = (floor_area * refl["floor"] + floor_area * refl["ceiling"]
         + (walls - open_area) * refl["walls"] + open_area * refl["glass"]) / A
    walls_seen = {}
    for w in windows:
        walls_seen[w.wall_id if w.wall_id is not None else id(w)] = w.wall_length_m
    other_perim = max(0.0, perimeter - sum(walls_seen.values()))
    g_area = sum(w.area_m2 for w in windows)
    mid = (sum(w.mid_height_m * w.area_m2 for w in windows) / g_area) if g_area > 0 else height / 2
    mid = min(max(mid, 0.0), height)
    lower, upper = other_perim * mid, other_perim * (height - mid)
    R_fw = (floor_area * refl["floor"] + lower * refl["walls"]) / (floor_area + lower)
    R_cw = (floor_area * refl["ceiling"] + upper * refl["walls"]) / (floor_area + upper)
    return dict(A=A, R=R, R_fw=R_fw, R_cw=R_cw)


def internally_reflected_component(floor_area_m2: float, perimeter_m: float, height_m: float,
                                   windows: Sequence[IRCWindow], reflectances: dict, m: float,
                                   k_f: float, rho_g: float, theta_o_deg: float = 0.0,
                                   rho_o: float = 0.2) -> dict:
    """DAY-05 split-flux: IRC_sky = tau M A_g f_s R_fw / (A (1 - R));
    IRC_ground = tau M A_g (0.5 rho_g) R_cw / (A (1 - R)). Sums over the room's windows.

    `reflectances`: keys floor, ceiling, walls, glass. Window walls are excluded from R_fw and R_cw;
    the split height is the area-weighted window mid-height.
    """
    if not windows:
        return dict(irc_sky=0.0, irc_ground=0.0, A=0.0, R=0.0, R_fw=0.0, R_cw=0.0, f_s=0.0)
    g = _room_reflectances(floor_area_m2, perimeter_m, height_m, windows, reflectances)
    flux = sum(w.tau * m * k_f * w.area_m2 for w in windows)
    pre = flux / (g["A"] * (1.0 - g["R"]))
    f_s = sky_window_factor(theta_o_deg, rho_o, rho_g)
    return dict(irc_sky=pre * f_s * g["R_fw"], irc_ground=pre * 0.5 * rho_g * g["R_cw"], f_s=f_s, **g)


# ---------------------------------------------------------------- DAY-06

def average_daylight_factor(floor_area_m2: float, perimeter_m: float, height_m: float,
                            windows: Sequence[IRCWindow], reflectances: dict, m: float, k_f: float,
                            theta_deg: float = 90.0) -> float:
    """DAY-06: ADF[%] = tau M A_g theta / (A (1 - R^2)). Room-level sanity check only."""
    if not windows:
        return 0.0
    g = _room_reflectances(floor_area_m2, perimeter_m, height_m, windows, reflectances)
    flux = sum(w.tau * m * k_f * w.area_m2 for w in windows)
    return flux * theta_deg / (g["A"] * (1.0 - g["R"] ** 2))


# ---------------------------------------------------------------- DAY-07

def extraterrestrial_normal(day_of_year):
    """DAY-07 worked example: I0 = 1361 (1 + 0.033 cos(2 pi n / 365)), W/m2."""
    return C.SOLAR_CONSTANT_W_M2 * (1.0 + 0.033 * np.cos(2.0 * np.pi * np.asarray(day_of_year) / 365.0))


def perez_luminous_efficacy(dni_w_m2, dhi_w_m2, zenith_deg, dew_point_c, i0_w_m2) -> dict:
    """DAY-07: Perez et al. 1990 eqs (1), (2), (3), (7), (8), Tables 1 and 4. Vectorised.

    Returns e_dh_lux, e_dn_lux, e_gh_lux, epsilon, delta, bin (1..8; 0 with the sun below 2 deg).
    """
    I = np.atleast_1d(np.asarray(dni_w_m2, dtype=float))
    Dh = np.atleast_1d(np.asarray(dhi_w_m2, dtype=float))
    zd = np.atleast_1d(np.asarray(zenith_deg, dtype=float))
    Td = np.broadcast_to(np.asarray(dew_point_c, dtype=float), I.shape)
    I0 = np.broadcast_to(np.asarray(i0_w_m2, dtype=float), I.shape)
    Z = np.radians(zd)
    up = (90.0 - zd) >= C.SUN_MIN_ALTITUDE_DEG
    kz3 = C.PEREZ_KAPPA * Z ** 3
    with np.errstate(divide="ignore", invalid="ignore"):
        eps = np.where(Dh > 0, ((Dh + I) / np.where(Dh > 0, Dh, 1.0) + kz3) / (1.0 + kz3), np.inf)
        m = 1.0 / (np.cos(Z) + 0.15 * np.maximum(93.885 - zd, 1e-6) ** (-1.253))
        delta = Dh * m / I0
        W = np.exp(0.07 * Td - 0.075)
        b = np.searchsorted(np.asarray(C.PEREZ_EPS_BOUNDS), eps, side="right")   # 1..8
        b = np.clip(b, 1, 8)
        dif = np.asarray(C.PEREZ_DIFFUSE)[b - 1]
        dir_ = np.asarray(C.PEREZ_DIRECT)[b - 1]
        ln_delta = np.log(np.where(delta > 0, delta, 1.0))
        eff_d = dif[:, 0] + dif[:, 1] * W + dif[:, 2] * np.cos(Z) + dif[:, 3] * ln_delta
        eff_b = dir_[:, 0] + dir_[:, 1] * W + dir_[:, 2] * np.exp(5.73 * Z - 5.0) + dir_[:, 3] * delta
    e_dh = np.where(up & (Dh > 0), Dh * eff_d, 0.0)
    e_dn = np.where(up, np.maximum(0.0, I * eff_b), 0.0)
    e_gh = e_dh + e_dn * np.cos(Z)
    e_gh = np.where(up, e_gh, 0.0)
    return dict(e_dh_lux=e_dh, e_dn_lux=e_dn, e_gh_lux=e_gh, epsilon=eps, delta=delta,
                bin=np.where(up, b, 0))


# ---------------------------------------------------------------- DAY-08, DAY-09, DAY-10

def indoor_illuminance_hourly(df_sky: float, df_gnd: float, e_dh_lux, e_gh_lux) -> np.ndarray:
    """DAY-08: E_in = DF_sky E_dh + DF_gnd E_gh (direct beam excluded)."""
    return df_sky * np.asarray(e_dh_lux, dtype=float) + df_gnd * np.asarray(e_gh_lux, dtype=float)


def daylight_autonomy(e_in_lux, occupied_mask, target_lux: float) -> dict:
    """DAY-09: DA_T = share of occupied hours with E_in >= T; cDA_T = mean of min(1, E_in / T)."""
    e = np.asarray(e_in_lux, dtype=float)
    occ = np.asarray(occupied_mask, dtype=bool)
    n = int(occ.sum())
    if n == 0:
        return dict(da=0.0, cda=0.0)
    e = e[occ]
    return dict(da=float(np.mean(e >= target_lux)), cda=float(np.mean(np.minimum(1.0, e / target_lux))))


def target_daylight_factor(target_lux: float, e_dh_lux) -> dict:
    """DAY-10: D_T = T / E_v,d,med; E_v,d,med is the median diffuse horizontal illuminance over the
    4380 hours with the highest value (or a given median when a scalar is passed)."""
    e = np.atleast_1d(np.asarray(e_dh_lux, dtype=float))
    if e.size == 1:
        med = float(e[0])
    else:
        top = np.sort(e)[::-1][:min(4380, e.size)]
        med = float(np.median(top))
    return dict(e_vd_med_lux=med, d_t=target_lux / med if med > 0 else math.inf)
