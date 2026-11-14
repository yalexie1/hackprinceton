"""Solar position: SOL-01 to SOL-07 of specs/physics/01-solar-pv.md.

SOL-01 (NREL SPA, `spa.py`) is the production path. SOL-02 to SOL-05 are the
closed-form Spencer/NOAA algorithm, kept as a cross-check only (error up to about one
sun diameter); they must not replace SOL-01. Angles in degrees, azimuth clockwise from
true north, times timezone-aware.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .spa import spa

_EPOCH = pd.Timestamp(0, tz="UTC")
_HOUR = pd.Timedelta(hours=1)
_HALF_HOUR = pd.Timedelta(minutes=30)


def _as_index(times) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(times if not isinstance(times, pd.Timestamp) else [times])
    if idx.tz is None:
        raise ValueError("times must be timezone-aware")
    return idx


def _unix_seconds(idx: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray((idx.tz_convert("UTC") - _EPOCH) / pd.Timedelta(seconds=1), dtype=float)


def pressure_from_elevation(elevation_m: float) -> float:
    """Site pressure in Pa from elevation (the formula of pvlib `atmosphere.alt2pres`, SOL-01 inputs)."""
    return 100.0 * ((44331.514 - elevation_m) / 11880.516) ** (1.0 / 0.1902632)


# ---------- SOL-01 ----------

def solar_position(times, lat_deg: float, lon_deg: float, elevation_m: float = 0.0,
                   pressure_pa: float | None = None, temperature_c: float = 12.0) -> pd.DataFrame:
    """SOL-01. NREL SPA sun position at each timestamp.

    Returns a DataFrame indexed by `times` with `zenith_deg` (true),
    `apparent_zenith_deg`, `elevation_deg` (true), `apparent_elevation_deg`,
    `azimuth_deg` and `equation_of_time_min`. Downstream code uses the apparent
    zenith (SOL-01, "Which zenith to use downstream").
    """
    idx = _as_index(times)
    if pressure_pa is None:
        pressure_pa = pressure_from_elevation(elevation_m)
    r = spa(_unix_seconds(idx), lat_deg, lon_deg, elevation_m, pressure_pa / 100.0, temperature_c)
    return pd.DataFrame({
        "zenith_deg": r["zenith"],
        "apparent_zenith_deg": r["apparent_zenith"],
        "elevation_deg": r["elevation"],
        "apparent_elevation_deg": r["apparent_elevation"],
        "azimuth_deg": r["azimuth"],
        "equation_of_time_min": r["equation_of_time"],
    }, index=idx)


# ---------- SOL-02 to SOL-05 (cross-check only) ----------

def _day_angle(day_of_year):
    return 2.0 * np.pi * (np.asarray(day_of_year, dtype=float) - 1.0) / 365.0


def equation_of_time_spencer(day_of_year):
    """SOL-02. Equation of time in minutes (Spencer series, pvlib constant 0.0000075)."""
    g = _day_angle(day_of_year)
    return 229.18 * (0.0000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                     - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))


def declination_spencer(day_of_year):
    """SOL-03. Solar declination in degrees (Spencer series)."""
    g = _day_angle(day_of_year)
    d = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g)
         - 0.006758 * np.cos(2 * g) + 0.000907 * np.sin(2 * g)
         - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    return np.degrees(d)


def hour_angle(times, lon_deg: float, equation_of_time_min):
    """SOL-04. Hour angle in degrees, negative before solar noon.

    omega = 15 (hours_utc - 12) + lon + E / 4, algebraically equal to
    tst / 4 - 180 with tst = 60 hr + mn + sc / 60 + E + 4 lon - 60 tz.
    """
    idx = _as_index(times)
    utc = idx.tz_convert("UTC")
    hours_utc = (utc - utc.normalize()) / _HOUR
    return 15.0 * (np.asarray(hours_utc, dtype=float) - 12.0) + lon_deg + np.asarray(equation_of_time_min) / 4.0


def zenith_azimuth_from_angles(lat_deg: float, declination_deg, hour_angle_deg):
    """SOL-05 core. True zenith and azimuth (deg) from latitude, declination and hour angle."""
    phi, dl, om = np.radians(lat_deg), np.radians(declination_deg), np.radians(hour_angle_deg)
    cos_z = np.sin(phi) * np.sin(dl) + np.cos(phi) * np.cos(dl) * np.cos(om)
    zenith = np.degrees(np.arccos(np.clip(cos_z, -1.0, 1.0)))
    east = -np.cos(dl) * np.sin(om)
    north = np.sin(dl) * np.cos(phi) - np.cos(dl) * np.sin(phi) * np.cos(om)
    azimuth = np.degrees(np.arctan2(east, north)) % 360.0
    azimuth = np.where(np.isclose(zenith, 0.0, atol=1e-12), 180.0, azimuth)
    return zenith, azimuth


def solar_position_simple(times, lat_deg: float, lon_deg: float, tz_hours: float):
    """SOL-05. Closed-form (zenith_deg, azimuth_deg). Test helper, not used in production.

    The day of year is taken from local standard time at offset `tz_hours`.
    """
    idx = _as_index(times)
    local = idx.tz_convert(dt.timezone(dt.timedelta(hours=tz_hours)))
    n = np.asarray(local.day_of_year, dtype=float)
    E = equation_of_time_spencer(n)
    omega = hour_angle(idx, lon_deg, E)
    return zenith_azimuth_from_angles(lat_deg, declination_spencer(n), omega)


# ---------- SOL-06 ----------

def sun_vector(apparent_zenith_deg, azimuth_deg):
    """SOL-06. Unit vector toward the sun in ENU: (east, north, up)."""
    z, a = np.radians(apparent_zenith_deg), np.radians(azimuth_deg)
    return np.sin(z) * np.sin(a), np.sin(z) * np.cos(a), np.cos(z)


# ---------- SOL-07 ----------

_CONVENTION_START = {
    "hour_end": -_HOUR,          # stamp t covers (t - 1 h, t]
    "hour_start": pd.Timedelta(0),  # stamp t covers [t, t + 1 h)
    "hour_centre": -_HALF_HOUR,  # stamp t is the middle of its hour
}


def interval_bounds(stamps, convention: str = "hour_end"):
    """Start and end of the hour each stamp stands for, under a `weather_time_convention`."""
    if convention not in _CONVENTION_START:
        raise ValueError(f"unknown weather_time_convention {convention!r}")
    idx = _as_index(stamps)
    start = idx + _CONVENTION_START[convention]
    return start, start + _HOUR


def interval_midpoints(stamps, lat_deg: float, lon_deg: float, *, convention: str = "hour_end",
                       elevation_m: float = 0.0, pressure_pa: float | None = None,
                       temperature_c: float = 12.0, iterations: int = 24) -> pd.DatetimeIndex:
    """SOL-07. The instant at which to evaluate the sun for each hourly value.

    The middle of the hour, except in the hour that contains sunrise or sunset, where
    it is the middle of the part of the hour with the sun up. "Up" means apparent
    zenith below 90 degrees, the same threshold as the night rule of section 0.1.
    The crossing is found by bisection on SOL-01 (24 halvings of an hour: 0.2 ms).
    """
    start, end = interval_bounds(stamps, convention)
    mid = start + _HALF_HOUR
    kw = dict(elevation_m=elevation_m, pressure_pa=pressure_pa, temperature_c=temperature_c)

    def up(times):
        return solar_position(times, lat_deg, lon_deg, **kw)["apparent_zenith_deg"].to_numpy() < 90.0

    up_start, up_end = up(start), up(end)
    edge = np.flatnonzero(up_start != up_end)
    if edge.size == 0:
        return mid

    lo = _unix_seconds(start[edge])     # side with the same state as the start
    hi = _unix_seconds(end[edge])
    lo_up = up_start[edge]
    for _ in range(iterations):
        m = 0.5 * (lo + hi)
        m_up = up(pd.to_datetime(m, unit="s", utc=True))
        same = m_up == lo_up
        lo = np.where(same, m, lo)
        hi = np.where(same, hi, m)
    crossing = 0.5 * (lo + hi)
    s_sec, e_sec = _unix_seconds(start[edge]), _unix_seconds(end[edge])
    # sunrise (down at start): middle of [crossing, end]; sunset: middle of [start, crossing]
    new = np.where(lo_up, 0.5 * (s_sec + crossing), 0.5 * (crossing + e_sec))

    out = _unix_seconds(mid)
    out[edge] = new
    return pd.to_datetime(out, unit="s", utc=True).tz_convert(mid.tz)
