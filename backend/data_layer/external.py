"""Weather and tariff (package D9) — the two required `PropertyBundle` fields that
no sponsor API supplies.

Every rule here is a verified finding from `specs/data-integration.md` section 5:

- **The hourly source is a TMYx typical year** from the nearest representative
  station (#295, `tmyx.py`, data spec 5.1f). The Open-Meteo 2024 reanalysis it
  replaces ran about 3 °F cold at the golden house against the Downtown USC station
  in the same year, which inflated heating by half.
- **Open-Meteo archive is the fallback**: keyless, covers both cities, and returns
  GHI, DNI and DHI already separated. A `fallback` record says why it was used.
- **`weather_time_convention` is `hour_end`** for both. For Open-Meteo, verified
  twice: the 24 hourly `shortwave_radiation` values for one day sum to 29.923 MJ/m2
  against a daily `shortwave_radiation_sum` of 29.92, a ratio of 1.0001, so they are
  full-hour means and not instantaneous samples; and at sunrise 04:42 the stamps read
  0.0 at 04:00, 2.0 at 05:00 and 85.0 at 06:00, which only fits the stamp labelling
  the hour that *ends* at it. Reading a stamp as the following hour shifts every
  solar calculation by an hour, and nothing downstream would error. For TMYx, the
  EPW convention, with the irradiance checked and realigned (`tmyx.py`).
- **An Open-Meteo file is one real calendar year, not a TMY**, so its
  `weather_source` names the exact year.
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

from . import cache, tmyx

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
    """Where the hourly CSV lives, as the string `ClimateSite.weather_path` carries.

    Routed through D4's cache root so `DATA_LAYER_CACHE_DIR` actually redirects it -
    the hard-coded `data/cache/...` meant a temporary cache still had 8,760 rows
    written into the real one. `cache.relative` keeps the value repo-relative in the
    default case, so the contract field is unchanged, and `get_asset` resolves an
    absolute path too, with its containment check following the same root.
    """
    return cache.relative(cache.cache_root() / sid / "weather" / "typical_year_hourly.csv")


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


def _pvgis_elevation(payload: Optional[dict]) -> Optional[float]:
    """The site elevation PVGIS reports from its DEM, which the TMYx station rule uses
    to keep a basin site off a valley station behind a ridge."""
    elev = (((payload or {}).get("inputs") or {}).get("location") or {}).get("elevation")
    return float(elev) if isinstance(elev, (int, float)) and not isinstance(elev, bool) else None


def get_climate_site(
    sid: str, lat: float, lon: float, year: int, *,
    climate_zone: Optional[str] = None,
    get: Optional[Getter] = None,
    get_bytes: Optional[tmyx.BytesGetter] = None,
    write: bool = True,
    typical_year: bool = True,
) -> tuple[ClimateSite, list[FetchRecord]]:
    """`ClimateSite` plus provenance. Writes the hourly CSV into the cache.

    **TMYx first** (#295): the typical year of the nearest representative station,
    see `tmyx.py`. **Open-Meteo archive `year` is the fallback** when no station
    qualifies, the download fails or the file does not verify, and a `fallback`
    record says why. `weather_source` always names which one was used.

    An injected `get` without `get_bytes` means the caller is supplying Open-Meteo and
    PVGIS only, so no TMYx download is attempted: the lane's rule is that an injected
    transport puts the caller in control of every byte, and the suite makes no
    network call.
    """
    notes: list[FetchRecord] = []
    rel = weather_path(sid)
    target = Path(rel) if Path(rel).is_absolute() else _ROOT / rel

    # PVGIS first: the cross-check, and the DEM elevation the station rule uses.
    annual = sd = None
    pvgis_payload = None
    try:
        pvgis_payload = fetch_pvgis(lat, lon, get=get)
        annual, sd = _pvgis_annual_and_sd(pvgis_payload)
        notes.append(FetchRecord(layer="weather", what="pvgis/PVcalc",
                                 status="ok" if annual else "missing",
                                 detail="annual cross-check, PVGIS-ERA5 (~30 km reanalysis)"))
    except Exception as exc:                       # a cross-check must never be fatal
        notes.append(FetchRecord(layer="weather", what="pvgis/PVcalc", status="error",
                                 detail=str(exc)[:200]))

    why_not = None
    if not typical_year:
        why_not = "typical year not requested"
    elif get is not None and get_bytes is None:
        why_not = "a transport was injected for Open-Meteo and PVGIS only, so TMYx was not tried"
    else:
        try:
            tmy = tmyx.typical_year(sid, lat, lon, site_elevation_m=_pvgis_elevation(pvgis_payload),
                                    get_bytes=get_bytes)
        except tmyx.Unavailable as exc:
            why_not = str(exc)
        else:
            if write:
                cache.atomic_write_path(target, tmy.csv_text.encode())
            notes.append(FetchRecord(layer="weather", what="onebuilding/tmyx", status="ok",
                                     detail=tmy.detail))
            return ClimateSite(
                lat=lat, lon=lon,
                timezone=tmy.timezone,
                climate_zone=climate_zone,
                weather_path=rel,
                weather_source=tmy.source,
                weather_time_convention=tmyx.TIME_CONVENTION,
                pvgis_annual_kwh_per_kw=annual,
                pvgis_sd_fraction=sd,
            ), notes

    if typical_year:
        notes.append(FetchRecord(layer="weather", what="onebuilding/tmyx", status="fallback",
                                 detail=f"{why_not}; Open-Meteo archive {year} used instead"))

    payload = fetch_hourly(lat, lon, year, get=get)
    rows = len((payload.get("hourly") or {}).get("time") or [])
    if write:
        # Atomic: a plain `write_text` interrupted part way leaves 8,760 rows of
        # half a CSV that the next run happily reads as a complete year.
        cache.atomic_write_path(target, hourly_csv(payload).encode())
    short = rows < 8760
    notes.append(FetchRecord(
        layer="weather", what="open-meteo/archive",
        status="fallback" if (short or typical_year) else "ok",
        detail=f"{rows} hourly rows for {year}" + ("; short year" if short else "")
               + (f"; fallback for the TMYx typical year ({why_not})" if typical_year else ""),
    ))

    return ClimateSite(
        lat=lat, lon=lon,
        timezone=payload.get("timezone") or "UTC",
        climate_zone=climate_zone,
        weather_path=rel,
        weather_source=(f"Open-Meteo archive, calendar year {year} (one real year, not a TMY; "
                        f"fallback: {why_not})" if typical_year else
                        f"Open-Meteo archive, calendar year {year} (one real year, not a TMY)"),
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


# ---------- gas (D15) ----------

EIA_GAS = "https://api.eia.gov/v2/natural-gas/pri/sum/data/"

#: EIA's process codes for the delivered gas price. Discovered from the route's own
#: `facet/process` listing rather than guessed.
GAS_PROCESS = {"RES": "PRS", "COM": "PCS"}      # Residential / Commercial consumers
GAS_AREA = {"CA": "SCA", "TX": "STX"}

#: **Annual**, not monthly, and deliberately. Gas prices swing hard with the winter
#: heating season, so one month is a poor proxy for an annual energy model in a way
#: that the electricity price is not. The monthly route also times out far more often.
GAS_FREQUENCY = "annual"

#: 1 therm = 29.3071070172 kWh, so 1 MMBtu = 10 therms = 293.071070172 kWh. This is
#: physics 04 TAR-05's constant, restated here rather than imported: the analysis lane
#: imports this lane, never the reverse.
KWH_PER_MMBTU = 293.071070172

#: **The unit trap.** EIA prices gas in **dollars per thousand cubic feet**, not per
#: therm, so physics 04 TAR-04's `usd_per_therm / 29.3071` is the wrong conversion to
#: apply to this number - it would overstate the price by a factor of about ten.
#: Volume becomes energy through the heat content of gas delivered to consumers, about
#: 1,037 Btu per cubic foot (EIA's published average), hence 1.037 MMBtu per MCF.
#:
#: That factor carries roughly ±0.5 % of uncertainty, since the heat content varies
#: year to year and by region between about 1,030 and 1,040 Btu/cf. It is far below
#: the uncertainty already in using a **state average** instead of the building's own
#: tariff, which is why the state average is labelled a fallback.
MMBTU_PER_MCF = 1.037


def usd_per_mcf_to_usd_per_kwh(price: float) -> float:
    """EIA's `$/MCF` to the contract's `gas_usd_per_kwh` (higher heating value)."""
    return price / (MMBTU_PER_MCF * KWH_PER_MMBTU)


#: The four delivered gas prices this project needs, in EIA's own `$/MCF`, with the
#: series and the date they were read. **Committed on purpose.**
#:
#: The live route is slow and erratic: measured 1 s, 14 s, 41 s and 66 s on the four
#: combinations, with 504s in between. Waiting on it took a cold bundle assembly from
#: 2.5 s to **44-76 s**, which is not a demo path. These are public EIA figures (not
#: sponsor data, so committing them is fine), they change once a year, and a table
#: beats a timeout that silently leaves the field unknown.
#:
#: The live lookup still runs first when `GAS_REFRESH` is set, so the table can be
#: refreshed rather than drifting. Either way the figure is a **state average** and is
#: labelled `fallback`; the detail says which route produced it.
GAS_DEFAULTS: dict[tuple[str, str], tuple[float, str, str]] = {
    ("CA", "RES"): (22.01, "2025", "N3010CA3"),
    ("CA", "COM"): (16.56, "2025", "N3020CA3"),
    ("TX", "RES"): (19.42, "2025", "N3010TX3"),
    ("TX", "COM"): (10.98, "2025", "N3020TX3"),
}

#: Set to `1` to try EIA live before the table. Off by default so a bundle never waits
#: on a route that has taken over a minute.
GAS_REFRESH_ENV = "EIA_GAS_REFRESH"

#: Short on purpose. If EIA has not answered in this long, the table is better than
#: both waiting and giving up.
GAS_TIMEOUT_S = 15.0


def _gas_from_table(state: str, sector: str) -> tuple[Optional[float], Optional[str], Optional[str]]:
    entry = GAS_DEFAULTS.get((state.upper(), sector.upper()))
    if entry is None:
        return None, None, None
    price, period, series = entry
    return usd_per_mcf_to_usd_per_kwh(price), period, f"{price} $/MCF, EIA {series}, table"


def _gas_get(url: str, params: dict) -> dict:
    """Like `_default_get` but with `GAS_TIMEOUT_S`, so one slow route cannot hold up
    a bundle that is otherwise two and a half seconds."""
    import httpx

    resp = httpx.get(url, params=params, timeout=GAS_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


def _eia_gas_usd_per_kwh(
    state: str, sector: str, *, get: Optional[Getter] = None
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """`(usd_per_kwh, period, raw_label)` for the state's delivered gas price.

    The committed table answers immediately. A live fetch is tried first only when
    `EIA_GAS_REFRESH=1`, or when a caller injects a transport - which is what the
    tests do, so they still exercise the real parsing and the unit guard.
    """
    if get is None and os.environ.get(GAS_REFRESH_ENV) != "1":
        return _gas_from_table(state, sector)

    key = os.environ.get("EIA_API_KEY")
    area, process = GAS_AREA.get(state.upper()), GAS_PROCESS.get(sector.upper())
    if not key or not area or not process:
        return _gas_from_table(state, sector)

    params = {
        "api_key": key, "frequency": GAS_FREQUENCY, "data[0]": "value",
        "facets[duoarea][]": area, "facets[process][]": process,
        "sort[0][column]": "period", "sort[0][direction]": "desc", "length": 1,
    }
    try:
        payload, _ = cache.cached_json(
            "eia-gas", f"{state.upper()}-{sector.upper()}",
            lambda: (get or _gas_get)(EIA_GAS, params),
            {"frequency": GAS_FREQUENCY, "process": process},
            use_cache=get is None,
        )
    except Exception:
        # A gas price is an improvement on the bundle, never a precondition for it.
        return _gas_from_table(state, sector)

    rows = ((payload or {}).get("response") or {}).get("data") or []
    if not rows:
        return _gas_from_table(state, sector)
    row = rows[0]
    # **Guard the unit, do not assume it.** The whole conversion hangs on the price
    # being per thousand cubic feet; a per-therm or per-MMBtu series would be out by a
    # factor of ten or a hundred and nothing downstream would notice. This is the same
    # lesson as D9, where an offline fixture used a float and kept the suite green
    # against a shape the real API never sends.
    units = str(row.get("units") or "")
    if "MCF" not in units.upper():
        return None, None, f"unexpected units {units!r}"

    price = _as_number(row.get("value"))      # EIA sends numbers as strings
    if price is None:
        return None, None, None
    return (
        usd_per_mcf_to_usd_per_kwh(price),
        str(row.get("period") or ""),
        f"{price} {row.get('units') or '$/MCF'}",
    )


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
    notes = [FetchRecord(layer="tariff", what="eia/retail-sales", status="fallback", detail=label)]

    # D15. Without this the field stays None, and `physics/systems/baseline.py` reads
    # a missing gas price as **electric** heating and hot water (`:149`, `:216`) and
    # prices any gas at zero (`:252`), so a 1920s Los Angeles house came out
    # all-electric on every live bundle. A missing price is "unknown", not "no gas".
    gas, gas_period, raw = _eia_gas_usd_per_kwh(state, sector, get=get)
    if gas is not None:
        gas_label = (f"EIA state average delivered gas price, {state} {sector}, {gas_period} "
                     f"({raw} at {MMBTU_PER_MCF} MMBtu/MCF, +/-0.5% on the heat content)")
        notes.append(FetchRecord(layer="tariff", what="eia/natural-gas-price",
                                 status="fallback", detail=gas_label))
        label = f"{label}; {gas_label}"
    else:
        notes.append(FetchRecord(
            layer="tariff", what="eia/natural-gas-price", status="missing",
            detail=("no delivered gas price for that state and sector, so gas_usd_per_kwh is "
                    "unknown - which is not the same as the site having no gas"),
        ))

    return Tariff(
        utility=utility or f"{state} state average ({sector})",
        electricity_usd_per_kwh=round(price, 6),
        gas_usd_per_kwh=round(gas, 6) if gas is not None else None,
        export_regime=EXPORT_REGIME.get(state),
        source=label,
        retrieved=period or "",
    ), notes
