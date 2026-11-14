"""Irradiance: IRR-01 to IRR-10 of specs/physics/01-solar-pv.md.

Required path: GHI, DNI and DHI from the weather file; IRR-04 incidence, then
IRR-05 beam, IRR-08 Perez sky diffuse and IRR-09 ground reflected, summed by IRR-10.
Fallback: IRR-02 (Erbs) splits GHI when the file has no DNI and DHI. IRR-06 and
IRR-07 are simpler sky models kept for shading and as cross-checks.

All functions take scalars or NumPy arrays. Irradiance W/m2, angles degrees.
"""
from __future__ import annotations

import numpy as np

#: Solar constant, W/m2 (pvlib default; IRR-01). Moves to backend/config.py under A0/A29.
SOLAR_CONSTANT_W_M2 = 1366.1
#: Default ground albedo (IRR-09). Moves to backend/config.py under A0/A29.
DEFAULT_ALBEDO = 0.2

#: IRR-08 coefficients, Perez et al. 1990 Table 6 (irradiance set, "allsitescomposite1990"),
#: rows are the eight sky-clearness bins; columns f11 f12 f13 f21 f22 f23.
PEREZ_COEFFICIENTS = np.array([
    [-0.008, 0.588, -0.062, -0.060, 0.072, -0.022],
    [0.130, 0.683, -0.151, -0.019, 0.066, -0.029],
    [0.330, 0.487, -0.221, 0.055, -0.064, -0.026],
    [0.568, 0.187, -0.295, 0.109, -0.152, -0.014],
    [0.873, -0.392, -0.362, 0.226, -0.462, 0.001],
    [1.132, -1.237, -0.412, 0.288, -0.823, 0.056],
    [1.060, -1.600, -0.359, 0.264, -1.127, 0.131],
    [0.678, -0.327, -0.250, 0.156, -1.377, 0.251],
])
#: Lower edges of bins 2..8 of the sky clearness eps (bin 1 is everything below 1.065).
PEREZ_EPS_EDGES = np.array([1.065, 1.230, 1.500, 1.950, 2.800, 4.500, 6.200])


def _cosd(x):
    return np.cos(np.radians(x))


def _sind(x):
    return np.sin(np.radians(x))


# ---------- IRR-01 ----------

def extraterrestrial_normal_irradiance(day_of_year, solar_constant: float = SOLAR_CONSTANT_W_M2):
    """IRR-01. E0n in W/m2 (Spencer). `day_of_year` is the UTC day."""
    g = 2.0 * np.pi * (np.asarray(day_of_year, dtype=float) - 1.0) / 365.0
    return solar_constant * (1.00011 + 0.034221 * np.cos(g) + 0.00128 * np.sin(g)
                             + 0.000719 * np.cos(2 * g) + 0.000077 * np.sin(2 * g))


# ---------- IRR-02 (fallback) ----------

def clearness_index(ghi, zenith_deg, e0n, min_cos_zenith: float = 0.065, max_kt: float = 1.0):
    """IRR-02, first line. kt = GHI / (E0n max(cos(theta_z), 0.065)), limited to [0, 1]."""
    kt = np.asarray(ghi, dtype=float) / (e0n * np.maximum(_cosd(zenith_deg), min_cos_zenith))
    return np.minimum(np.maximum(kt, 0.0), max_kt)


def decompose_ghi_erbs(ghi_w_m2, zenith_deg, day_of_year, max_zenith_deg: float = 87.0):
    """IRR-02. Erbs split of GHI into (dni, dhi, kt). Fallback only; the result carries a warning."""
    ghi = np.asarray(ghi_w_m2, dtype=float)
    kt = clearness_index(ghi, zenith_deg, extraterrestrial_normal_irradiance(day_of_year))
    df = 1.0 - 0.09 * kt
    df = np.where((kt > 0.22) & (kt <= 0.80),
                  0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4, df)
    df = np.where(kt > 0.80, 0.165, df)
    dhi = df * ghi
    with np.errstate(divide="ignore", invalid="ignore"):
        dni = (ghi - dhi) / _cosd(zenith_deg)
    bad = (np.asarray(zenith_deg) > max_zenith_deg) | (ghi < 0) | (dni < 0) | ~np.isfinite(dni)
    return np.where(bad, 0.0, dni), np.where(bad, ghi, dhi), kt


# ---------- IRR-03 ----------

def relative_air_mass(apparent_zenith_deg):
    """IRR-03. Kasten (1966) relative air mass; NaN for zenith above 90 degrees."""
    z = np.asarray(apparent_zenith_deg, dtype=float)
    z = np.where(z > 90.0, np.nan, z)
    return 1.0 / (_cosd(z) + 0.15 * (93.885 - z) ** (-1.253))


# ---------- IRR-04 to IRR-07 ----------

def cos_incidence(tilt_deg, surface_azimuth_deg, apparent_zenith_deg, solar_azimuth_deg):
    """IRR-04, cosine form, not clipped (negative: sun behind the plane)."""
    c = (_cosd(tilt_deg) * _cosd(apparent_zenith_deg)
         + _sind(tilt_deg) * _sind(apparent_zenith_deg)
         * _cosd(np.asarray(solar_azimuth_deg) - np.asarray(surface_azimuth_deg)))
    return np.clip(c, -1.0, 1.0)


def incidence_angle(tilt_deg, surface_azimuth_deg, apparent_zenith_deg, solar_azimuth_deg):
    """IRR-04. Angle of incidence on a tilted plane, degrees."""
    return np.degrees(np.arccos(cos_incidence(tilt_deg, surface_azimuth_deg,
                                              apparent_zenith_deg, solar_azimuth_deg)))


def poa_beam(dni_w_m2, incidence_deg):
    """IRR-05. Eb = DNI max(cos(theta), 0)."""
    return np.asarray(dni_w_m2, dtype=float) * np.maximum(_cosd(incidence_deg), 0.0)


def sky_diffuse_isotropic(dhi_w_m2, tilt_deg):
    """IRR-06. Ed,iso = DHI (1 + cos(beta)) / 2."""
    return np.asarray(dhi_w_m2, dtype=float) * (1.0 + _cosd(tilt_deg)) / 2.0


def sky_diffuse_haydavies(dhi, dni, e0n, tilt_deg, incidence_deg, zenith_deg):
    """IRR-07. Hay and Davies sky diffuse, W/m2."""
    ai = np.asarray(dni, dtype=float) / e0n
    rb = np.maximum(_cosd(incidence_deg), 0.0) / np.maximum(_cosd(zenith_deg), 0.01745)
    dhi = np.asarray(dhi, dtype=float)
    iso = np.maximum(dhi * (1.0 - ai) * (1.0 + _cosd(tilt_deg)) / 2.0, 0.0)
    circ = np.maximum(dhi * ai * rb, 0.0)
    return iso + circ


# ---------- IRR-08 ----------

def perez_bin(eps):
    """IRR-08. Index 0..7 of the sky-clearness bin ('from' inclusive, 'to' exclusive)."""
    return np.searchsorted(PEREZ_EPS_EDGES, np.asarray(eps, dtype=float), side="right")


def sky_diffuse_perez(dhi, dni, e0n, tilt_deg, incidence_deg, apparent_zenith_deg, air_mass) -> dict:
    """IRR-08. Perez 1990 sky diffuse and its three parts, W/m2.

    Returns {sky_diffuse, isotropic, circumsolar, horizon}. Zero where DHI <= 0,
    the apparent zenith is 90 or more, or the air mass is undefined, and every part
    is zero wherever the total is clipped to zero.
    """
    dhi = np.asarray(dhi, dtype=float)
    dni = np.asarray(dni, dtype=float)
    zen = np.asarray(apparent_zenith_deg, dtype=float)
    am = np.asarray(air_mass, dtype=float)
    valid = (dhi > 0) & (zen < 90.0) & np.isfinite(am)
    dhi_s = np.where(valid, dhi, 1.0)                    # avoid 0/0 where the result is zeroed
    am_s = np.where(valid, am, 1.0)

    z = np.radians(zen)
    kappa = 1.041
    eps = ((dhi_s + dni) / dhi_s + kappa * z**3) / (1.0 + kappa * z**3)
    delta = dhi_s * am_s / e0n
    f = PEREZ_COEFFICIENTS[perez_bin(eps)]
    F1 = np.maximum(0.0, f[..., 0] + f[..., 1] * delta + f[..., 2] * z)
    F2 = f[..., 3] + f[..., 4] * delta + f[..., 5] * z

    a = np.maximum(0.0, _cosd(incidence_deg))
    b = np.maximum(_cosd(85.0), _cosd(zen))
    iso = dhi * (1.0 - F1) * (1.0 + _cosd(tilt_deg)) / 2.0
    circ = dhi * F1 * a / b
    hor = dhi * F2 * _sind(tilt_deg)
    total = np.maximum(0.0, iso + circ + hor)
    keep = valid & (total > 0)
    return {
        "sky_diffuse": np.where(keep, total, 0.0),
        "isotropic": np.where(keep, iso, 0.0),
        "circumsolar": np.where(keep, circ, 0.0),
        "horizon": np.where(keep, hor, 0.0),
    }


# ---------- IRR-09, IRR-10 ----------

def poa_ground_reflected(ghi_w_m2, albedo, tilt_deg):
    """IRR-09. Eg = GHI rho (1 - cos(beta)) / 2."""
    return np.asarray(ghi_w_m2, dtype=float) * np.asarray(albedo, dtype=float) * (1.0 - _cosd(tilt_deg)) / 2.0


def plane_of_array_irradiance(ghi, dni, dhi, day_of_year, apparent_zenith_deg, solar_azimuth_deg,
                              tilt_deg, surface_azimuth_deg, albedo=DEFAULT_ALBEDO,
                              e0n=None, air_mass=None) -> dict:
    """IRR-10. Plane-of-array irradiance on a tilted plane with the Perez sky (IRR-08).

    Returns {poa_global, poa_beam, poa_sky_diffuse, poa_sky_isotropic,
    poa_sky_circumsolar, poa_sky_horizon, poa_ground, incidence_deg} in W/m2 (and
    degrees). Every component is 0 when the apparent zenith is 90 or more (section 0.1).
    `e0n` and `air_mass` may be passed precomputed; otherwise IRR-01 and IRR-03.
    """
    zen = np.asarray(apparent_zenith_deg, dtype=float)
    if e0n is None:
        e0n = extraterrestrial_normal_irradiance(day_of_year)
    if air_mass is None:
        air_mass = relative_air_mass(zen)
    aoi = incidence_angle(tilt_deg, surface_azimuth_deg, zen, solar_azimuth_deg)
    day = zen < 90.0
    eb = np.where(day, poa_beam(dni, aoi), 0.0)
    sky = sky_diffuse_perez(dhi, dni, e0n, tilt_deg, aoi, zen, air_mass)
    eg = np.where(day, poa_ground_reflected(ghi, albedo, tilt_deg), 0.0)
    return {
        "poa_global": eb + sky["sky_diffuse"] + eg,
        "poa_beam": eb,
        "poa_sky_diffuse": sky["sky_diffuse"],
        "poa_sky_isotropic": sky["isotropic"],
        "poa_sky_circumsolar": sky["circumsolar"],
        "poa_sky_horizon": sky["horizon"],
        "poa_ground": eg,
        "incidence_deg": aoi,
    }
