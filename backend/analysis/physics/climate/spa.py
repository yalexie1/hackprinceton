"""NREL Solar Position Algorithm in NumPy (SOL-01).

Reda, I. and Andreas, A., "Solar Position Algorithm for Solar Radiation
Applications", NREL/TP-560-34302, revised January 2008, section 3, steps 3.1 to 3.16,
and appendix A.6 (equation of time). Step and equation numbers below are the
report's. Vectorised over time; latitude, longitude and elevation are scalars.

`spa(...)` is the raw algorithm on Unix seconds (UTC). The public wrapper, which
takes timezone-aware timestamps, is `solar_position.solar_position`.
"""
from __future__ import annotations

import numpy as np

from . import _spa_tables as T

#: Delta T = TT - UT in seconds. pvlib's default; a 10 s error moves the sun by about
#: 0.04 degrees (SOL-01 validity). Moves to backend/config.py under A0/A29.
DELTA_T_S = 67.0
#: Sun radius plus the refraction at the horizon, degrees (SPA eq. 42 switch).
ATMOS_REFRACT_DEG = 0.5667
SUN_RADIUS_DEG = 0.26667


def _periodic(tables, jme):
    """Sum over each table of A cos(B + C * JME), combined as a polynomial in JME (eq. 9-11)."""
    jme = np.asarray(jme, dtype=float)
    total = np.zeros_like(jme)
    for power, tab in enumerate(tables):
        s = (tab[:, 0][:, None] * np.cos(tab[:, 1][:, None] + tab[:, 2][:, None] * jme[None, :])).sum(axis=0)
        total = total + s * jme**power
    return total / 1e8


def spa(unixtime, lat_deg: float, lon_deg: float, elevation_m: float = 0.0,
        pressure_mbar: float = 1013.25, temperature_c: float = 12.0,
        delta_t_s: float = DELTA_T_S, atmos_refract_deg: float = ATMOS_REFRACT_DEG) -> dict:
    """Topocentric sun position for Unix times in seconds (UTC).

    Returns a dict of arrays, angles in degrees:
    `zenith` (true, no refraction), `apparent_zenith`, `elevation`,
    `apparent_elevation`, `azimuth` (from north, clockwise), `equation_of_time`
    (minutes).
    """
    t = np.atleast_1d(np.asarray(unixtime, dtype=float))

    # 3.1 Julian day, century, ephemeris millennium (eq. 4-8); Unix epoch = JD 2440587.5
    jd = t / 86400.0 + 2440587.5
    jde = jd + delta_t_s / 86400.0
    jc = (jd - 2451545.0) / 36525.0
    jce = (jde - 2451545.0) / 36525.0
    jme = jce / 10.0

    # 3.2 Earth heliocentric longitude, latitude, radius vector (eq. 9-13)
    L = np.rad2deg(_periodic(T.L_TERMS, jme)) % 360.0
    B = np.rad2deg(_periodic(T.B_TERMS, jme))
    R = _periodic(T.R_TERMS, jme)

    # 3.3 Geocentric longitude and latitude (eq. 13-14)
    theta = (L + 180.0) % 360.0
    beta = -B

    # 3.4 Nutation in longitude and obliquity (eq. 15-23)
    x0 = 297.85036 + 445267.111480 * jce - 0.0019142 * jce**2 + jce**3 / 189474.0
    x1 = 357.52772 + 35999.050340 * jce - 0.0001603 * jce**2 - jce**3 / 300000.0
    x2 = 134.96298 + 477198.867398 * jce + 0.0086972 * jce**2 + jce**3 / 56250.0
    x3 = 93.27191 + 483202.017538 * jce - 0.0036825 * jce**2 + jce**3 / 327270.0
    x4 = 125.04452 - 1934.136261 * jce + 0.0020708 * jce**2 + jce**3 / 450000.0
    X = np.vstack([x0, x1, x2, x3, x4])                        # (5, n)
    arg = np.radians(T.NUTATION_YTERM.astype(float) @ X)        # (63, n)
    a, b, c, d = (T.NUTATION_ABCD[:, k][:, None] for k in range(4))
    delta_psi = ((a + b * jce) * np.sin(arg)).sum(axis=0) / 36e6
    delta_eps = ((c + d * jce) * np.cos(arg)).sum(axis=0) / 36e6

    # 3.5 True obliquity of the ecliptic (eq. 24-25)
    U = jme / 10.0
    eps0 = (84381.448 - 4680.93 * U - 1.55 * U**2 + 1999.25 * U**3 - 51.38 * U**4
            - 249.67 * U**5 - 39.05 * U**6 + 7.12 * U**7 + 27.87 * U**8
            + 5.79 * U**9 + 2.45 * U**10)
    eps = eps0 / 3600.0 + delta_eps

    # 3.6-3.7 Aberration and apparent sun longitude (eq. 26-27)
    lamd = theta + delta_psi + (-20.4898 / (3600.0 * R))

    # 3.8 Apparent sidereal time at Greenwich (eq. 28-29)
    nu0 = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
           + 0.000387933 * jc**2 - jc**3 / 38710000.0) % 360.0
    nu = nu0 + delta_psi * np.cos(np.radians(eps))

    # 3.9-3.10 Geocentric right ascension and declination (eq. 30-31)
    lam_r, eps_r, beta_r = np.radians(lamd), np.radians(eps), np.radians(beta)
    alpha = np.degrees(np.arctan2(np.sin(lam_r) * np.cos(eps_r) - np.tan(beta_r) * np.sin(eps_r),
                                  np.cos(lam_r))) % 360.0
    delta = np.degrees(np.arcsin(np.sin(beta_r) * np.cos(eps_r)
                                 + np.cos(beta_r) * np.sin(eps_r) * np.sin(lam_r)))

    # 3.11 Observer local hour angle, westward from south (eq. 32)
    H = (nu + lon_deg - alpha) % 360.0

    # 3.12 Topocentric right ascension and declination (eq. 33-38)
    xi = np.radians(8.794 / (3600.0 * R))
    lat_r = np.radians(lat_deg)
    u = np.arctan(0.99664719 * np.tan(lat_r))
    x = np.cos(u) + elevation_m / 6378140.0 * np.cos(lat_r)
    y = 0.99664719 * np.sin(u) + elevation_m / 6378140.0 * np.sin(lat_r)
    H_r, delta_r = np.radians(H), np.radians(delta)
    d_alpha = np.degrees(np.arctan2(-x * np.sin(xi) * np.sin(H_r),
                                    np.cos(delta_r) - x * np.sin(xi) * np.cos(H_r)))
    delta_p = np.degrees(np.arctan2((np.sin(delta_r) - y * np.sin(xi)) * np.cos(np.radians(d_alpha)),
                                    np.cos(delta_r) - x * np.sin(xi) * np.cos(H_r)))

    # 3.13 Topocentric local hour angle (eq. 39)
    H_p = H - d_alpha

    # 3.14 Topocentric elevation, refraction, zenith (eq. 41-44)
    dp_r, Hp_r = np.radians(delta_p), np.radians(H_p)
    e0 = np.degrees(np.arcsin(np.sin(lat_r) * np.sin(dp_r) + np.cos(lat_r) * np.cos(dp_r) * np.cos(Hp_r)))
    sun_up = e0 >= -1.0 * (SUN_RADIUS_DEG + atmos_refract_deg)
    with np.errstate(divide="ignore", invalid="ignore"):
        de = ((pressure_mbar / 1010.0) * (283.0 / (273.0 + temperature_c))
              * 1.02 / (60.0 * np.tan(np.radians(e0 + 10.3 / (e0 + 5.11)))))
    de = np.where(sun_up, de, 0.0)
    e = e0 + de

    # 3.15 Topocentric azimuth (eq. 45-46)
    gamma = np.degrees(np.arctan2(np.sin(Hp_r),
                                  np.cos(Hp_r) * np.sin(lat_r) - np.tan(dp_r) * np.cos(lat_r))) % 360.0
    azimuth = (gamma + 180.0) % 360.0

    # A.6 Equation of time (eq. A1-A2), minutes, limited to +/-20
    M = (280.4664567 + 360007.6982779 * jme + 0.03032028 * jme**2
         + jme**3 / 49931.0 - jme**4 / 15300.0 - jme**5 / 2000000.0)
    E = ((M - 0.0057183 - alpha + delta_psi * np.cos(eps_r)) % 360.0) * 4.0
    E = np.where(E > 20.0, E - 1440.0, np.where(E < -20.0, E + 1440.0, E))

    return {
        "zenith": 90.0 - e0,
        "apparent_zenith": 90.0 - e,
        "elevation": e0,
        "apparent_elevation": e,
        "azimuth": azimuth,
        "equation_of_time": E,
    }
