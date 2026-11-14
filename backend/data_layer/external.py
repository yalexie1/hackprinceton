"""Weather and tariff (package D9) — the two required `PropertyBundle` fields that
no sponsor API supplies.

Every rule here is a verified finding from `specs/data-integration.md` section 5:

- **Open-Meteo archive** is the hourly source: keyless, covers both cities, and
  returns GHI, DNI and DHI already separated, which makes an irradiance
  *decomposition* step optional and leaves only the transposition to plane-of-array.
- **`weather_time_convention` is `hour_end`.** Verified twice: the 24 hourly
  `shortwave_radiation` values for one day sum to 29.923 MJ/m2 against a daily
  `shortwave_radiation_sum` of 29.92, a ratio of 1.0001, so they are full-hour means
  and not instantaneous samples; and at sunrise 04:42 the stamps read 0.0 at 04:00,
  2.0 at 05:00 and 85.0 at 06:00, which only fits the stamp labelling the hour that
  *ends* at it. Reading a stamp as the following hour shifts every solar calculation
  by an hour, and nothing downstream would error.
- **What this writes is one real calendar year, not a TMY.** A true typical year
  needs multi-year statistics that are out of scope, so `weather_source` names the
  exact year and the inter-annual spread comes from PVGIS `SD_y` rather than being
  invented.
- **PVGIS** gives the annual cross-check and that spread. Only `PVGIS-ERA5` exists
  for the United States, and it is a ~30 km reanalysis, so it is a sanity band and
  never the hourly source. **PVWatts and NSRDB are unusable**: both
  `developer.nrel.gov` and `nsrdb.nrel.gov` fail DNS resolution from here.
- **Tariff**: the **EIA state average for all three golden properties**, decided by
  the lead on 2026-11-14 (`specs/data-integration.md` 5.1c). URDB gives the real
  utility where one exists but has **zero** rates at the Houston office, ERCOT being
  a deregulated retail market with no single regulated tariff, and
  `electricity_usd_per_kwh` is one marginal price, so a time-of-use schedule would
  have to be flattened regardless. The figure is always labelled a `fallback` - it is
  a state monthly average, not that building's contract.
"""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Callable, Optional

from backend.schema import ClimateSite, FetchRecord, Tariff

from . import cache

_ROOT = Path(__file__).resolve().parents[2]

OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
PVGIS = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
EIA = "https://api.eia.gov/v2/electricity/retail-sales/data/"
URDB = "https://api.openei.org/utility_rates"

#: What an hourly stamp means. Proven, not assumed - see the module docstring.
TIME_CONVENTION = "hour_end"

HOURLY_VARS = (
    "temperature_2m", "relative_humidity_2m", "shortwave_radiation",
    "direct_normal_irradiance", "diffuse_radiation", "wind_speed_10m",
)
CSV_COLUMNS = ("time_local", "temp_c", "rh_pct", "ghi_w_m2", "dni_w_m2", "dhi_w_m2", "wind_m_s")

KMH_TO_MS = 1000.0 / 3600.0
CENTS_TO_USD = 0.01

#: `(url, params)` -> parsed JSON
Getter = Callable[[str, dict], dict]


def _default_get(url: str, params: dict) -> dict:
    import httpx  # lazy so offline tests need no transport

    resp = httpx.get(url, params=params, timeout=120.0)
    resp.raise_for_status()
    return resp.json()


# ---------- weather ----------

def weather_path(sid: str) -> str:
    return f"data/cache/{sid}/weather/typical_year_hourly.csv"


def hourly_csv(payload: dict) -> str:
    """Open-Meteo hourly block as the lane's CSV. Wind is converted km/h -> m/s."""
    h = payload.get("hourly") or {}
    times = h.get("time") or []
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for i, stamp in enumerate(times):
        def at(name):
            seq = h.get(name) or []
            return seq[i] if i < len(seq) else None
        wind = at("wind_speed_10m")
        writer.writerow([
            stamp,
            at("temperature_2m"),
            at("relative_humidity_2m"),
            at("shortwave_radiation"),
            at("direct_normal_irradiance"),
            at("diffuse_radiation"),
            round(wind * KMH_TO_MS, 4) if isinstance(wind, (int, float)) else None,
        ])
    return buf.getvalue()


def fetch_hourly(lat: float, lon: float, year: int, *, get: Optional[Getter] = None,
                 refresh: bool = False) -> dict:
    """A year of hourly weather. Cached by D4 - it is 8,760 rows and the slowest call
    in the lane at 1.3 s - and the cache is bypassed when `get` is injected.

    The variable list is in the key: adding one must not serve the older response
    that lacks it.
    """
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": f"{year}-01-01", "end_date": f"{year}-12-31",
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "auto",
    }
    payload, _ = cache.cached_json(
        "open-meteo", f"{lat:.5f},{lon:.5f},{year}",
        lambda: (get or _default_get)(OPEN_METEO, params),
        {"hourly": params["hourly"]},
        use_cache=get is None, refresh=refresh,
    )
    return payload


def fetch_pvgis(lat: float, lon: float, *, tilt: float = 20.0, azimuth: float = 0.0,
                get: Optional[Getter] = None) -> dict:
    """Annual yield for 1 kWp with its inter-annual standard deviation.

    `raddatabase` is left to the service: only `PVGIS-ERA5` covers the United States,
    `PVGIS-NSRDB` is not a valid v5_3 value and `PVGIS-SARAH3` reports Los Angeles
    out of coverage.
    """
    params = {
        "lat": lat, "lon": lon, "peakpower": 1, "loss": 14,
        "angle": tilt, "aspect": azimuth, "mountingplace": "building",
        "outputformat": "json",
    }
    payload, _ = cache.cached_json(
        "pvgis", f"{lat:.5f},{lon:.5f}",
        lambda: (get or _default_get)(PVGIS, params),
        {"angle": tilt, "aspect": azimuth, "loss": 14},
        use_cache=get is None,
    )
    return payload


def _pvgis_annual_and_sd(payload: dict) -> tuple[Optional[float], Optional[float]]:
    fixed = (((payload or {}).get("outputs") or {}).get("totals") or {}).get("fixed") or {}
    e_y, sd_y = fixed.get("E_y"), fixed.get("SD_y")
    if not isinstance(e_y, (int, float)) or e_y <= 0:
        return None, None
    sd_fraction = sd_y / e_y if isinstance(sd_y, (int, float)) else None
    return float(e_y), sd_fraction


def get_climate_site(
    sid: str, lat: float, lon: float, year: int, *,
    climate_zone: Optional[str] = None,
    get: Optional[Getter] = None,
    write: bool = True,
) -> tuple[ClimateSite, list[FetchRecord]]:
    """`ClimateSite` plus provenance. Writes the hourly CSV into the cache.

    `year` is a real calendar year, named in `weather_source` so nobody mistakes the
    file for a typical meteorological year.
    """
    notes: list[FetchRecord] = []
    payload = fetch_hourly(lat, lon, year, get=get)
    rows = len((payload.get("hourly") or {}).get("time") or [])
    rel = weather_path(sid)
    if write:
        # Atomic: a plain `write_text` interrupted part way leaves 8,760 rows of
        # half a CSV that the next run happily reads as a complete year.
        cache.atomic_write_path(_ROOT / rel, hourly_csv(payload).encode())
    notes.append(FetchRecord(
        layer="weather", what="open-meteo/archive",
        status="ok" if rows >= 8760 else "fallback",
        detail=f"{rows} hourly rows for {year}" + ("" if rows >= 8760 else "; short year"),
    ))

    annual = sd = None
    try:
        annual, sd = _pvgis_annual_and_sd(fetch_pvgis(lat, lon, get=get))
        notes.append(FetchRecord(layer="weather", what="pvgis/PVcalc",
                                 status="ok" if annual else "missing",
                                 detail="annual cross-check, PVGIS-ERA5 (~30 km reanalysis)"))
    except Exception as exc:                       # a cross-check must never be fatal
        notes.append(FetchRecord(layer="weather", what="pvgis/PVcalc", status="error",
                                 detail=str(exc)[:200]))

    return ClimateSite(
        lat=lat, lon=lon,
        timezone=payload.get("timezone") or "UTC",
        climate_zone=climate_zone,
        weather_path=rel,
        weather_source=f"Open-Meteo archive, calendar year {year} (one real year, not a TMY)",
        weather_time_convention=TIME_CONVENTION,
        pvgis_annual_kwh_per_kw=annual,
        pvgis_sd_fraction=sd,
    ), notes


# ---------- tariff ----------

def _as_number(value) -> Optional[float]:
    """EIA returns numbers as JSON **strings**: `"price": "8.96"`.

    An `isinstance(value, (int, float))` guard silently rejects every real response,
    and a hand-written fixture using a number will not catch it.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _eia_price_usd_per_kwh(state: str, sector: str, *, get: Optional[Getter] = None
                           ) -> tuple[Optional[float], Optional[str]]:
    """Latest state monthly average retail price. EIA answers in cents per kWh."""
    key = os.environ.get("EIA_API_KEY")
    if not key:
        return None, None
    body = (get or _default_get)(EIA, {
        "api_key": key, "frequency": "monthly", "data[0]": "price",
        "facets[stateid][]": state, "facets[sectorid][]": sector,
        "sort[0][column]": "period", "sort[0][direction]": "desc", "length": 1,
    })
    rows = ((body or {}).get("response") or {}).get("data") or []
    if not rows:
        return None, None
    cents = _as_number(rows[0].get("price"))
    if cents is None:
        return None, None
    return cents * CENTS_TO_USD, rows[0].get("period")


#: Whether the state mandates a price for exported PV. The contract's own rule -
#: `Tariff.export_regime` is documented as "None where no export price is mandated
#: (Texas)" - so California is `net_metering` and ERCOT, which mandates no export
#: compensation at all, is `none`. Leaving the field unset was discarding something
#: the schema asked for, and the PV measure needs it to value exported generation.
EXPORT_REGIME: dict[str, str] = {"CA": "net_metering", "TX": "none"}


def get_tariff(
    state: str, sector: str, *, utility: Optional[str] = None,
    get: Optional[Getter] = None,
) -> tuple[Optional[Tariff], list[FetchRecord]]:
    """A `Tariff` from the EIA state average, always labelled as a fallback.

    `state` is `CA` or `TX`; `sector` is EIA's `RES` or `COM`.

    **This is a state monthly average, not the building's retail contract**, and as
    of the lead's decision of 2026-11-14 it is the source for **all three** golden
    properties, not only the Houston one (`specs/data-integration.md` 5.1c). URDB
    does return the real utility for Los Angeles (LADWP, `eiaid` 11208) but has
    **no tariff at all** at the Houston office - ERCOT is deregulated, so there is no
    single regulated schedule to look up - and `electricity_usd_per_kwh` is one
    marginal price, so a time-of-use schedule would have to be flattened anyway. The
    `fallback` status and the source string exist so no reader mistakes a state
    average for a looked-up rate.

    `utility` is passed in rather than inferred. Deriving it from the CoStar `City`
    field would repeat the mistake the PACE work caught, where `cityId` 5316
    "Houston" included a property outside the incorporated city: LADWP serves the
    city of Los Angeles and the surrounding unincorporated county is SCE, so the
    same trap applies. Absent a verified utility the field says what the number
    actually is.
    """
    price, period = _eia_price_usd_per_kwh(state, sector, get=get)
    if price is None:
        return None, [FetchRecord(layer="tariff", what="eia/retail-sales", status="missing",
                                  detail="no EIA_API_KEY, or no price for that state and sector")]
    label = f"EIA state average retail price, {state} {sector}, {period}"
    return Tariff(
        utility=utility or f"{state} state average ({sector})",
        electricity_usd_per_kwh=round(price, 6),
        export_regime=EXPORT_REGIME.get(state),
        source=label,
        retrieved=period or "",
    ), [FetchRecord(layer="tariff", what="eia/retail-sales", status="fallback", detail=label)]
