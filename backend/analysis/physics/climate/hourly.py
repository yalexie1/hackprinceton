"""Hourly climate inputs for S5 and solar (A1): sun, irradiance on a plane, temperature.

`load_climate(site)` reads the weather file once and evaluates the sun at the SOL-07
instant of every hour. `plane_irradiance(hours, tilt, azimuth)` transposes onto one
plane with the Perez sky (IRR-10). `hourly_climate(site, tilt, azimuth)` does both.
Pure: reads one file, no network, no writes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.schema import ClimateSite

from .irradiance import (DEFAULT_ALBEDO, decompose_ghi_erbs, extraterrestrial_normal_irradiance,
                         plane_of_array_irradiance, relative_air_mass)
from .solar_position import interval_midpoints, pressure_from_elevation, solar_position
from .weather import Weather, read_site_weather

#: Zenith limit for the closure check GHI = DNI cos(theta_z) + DHI (report only).
CLOSURE_MAX_ZENITH_DEG = 85.0


@dataclass(frozen=True)
class ClimateHours:
    """Weather plus the sun for each hour. All arrays have one value per weather row."""
    weather: Weather
    eval_times: pd.DatetimeIndex        # SOL-07 instant per hour
    apparent_zenith_deg: np.ndarray
    zenith_deg: np.ndarray
    sun_azimuth_deg: np.ndarray
    sun_elevation_deg: np.ndarray       # apparent (refraction-corrected)
    day_of_year_utc: np.ndarray
    e0n_w_m2: np.ndarray                # IRR-01
    air_mass: np.ndarray                # IRR-03, NaN with the sun down
    ghi_w_m2: np.ndarray
    dni_w_m2: np.ndarray
    dhi_w_m2: np.ndarray
    decomposed: bool                    # True when IRR-02 split GHI (fallback)
    closure: dict                       # GHI - (DNI cos z + DHI) on daytime hours, report only
    formula_ids: tuple[str, ...]
    warnings: tuple[str, ...] = field(default=())

    @property
    def temp_c(self) -> np.ndarray:
        return self.weather.temp_c

    @property
    def stamps(self) -> pd.DatetimeIndex:
        return self.weather.stamps


def load_climate(site: ClimateSite, *, elevation_m: float = 0.0, root=None,
                 weather: Weather | None = None) -> ClimateHours:
    """Read the site's weather and compute the sun for every hour.

    `elevation_m`: `ClimateSite` carries no elevation, so the caller passes one if
    known (e.g. Vexcel ground elevation); 0 m by default. It enters only the parallax
    and the refraction pressure (SOL-01), both negligible at building scale.
    Refraction uses the annual mean air temperature of the file (SOL-01 inputs).
    """
    w = weather if weather is not None else read_site_weather(site, root)
    warnings = list(w.warnings)
    temp_mean = float(np.mean(w.temp_c))
    kw = dict(elevation_m=elevation_m, pressure_pa=pressure_from_elevation(elevation_m),
              temperature_c=temp_mean)

    eval_times = interval_midpoints(w.stamps, site.lat, site.lon, convention=w.convention, **kw)
    sun = solar_position(eval_times, site.lat, site.lon, **kw)
    app_zen = sun["apparent_zenith_deg"].to_numpy()
    doy = np.asarray(eval_times.tz_convert("UTC").day_of_year, dtype=float)
    e0n = extraterrestrial_normal_irradiance(doy)
    am = relative_air_mass(app_zen)

    ghi = np.maximum(w.ghi_w_m2, 0.0)
    formula_ids = ["SOL-01", "SOL-07", "IRR-01", "IRR-03"]
    if w.has_direct_diffuse:
        dni, dhi, decomposed = np.maximum(w.dni_w_m2, 0.0), np.maximum(w.dhi_w_m2, 0.0), False
    else:
        dni, dhi, _ = decompose_ghi_erbs(ghi, app_zen, doy)
        decomposed = True
        formula_ids.append("IRR-02")
        warnings.append("weather file has no DNI and DHI; GHI split by Erbs (IRR-02), a fallback "
                        "with wide hour-to-hour scatter")

    night = app_zen >= 90.0
    lost = night & (ghi > 0)
    if lost.any():
        warnings.append(f"{int(lost.sum())} hours report GHI > 0 with the sun down at the SOL-07 "
                        f"instant ({float(ghi[lost].sum()) / 1000:.3f} kWh/m2 in total); set to 0")
    ghi, dni, dhi = (np.where(night, 0.0, x) for x in (ghi, dni, dhi))

    day = (app_zen < CLOSURE_MAX_ZENITH_DEG) & (ghi > 0)
    resid = ghi[day] - (dni[day] * np.cos(np.radians(app_zen[day])) + dhi[day])
    closure = {
        "hours": int(day.sum()),
        "mean_w_m2": float(resid.mean()) if resid.size else 0.0,
        "mean_abs_w_m2": float(np.abs(resid).mean()) if resid.size else 0.0,
        "max_abs_w_m2": float(np.abs(resid).max()) if resid.size else 0.0,
    }

    return ClimateHours(
        weather=w, eval_times=eval_times, apparent_zenith_deg=app_zen,
        zenith_deg=sun["zenith_deg"].to_numpy(), sun_azimuth_deg=sun["azimuth_deg"].to_numpy(),
        sun_elevation_deg=sun["apparent_elevation_deg"].to_numpy(), day_of_year_utc=doy,
        e0n_w_m2=e0n, air_mass=am, ghi_w_m2=ghi, dni_w_m2=dni, dhi_w_m2=dhi,
        decomposed=decomposed, closure=closure, formula_ids=tuple(formula_ids),
        warnings=tuple(warnings),
    )


def plane_irradiance(hours: ClimateHours, tilt_deg: float, surface_azimuth_deg: float,
                     albedo: float | None = None) -> dict:
    """IRR-04 to IRR-10 on one plane for every hour. Arrays in W/m2 (incidence in degrees).

    Albedo: the argument if given, else the file's hourly `albedo` column, else 0.2 (IRR-09).
    """
    if albedo is None:
        albedo = hours.weather.albedo if hours.weather.albedo is not None else DEFAULT_ALBEDO
    return plane_of_array_irradiance(
        hours.ghi_w_m2, hours.dni_w_m2, hours.dhi_w_m2, hours.day_of_year_utc,
        hours.apparent_zenith_deg, hours.sun_azimuth_deg, tilt_deg, surface_azimuth_deg,
        albedo=albedo, e0n=hours.e0n_w_m2, air_mass=hours.air_mass)


PLANE_FORMULA_IDS = ("IRR-04", "IRR-05", "IRR-08", "IRR-09", "IRR-10")


def hourly_climate(site: ClimateSite, tilt_deg: float, surface_azimuth_deg: float, *,
                   elevation_m: float = 0.0, albedo: float | None = None, root=None,
                   hours: ClimateHours | None = None) -> dict:
    """A1 output: hourly sun azimuth and elevation, irradiance on the plane, outdoor temperature.

    Returns a dict of NumPy arrays (one value per weather hour) plus `stamps`,
    `formula_ids` and `warnings`. Pass `hours` to reuse one `load_climate` result
    across many planes.
    """
    h = hours if hours is not None else load_climate(site, elevation_m=elevation_m, root=root)
    poa = plane_irradiance(h, tilt_deg, surface_azimuth_deg, albedo)
    return {
        "stamps": h.stamps,
        "sun_azimuth_deg": h.sun_azimuth_deg,
        "sun_elevation_deg": h.sun_elevation_deg,
        "apparent_zenith_deg": h.apparent_zenith_deg,
        "temp_c": h.temp_c,
        "ghi_w_m2": h.ghi_w_m2,
        "dni_w_m2": h.dni_w_m2,
        "dhi_w_m2": h.dhi_w_m2,
        **poa,
        "formula_ids": h.formula_ids + PLANE_FORMULA_IDS,
        "warnings": h.warnings,
    }
