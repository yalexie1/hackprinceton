"""PV-10: the modelled PV yield against PVGIS (physics 01 section 3).

PVGIS is fetched by the Data lane at one fixed orientation (``backend/data_layer/external.py``
``fetch_pvgis``: 1 kWp, tilt 20, aspect 0 = south, system loss 14 percent, mounting "building").
The design may face elsewhere, so PVGIS is first moved to the design's orientation with a
transposition ratio and to the design's loss accounting, then compared.

Numpy only (pvlib is a test reference here, as in the rest of the lane). No network.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

import numpy as np

# What fetch_pvgis asks PVGIS for (backend/data_layer/external.py, read 2026-11-14).
PVGIS_TILT_DEG = 20.0
PVGIS_AZIMUTH_DEG = 180.0       # PVGIS "aspect" 0 = south; contract azimuth 180
PVGIS_LOSS_PERCENT = 14.0       # PVGIS "loss": cables, inverter, soiling, ... (PVGIS user manual 4.1)

# Loss accounting of the design (physics 01 PV-04, PV-05).
PVWATTS_LOSSES_NO_SHADING = 11.4182     # PV-04 defaults with shading 0
PVWATTS_LOSSES_DEFAULT = 14.0757        # PV-04 defaults with the 3 percent shading row
INVERTER_EFFICIENCY = 0.96              # PV-05 eta_nom; PVGIS's 14 percent already includes the inverter

# Tolerance (PV-10) [J].
Z_TWO_SIDED_95 = 1.96
MODEL_DIFFERENCE = 0.05          # [J] thermal model ("building" vs close roof mount), IAM, spectral, inverter curve
CLEAR_SKY_EXTRA = 0.06           # [J] added when no weather file is given (measured up to 5.8 %, PV-10)
DEFAULT_SD_FRACTION = 0.04       # [J] when PVGIS gave no SD_y: the larger of the two real-or-example values, rounded up
ALBEDO = 0.2


@dataclass(frozen=True)
class Plane:
    tilt_deg: float
    azimuth_deg: float               # contract convention, 0 = north, clockwise
    kw_dc: float = 1.0


@dataclass(frozen=True)
class PvCrossCheck:
    status: str                      # "checked" or "not_checked"
    reason: str = ""
    modelled_kwh_per_kw: Optional[float] = None
    modelled_unshaded_kwh_per_kw: Optional[float] = None
    pvgis_kwh_per_kw: Optional[float] = None          # as fetched, at the PVGIS orientation
    transposition_ratio: Optional[float] = None       # design plane(s) / PVGIS plane, annual irradiation
    transposition_source: str = ""                    # "weather file" or "clear-sky year"
    loss_ratio: Optional[float] = None                # design system factor / PVGIS system factor
    expected_kwh_per_kw: Optional[float] = None       # PVGIS moved to the design
    deviation: Optional[float] = None                 # modelled_unshaded / expected - 1
    tolerance: Optional[float] = None
    within: Optional[bool] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ sun and plane

def _sun(doy: np.ndarray, solar_hour_lst: np.ndarray, lat: float, lon: float, utc_offset_h: float):
    """Spencer (1971) declination and equation of time, as in physics 01 SOL-02 to SOL-05."""
    g = 2.0 * math.pi * (doy - 1) / 365.0
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    eot_min = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                        - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    solar_time = solar_hour_lst + (4.0 * (lon - 15.0 * utc_offset_h) + eot_min) / 60.0
    omega = np.radians(15.0 * (solar_time - 12.0))
    phi = math.radians(lat)
    cos_z = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(omega)
    e0n = 1367.0 * (1.0 + 0.033 * np.cos(2.0 * math.pi * doy / 365.0))
    return decl, omega, cos_z, e0n


def _cos_incidence(decl, omega, lat: float, tilt: float, azimuth: float):
    """Duffie and Beckman eq. 1.6.2; surface azimuth from south, west positive."""
    phi, b, gam = math.radians(lat), math.radians(tilt), math.radians(azimuth - 180.0)
    return (np.sin(decl) * math.sin(phi) * math.cos(b)
            - np.sin(decl) * math.cos(phi) * math.sin(b) * math.cos(gam)
            + np.cos(decl) * math.cos(phi) * math.cos(b) * np.cos(omega)
            + np.cos(decl) * math.sin(phi) * math.sin(b) * math.cos(gam) * np.cos(omega)
            + np.cos(decl) * math.sin(b) * math.sin(gam) * np.sin(omega))


def plane_irradiation(weather: dict, lat: float, lon: float, tilt: float, azimuth: float) -> float:
    """Annual plane-of-array irradiation, kWh/m2, Hay and Davies sky diffuse (physics 01 IRR-07)."""
    decl, omega, cos_z, e0n = _sun(weather["doy"], weather["hour"], lat, lon, weather["utc_offset_h"])
    up = cos_z > 0.0
    cos_t = np.clip(_cos_incidence(decl, omega, lat, tilt, azimuth), 0.0, None)
    ghi, dni, dhi = weather["ghi"], weather["dni"], weather["dhi"]
    a_i = np.clip(dni / e0n, 0.0, 1.0)
    rb = cos_t / np.maximum(cos_z, math.cos(math.radians(87.0)))
    b = math.radians(tilt)
    poa = (dni * cos_t + dhi * ((1.0 - a_i) * (1.0 + math.cos(b)) / 2.0 + a_i * rb)
           + ghi * ALBEDO * (1.0 - math.cos(b)) / 2.0)
    return float(np.sum(np.where(up, poa, 0.0)) / 1000.0)


def clear_sky_year(lat: float, lon: float, utc_offset_h: float) -> dict:
    """365 days at the hour midpoints: Haurwitz GHI, Erbs split (physics 01 IRR-02)."""
    doy = np.repeat(np.arange(1, 366, dtype=float), 24)
    hour = np.tile(np.arange(24, dtype=float) + 0.5, 365)
    _, _, cos_z, e0n = _sun(doy, hour, lat, lon, utc_offset_h)
    cz = np.clip(cos_z, 0.0, None)
    ghi = np.where(cz > 0, 1098.0 * cz * np.exp(-0.057 / np.maximum(cz, 1e-6)), 0.0)
    kt = np.where(cz > 0.0175, ghi / (e0n * np.maximum(cz, 1e-6)), 0.0)
    kt = np.clip(kt, 0.0, 1.0)
    df = np.where(kt <= 0.22, 1.0 - 0.09 * kt,
                  np.where(kt <= 0.80, 0.9511 - 0.1604 * kt + 4.388 * kt ** 2 - 16.638 * kt ** 3
                           + 12.336 * kt ** 4, 0.165))
    dhi = ghi * df
    dni = np.where(cz > 0.0175, (ghi - dhi) / np.maximum(cz, 1e-6), 0.0)
    return {"doy": doy, "hour": hour, "ghi": ghi, "dni": dni, "dhi": dhi, "utc_offset_h": utc_offset_h}


def standard_utc_offset_hours(timezone: str, year: int = 2024) -> float:
    zone = ZoneInfo(timezone)
    probe = dt.datetime(year, 1, 15, 12, tzinfo=zone)
    return ((zone.utcoffset(probe) or dt.timedelta(0)) - (zone.dst(probe) or dt.timedelta(0))).total_seconds() / 3600.0


def read_weather_csv(path: str | Path, timezone: str, time_convention: Optional[str] = "hour_end") -> dict:
    """The cached weather file of data spec 5.1a: ``time_local`` in local standard time, GHI,
    DNI, DHI in W/m2. Returns arrays at the hour midpoints (physics 01 SOL-07)."""
    shift = {"hour_end": -0.5, "hour_start": 0.5, "hour_centre": 0.0, "hour_center": 0.0}.get(
        time_convention or "hour_end", -0.5)
    doy, hour, ghi, dni, dhi = [], [], [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            stamp = dt.datetime.fromisoformat(row["time_local"]).replace(tzinfo=None)
            if stamp.month == 2 and stamp.day == 29:
                continue
            h = stamp.hour + stamp.minute / 60.0 + shift
            d = stamp.timetuple().tm_yday
            if stamp.month > 2 and _leap(stamp.year):
                d -= 1
            doy.append(d)
            hour.append(h)
            ghi.append(float(row["ghi_w_m2"] or 0.0))
            dni.append(float(row.get("dni_w_m2") or 0.0))
            dhi.append(float(row.get("dhi_w_m2") or 0.0))
    if not doy or not any(dni) or not any(dhi):
        raise ValueError("weather file has no DNI and DHI columns to transpose with")
    return {"doy": np.array(doy, float), "hour": np.array(hour), "ghi": np.array(ghi), "dni": np.array(dni),
            "dhi": np.array(dhi), "utc_offset_h": standard_utc_offset_hours(timezone)}


def _leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


# ------------------------------------------------------------------ the check

def pv_tolerance(sd_fraction: Optional[float], clear_sky: bool) -> float:
    """PV-10 tolerance: one weather year against a multi-year mean (z * sigma_w) combined in
    quadrature with the model difference, plus the clear-sky allowance when it applies."""
    s = sd_fraction if sd_fraction and sd_fraction > 0 else DEFAULT_SD_FRACTION
    tol = math.hypot(Z_TWO_SIDED_95 * s, MODEL_DIFFERENCE)
    return tol + (CLEAR_SKY_EXTRA if clear_sky else 0.0)


def system_factor(losses_percent: Optional[float]) -> float:
    """Design energy after system losses and the inverter, per unit of DC energy before them,
    with shading taken out (it is compared separately, PVGIS has no near shading)."""
    lp = PVWATTS_LOSSES_NO_SHADING if losses_percent is None else losses_percent
    return (1.0 - lp / 100.0) * INVERTER_EFFICIENCY


def cross_check_pv(annual_kwh: Optional[float], system_kw_dc: Optional[float],
                   planes: Sequence[Plane], pvgis_kwh_per_kw: Optional[float],
                   pvgis_sd_fraction: Optional[float], lat: Optional[float], lon: Optional[float], *,
                   losses_percent: Optional[float] = None, shading_fraction: float = 0.0,
                   weather: Optional[dict] = None, timezone: Optional[str] = None,
                   pvgis_tilt_deg: float = PVGIS_TILT_DEG, pvgis_azimuth_deg: float = PVGIS_AZIMUTH_DEG,
                   pvgis_loss_percent: float = PVGIS_LOSS_PERCENT) -> PvCrossCheck:
    """PV-10. ``annual_kwh`` and ``system_kw_dc`` are the design's (``SolarDesign``).

    ``losses_percent`` is ``SolarDesign.losses_percent`` *without* shading: pass the PV-04 total
    and ``shading_fraction`` separately (``pv_inputs`` does this). ``shading_fraction`` is the
    energy-weighted shading loss of the panels, which is taken out of the modelled yield before
    comparing because PVGIS has none. ``weather`` is from ``read_weather_csv``; without it the
    transposition ratio uses a clear-sky year and the tolerance widens.
    """
    missing = []
    if not annual_kwh or not system_kw_dc or system_kw_dc <= 0:
        missing.append("no PV design")
    if not pvgis_kwh_per_kw or pvgis_kwh_per_kw <= 0:
        missing.append("no PVGIS yield for the site")
    if lat is None or lon is None:
        missing.append("no site coordinates")
    if not planes:
        missing.append("no plane orientation")
    if missing:
        reason = "; ".join(missing)
        return PvCrossCheck(status="not_checked", reason=reason,
                            warnings=[f"The solar yield was not cross-checked against PVGIS: {reason}."])

    modelled = annual_kwh / system_kw_dc
    unshaded = modelled / (1.0 - shading_fraction) if 0.0 <= shading_fraction < 1.0 else modelled
    clear = weather is None
    if clear:
        offset = standard_utc_offset_hours(timezone) if timezone else round(lon / 15.0)
        weather = clear_sky_year(lat, lon, offset)
    ref = plane_irradiation(weather, lat, lon, pvgis_tilt_deg, pvgis_azimuth_deg)
    kw = sum(p.kw_dc for p in planes)
    design = sum(p.kw_dc * plane_irradiation(weather, lat, lon, p.tilt_deg, p.azimuth_deg) for p in planes) / kw
    ratio = design / ref
    loss_ratio = system_factor(losses_percent) / (1.0 - pvgis_loss_percent / 100.0)
    expected = pvgis_kwh_per_kw * ratio * loss_ratio
    deviation = unshaded / expected - 1.0
    tol = pv_tolerance(pvgis_sd_fraction, clear)
    within = abs(deviation) <= tol
    warnings = []
    if clear:
        warnings.append("PVGIS was moved to the design's orientation with a clear-sky year (no weather "
                        f"file), so the cross-check tolerance is widened by {CLEAR_SKY_EXTRA:.0%}.")
    if not within:
        side = "above" if deviation > 0 else "below"
        warnings.append(
            f"Modelled solar yield of {unshaded:.0f} kWh/kW a year (before shading) is {abs(deviation):.0%} "
            f"{side} PVGIS for this site and orientation ({expected:.0f} kWh/kW, from PVGIS's "
            f"{pvgis_kwh_per_kw:.0f} at {pvgis_tilt_deg:g} degrees facing south, transposition ratio {ratio:.3f}, "
            f"loss ratio {loss_ratio:.3f}); the tolerance is {tol:.0%}. Check the weather file, the plane "
            "tilt and azimuth, and the losses before relying on the solar figures.")
    return PvCrossCheck(
        status="checked", modelled_kwh_per_kw=round(modelled, 1), modelled_unshaded_kwh_per_kw=round(unshaded, 1),
        pvgis_kwh_per_kw=pvgis_kwh_per_kw, transposition_ratio=round(ratio, 4),
        transposition_source="clear-sky year" if clear else "weather file", loss_ratio=round(loss_ratio, 4),
        expected_kwh_per_kw=round(expected, 1), deviation=round(deviation, 4), tolerance=round(tol, 4),
        within=within, warnings=warnings)
