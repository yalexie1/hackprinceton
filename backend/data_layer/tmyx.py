"""Typical-year weather from the nearest representative station (issue #295).

`ClimateSite.weather_path` used to be one real year (2024) of the Open-Meteo archive,
a reanalysis on a coarse grid. At the golden house it ran about 3 °F colder than the
Downtown USC station in the *same* year (1,562 against 1,045 °F heating degree-days),
so the house model burnt about twice the gas of a typical Los Angeles home. A
consultant would use a typical-meteorological-year file from the nearest
representative weather station; this module does that, with Open-Meteo kept as the
fallback in `external.py`. The numbers behind every choice are in
`specs/data-integration.md` 5.1f.

**Source.** TMYx files from climate.onebuilding.org (Lawrie and Crawley): typical
months picked by the ISO 15927-4 method from NOAA ISD station observations, with solar
radiation from ERA5. EPW format, one per station and period.

**Station rule** (`choose_station`), from the onebuilding Region 4 USA index:

1. **A long, current record.** The station's full record covers at least
   `MIN_RECORD_YEARS` years and runs to `MIN_RECORD_END` or later. That keeps first-order
   airport stations and drops heliports and short secondary records: at the Houston
   office the nearest entry, Houston-Dunn heliport (7.8 km, 18 years, a rooftop pad
   at 69 m), is skipped for Hobby airport.
2. **Similar ground.** Where the site elevation is known (PVGIS reports its DEM value),
   the station is within `MAX_ELEVATION_DIFF_M`. This is what separates a basin site
   from a valley station behind a ridge (Burbank, 236 m, against the house at 102 m).
3. **Then the nearest**, if within `MAX_DISTANCE_KM`; otherwise there is no station and
   the caller falls back. The bundle's climate zone is deliberately **not** used: the
   county-level IECC zone 3B covers both the marine strip and the inland basin, and
   matching on it would send the Culver City office to Downtown USC, whose cooling
   degree-days are 77 % above Culver City's observed ones.
4. **The newest 15-year window** of that station (`TMYx.2011-2025`), else the
   full-record file. The newest window describes the climate the building will run
   in; the full record reaches back to the 1940s at some airports and runs 10-20 %
   more heating degree-days.

**Time.** EPW rows are hour-ending, local standard time, and temperatures are
read at the stamp, so `weather_time_convention` is `hour_end` and the stamps are written
on a nominal non-leap year whose 1 January falls on the weekday the file's `DATA
PERIODS` record names (a TMY mixes years, so there is no real one). **The solar columns
are checked, not trusted**: in the 2026 release the irradiance runs half an hour late
against that convention (clear-day fits against a clear-sky model put the centre of
an hour's value 60-65 minutes before its stamp instead of 30, at all eight stations
tested, while Open-Meteo's verified hour-ending file fits at 30-40). `solar_offset_hours`
measures the offset of every file, a half-hour one is realigned by averaging adjacent
hours, and anything else is refused, so the caller falls back.

**Licence.** The site states no open licence ("Copyright 2014-2026 Climate.OneBuilding.
All Rights Reserved") and asks to be cited as Lawrie, Linda K. and Drury B. Crawley,
2026, *Development of Global Typical Meteorological Years (TMYx)*. The files are
therefore downloaded into the git-ignored cache and never committed.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from backend.schema import FetchRecord

from . import cache

ONEBUILDING = "https://climate.onebuilding.org"
#: The Region 4 USA index: one placemark per station and period, with the URL, the
#: WMO number, the coordinates, the elevation, the time zone and the record length.
INDEX_URL = f"{ONEBUILDING}/sources/Region4_USA_TMYx_EPW_Processing_locations.kml"
#: Bumped when the index parser changes, so a cached parse is not reused.
#: 2 - the file is kept as a path under `ONEBUILDING`, not a URL: D4 scrubs every URL
#:     out of a cached payload, and version 1's cached index served `<url-not-cached>`.
INDEX_PARSER_VERSION = 2

MAX_DISTANCE_KM = 50.0
MIN_RECORD_YEARS = 25
MIN_RECORD_END = 2020
MAX_ELEVATION_DIFF_M = 100.0

#: The index is about 16 MB, so it gets longer than a JSON API call.
FETCH_TIMEOUT_S = 90.0

TIME_CONVENTION = "hour_end"
HOURS_PER_YEAR = 8760

#: Solar offsets the converter knows how to repair, in hours late against hour-ending.
#: 0 is a conforming file; 0.5 is what the 2026 ERA5-based release measures.
_OFFSET_TOLERANCE_H = 0.25

#: A non-leap year starting on each weekday, Monday = 0, for the nominal stamps.
NOMINAL_YEAR_BY_WEEKDAY = {0: 2018, 1: 2019, 2: 2014, 3: 2015, 4: 2021, 5: 2022, 6: 2017}
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

#: IANA zone from the file's standard offset. A file is stamped in its station's
#: standard time, and the A1 reader localises stamps with the standard offset of
#: `ClimateSite.timezone`, so the two must agree; deriving the zone from the file
#: guarantees it. Arizona keeps standard time all year, hence the state override.
_ZONE_BY_OFFSET = {-5.0: "America/New_York", -6.0: "America/Chicago",
                   -7.0: "America/Denver", -8.0: "America/Los_Angeles",
                   -9.0: "America/Anchorage", -10.0: "Pacific/Honolulu"}
_ZONE_BY_STATE = {"AZ": "America/Phoenix", "HI": "Pacific/Honolulu"}

#: EPW missing-value codes for the columns the lane writes.
_MISSING = {"temp_c": 99.9, "rh_pct": 999.0, "ghi_w_m2": 9999.0, "dni_w_m2": 9999.0,
            "dhi_w_m2": 9999.0, "wind_m_s": 999.0}
#: EPW data-row field positions (EnergyPlus Auxiliary Programs, "Weather Data Format").
_FIELD = {"month": 1, "day": 2, "hour": 3, "temp_c": 6, "rh_pct": 8,
          "ghi_w_m2": 13, "dni_w_m2": 14, "dhi_w_m2": 15, "wind_m_s": 21}

CSV_COLUMNS = ("time_local", "temp_c", "rh_pct", "ghi_w_m2", "dni_w_m2", "dhi_w_m2", "wind_m_s")

#: `url -> bytes`
BytesGetter = Callable[[str], bytes]


class Unavailable(RuntimeError):
    """No usable TMYx file for this site; the message says why, for the fallback record."""


def _default_get_bytes(url: str) -> bytes:
    import httpx  # lazy so offline tests need no transport

    resp = httpx.get(url, timeout=FETCH_TIMEOUT_S, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


# ---------- the station index ----------

_PLACEMARK = re.compile(r"<Placemark>(.*?)</Placemark>", re.S)
_TITLE = re.compile(r"<b>USA\s+([A-Z]{2})\s+(\S+?)\.(\d{6})\s+(TMYx(?:\.\d{4}-\d{4})?)</b>")
_RECORD = re.compile(r"#years=\[(\d+)\]\s*Period of Record=(\d{4})-(\d{4})")
_ELEV = re.compile(r"Elevation\s*<b>(-?[\d.]+)</b>")
_TZ = re.compile(r"GMT\s*<b>(-?[\d.]+)</b>")
_URL = re.compile(r"URL\s+https://climate\.onebuilding\.org/(\S+?\.zip)")
_COORDS = re.compile(r"<coordinates>\s*(-?[\d.]+),(-?[\d.]+)")


def parse_index(kml: str) -> list[dict]:
    """Every TMYx placemark as a flat dict. Placemarks without a URL (the region marker)
    or of another dataset are skipped rather than guessed at."""
    rows: list[dict] = []
    for body in _PLACEMARK.findall(kml):
        title, url, coords = _TITLE.search(body), _URL.search(body), _COORDS.search(body)
        if not (title and url and coords):
            continue
        record, elev, tz = _RECORD.search(body), _ELEV.search(body), _TZ.search(body)
        rows.append({
            "state": title.group(1), "name": title.group(2), "wmo": title.group(3),
            "variant": title.group(4), "path": url.group(1),
            "lon": float(coords.group(1)), "lat": float(coords.group(2)),
            "elevation_m": float(elev.group(1)) if elev else None,
            "tz_offset_h": float(tz.group(1)) if tz else None,
            "record_years": int(record.group(1)) if record else None,
            "record_start": int(record.group(2)) if record else None,
            "record_end": int(record.group(3)) if record else None,
        })
    return rows


def load_index(*, get_bytes: Optional[BytesGetter] = None, refresh: bool = False) -> list[dict]:
    """The parsed index, cached by D4 (the KML is about 16 MB; the parse is ~1 MB).
    An injected transport bypasses the cache, as everywhere in the lane."""
    def fetch():
        return parse_index((get_bytes or _default_get_bytes)(INDEX_URL).decode("utf-8", "replace"))

    rows, _ = cache.cached_json("onebuilding", "region4-usa-tmyx-index", fetch,
                                {"url": INDEX_URL, "parser": INDEX_PARSER_VERSION},
                                use_cache=get_bytes is None, refresh=refresh)
    return rows


def file_url(entry: dict) -> str:
    """The download URL. The index keeps a path because the cache refuses URLs."""
    return f"{ONEBUILDING}/{entry['path']}"


# ---------- choosing the station ----------

def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance on a 6,371 km sphere."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class Choice:
    station: dict            # the full-record entry: its record decides eligibility
    file: dict               # the entry actually downloaded (newest window, else full)
    distance_km: float
    skipped: tuple[str, ...]  # nearer stations passed over, and why


def _window_end(entry: dict) -> int:
    m = re.match(r"TMYx\.(\d{4})-(\d{4})$", entry["variant"])
    return int(m.group(2)) if m else -1


def choose_station(lat: float, lon: float, index: list[dict], *,
                   site_elevation_m: Optional[float] = None) -> Optional[Choice]:
    """The station rule in the module docstring. `None` when nothing qualifies within
    `MAX_DISTANCE_KM`."""
    by_wmo: dict[str, list[dict]] = {}
    for entry in index:
        by_wmo.setdefault(entry["wmo"], []).append(entry)

    candidates = []
    for entries in by_wmo.values():
        full = next((e for e in entries if e["variant"] == "TMYx"), None)
        ref = full or max(entries, key=lambda e: (e.get("record_years") or 0))
        d = distance_km(lat, lon, ref["lat"], ref["lon"])
        if d <= MAX_DISTANCE_KM:
            candidates.append((d, ref, entries))
    candidates.sort(key=lambda c: c[0])

    skipped: list[str] = []
    for d, ref, entries in candidates:
        label = f"{ref['name']} {ref['wmo']} ({d:.1f} km"
        years, end = ref.get("record_years") or 0, ref.get("record_end") or 0
        if years < MIN_RECORD_YEARS or end < MIN_RECORD_END:
            skipped.append(f"{label}, record {years} years to {end})")
            continue
        elev = ref.get("elevation_m")
        if (site_elevation_m is not None and elev is not None
                and abs(elev - site_elevation_m) > MAX_ELEVATION_DIFF_M):
            skipped.append(f"{label}, {elev:.0f} m against the site's {site_elevation_m:.0f} m)")
            continue
        windows = [e for e in entries if _window_end(e) > 0]
        chosen = max(windows, key=_window_end) if windows else ref
        return Choice(station=ref, file=chosen, distance_km=d, skipped=tuple(skipped))
    return None


# ---------- the EPW ----------

@dataclass(frozen=True)
class Epw:
    location: dict
    start_weekday: Optional[int]   # Monday = 0, from DATA PERIODS
    source_months: str             # "Jan=2022; Feb=2014; ..." from COMMENTS 1, if present
    month: np.ndarray
    day: np.ndarray
    hour: np.ndarray
    columns: dict                  # name -> float array with NaN for missing


def parse_epw(text: str) -> Epw:
    """Read an EPW. Raises `Unavailable` on anything that is not a full, clean year."""
    lines = text.splitlines()
    if len(lines) < 9 or not lines[0].startswith("LOCATION"):
        raise Unavailable("not an EPW file (no LOCATION header)")
    loc = lines[0].split(",")
    try:
        location = {"city": loc[1], "state": loc[2], "wmo": loc[5], "lat": float(loc[6]),
                    "lon": float(loc[7]), "tz_offset_h": float(loc[8]),
                    "elevation_m": float(loc[9])}
    except (IndexError, ValueError) as exc:
        raise Unavailable(f"unreadable EPW LOCATION header: {exc}") from exc

    start_weekday, source_months = None, ""
    for line in lines[1:8]:
        if line.startswith("DATA PERIODS"):
            parts = [p.strip().lower() for p in line.split(",")]
            if len(parts) > 4 and parts[4] in _WEEKDAYS:
                start_weekday = _WEEKDAYS.index(parts[4])
        if line.startswith("COMMENTS 1"):
            m = re.search(r"(Jan=\d{4}.*?Dec=\d{4})", line)
            source_months = m.group(1) if m else ""

    rows = [ln.split(",") for ln in lines[8:] if ln.strip()]
    if len(rows) != HOURS_PER_YEAR:
        raise Unavailable(f"EPW has {len(rows)} hourly rows, not {HOURS_PER_YEAR}")
    try:
        month = np.array([int(r[_FIELD["month"]]) for r in rows])
        day = np.array([int(r[_FIELD["day"]]) for r in rows])
        hour = np.array([int(r[_FIELD["hour"]]) for r in rows])
        columns = {}
        for name, missing in _MISSING.items():
            values = np.array([float(r[_FIELD[name]]) for r in rows])
            columns[name] = np.where(values >= missing, np.nan, values)
    except (IndexError, ValueError) as exc:
        raise Unavailable(f"unreadable EPW data row: {exc}") from exc

    if not (np.all((hour >= 1) & (hour <= 24)) and np.all(np.diff(hour)[hour[:-1] < 24] == 1)):
        raise Unavailable("EPW hours are not 1..24 in sequence")
    if bool(np.any((month == 2) & (day == 29))):
        raise Unavailable("EPW carries 29 February; a typical year should not")
    for name in ("temp_c", "ghi_w_m2"):
        gaps = int(np.isnan(columns[name]).sum())
        if gaps > HOURS_PER_YEAR * 0.02:
            raise Unavailable(f"EPW {name} has {gaps} missing hours")
    t = columns["temp_c"]
    if np.nanmin(t) < -60 or np.nanmax(t) > 60:
        raise Unavailable("EPW dry-bulb temperature outside -60..60 °C")
    g = columns["ghi_w_m2"]
    if np.nanmin(g) < 0 or np.nanmax(g) > 1500:
        raise Unavailable("EPW global horizontal irradiance outside 0..1500 W/m2")

    return Epw(location=location, start_weekday=start_weekday, source_months=source_months,
               month=month, day=day, hour=hour, columns=columns)


def solar_offset_hours(epw: Epw) -> float:
    """How late the irradiance runs against the hour-ending convention, in hours.

    Under hour-ending a value stamped `h` is the mean over `h-1..h`, centred at
    `h-0.5`. Weighting those centres by GHI over the year lands on mean solar noon,
    `12 - (lon - 15*tz)/15` in local standard time, up to the weather's own
    morning/afternoon asymmetry: Open-Meteo's verified hour-ending files measure
    +0.15 h in Los Angeles (morning marine layer) and +0.03 h in Houston. The TMYx 2026
    files measure +0.47 to +0.57 h.
    """
    g = np.nan_to_num(epw.columns["ghi_w_m2"])
    if g.sum() <= 0:
        raise Unavailable("EPW has no irradiance at all")
    centroid = float((g * (epw.hour - 0.5)).sum() / g.sum())
    lon, tz = epw.location["lon"], epw.location["tz_offset_h"]
    return centroid - (12.0 - (lon - 15.0 * tz) / 15.0)


def _realign_half_hour(values: np.ndarray) -> np.ndarray:
    """Values centred half an hour before hour-ending: the mean over `h-1..h` is the
    average of the value stamped `h` (centred `h-1`) and the one stamped `h+1`
    (centred `h`). Wraps at the year end, so the annual sum is preserved."""
    v = np.nan_to_num(values)
    return (v + np.roll(v, -1)) / 2.0


def realigned_solar(epw: Epw) -> tuple[dict, float, float]:
    """`(columns with solar realigned, measured offset, shift applied)`. Raises
    `Unavailable` for an offset this converter does not know how to repair."""
    offset = solar_offset_hours(epw)
    cols = dict(epw.columns)
    if abs(offset) < _OFFSET_TOLERANCE_H:
        return cols, offset, 0.0
    if abs(offset - 0.5) < _OFFSET_TOLERANCE_H:
        for name in ("ghi_w_m2", "dni_w_m2", "dhi_w_m2"):
            cols[name] = _realign_half_hour(cols[name])
        return cols, offset, 0.5
    raise Unavailable(f"EPW irradiance is {offset:+.2f} h off hour-ending; refused rather "
                      f"than guessed")


def nominal_year(epw: Epw) -> int:
    """A non-leap year whose 1 January is the weekday the file starts on (Sunday, as
    EnergyPlus defaults, when the file does not say)."""
    return NOMINAL_YEAR_BY_WEEKDAY[6 if epw.start_weekday is None else epw.start_weekday]


def iana_zone(state: str, tz_offset_h: float) -> str:
    zone = _ZONE_BY_STATE.get(state.upper()) or _ZONE_BY_OFFSET.get(float(tz_offset_h))
    if zone is None:
        raise Unavailable(f"no IANA zone for a standard offset of {tz_offset_h:+.1f} h")
    return zone


def epw_to_csv(epw: Epw, columns: Optional[dict] = None) -> str:
    """The lane's CSV (data spec 5.1a). EPW hour `h` of a day becomes the stamp
    `day + h hours` on the nominal year, so hour 24 is the next day's 00:00 and the
    last row is 1 January of the following year: hour-ending, local standard time."""
    cols = columns or epw.columns
    year = nominal_year(epw)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)

    def fmt(v):
        return "" if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 2)

    for i in range(len(epw.hour)):
        stamp = dt.datetime(year, int(epw.month[i]), int(epw.day[i])) + dt.timedelta(hours=int(epw.hour[i]))
        writer.writerow([stamp.strftime("%Y-%m-%dT%H:%M")]
                        + [fmt(cols[name][i]) for name in CSV_COLUMNS[1:]])
    return buf.getvalue()


def _epw_from_zip(data: bytes) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".epw")]
            if len(names) != 1:
                raise Unavailable(f"ZIP holds {len(names)} EPW files, expected 1")
            return names[0], zf.read(names[0]).decode("latin-1")
    except zipfile.BadZipFile as exc:
        raise Unavailable(f"download is not a ZIP: {exc}") from exc


# ---------- the whole step ----------

@dataclass(frozen=True)
class TypicalYear:
    csv_text: str
    timezone: str
    source: str
    detail: str
    choice: Choice


def typical_year(sid: str, lat: float, lon: float, *,
                 site_elevation_m: Optional[float] = None,
                 get_bytes: Optional[BytesGetter] = None,
                 refresh: bool = False) -> TypicalYear:
    """Pick the station, fetch (or replay) its ZIP, parse, verify and convert. Raises
    `Unavailable` with the reason on any failure; the caller falls back.

    The ZIP is kept in `data/cache/<sid>/weather/` beside the CSV, so a second run is
    offline. An injected transport neither reads nor writes it.
    """
    try:
        index = load_index(get_bytes=get_bytes, refresh=refresh)
    except Unavailable:
        raise
    except Exception as exc:  # network, HTTP status, decode: all mean "no index"
        raise Unavailable(f"TMYx station index unavailable: {str(exc)[:160]}") from exc
    if not index:
        raise Unavailable("TMYx station index is empty")

    choice = choose_station(lat, lon, index, site_elevation_m=site_elevation_m)
    if choice is None:
        raise Unavailable(f"no TMYx station within {MAX_DISTANCE_KM:.0f} km with a record of "
                          f"{MIN_RECORD_YEARS}+ years to {MIN_RECORD_END} or later")

    url = file_url(choice.file)
    zip_path = cache.cache_root() / sid / "weather" / Path(url).name
    data = None
    if get_bytes is None and not refresh and zip_path.is_file():
        data = zip_path.read_bytes()
    if data is None:
        try:
            data = (get_bytes or _default_get_bytes)(url)
        except Exception as exc:
            raise Unavailable(f"TMYx download failed for {Path(url).name}: {str(exc)[:160]}") from exc
    name, text = _epw_from_zip(data)
    epw = parse_epw(text)
    if epw.location["wmo"] != choice.station["wmo"]:
        raise Unavailable(f"EPW is WMO {epw.location['wmo']}, index said {choice.station['wmo']}")
    if get_bytes is None:
        cache.atomic_write_path(zip_path, data)

    columns, offset, shift = realigned_solar(epw)
    zone = iana_zone(choice.station["state"], epw.location["tz_offset_h"])
    st = choice.station
    period = choice.file["variant"].replace("TMYx", "").lstrip(".") or "full record"
    rec = (f"record {choice.file.get('record_start')}-{choice.file.get('record_end')}"
           if choice.file.get("record_start") else "record not stated")
    solar = (f"irradiance measured {offset:+.2f} h late against hour-ending and realigned by "
             f"{shift:g} h" if shift else f"irradiance measured {offset:+.2f} h against hour-ending, kept")
    source = (f"TMYx typical year (climate.onebuilding.org; NOAA ISD observations, ERA5 solar), "
              f"station {st['name']} WMO {st['wmo']}, {choice.distance_km:.1f} km away, "
              f"{period} ({rec}); stamps on nominal year {nominal_year(epw)}")
    detail = (f"{name}; {choice.distance_km:.1f} km, station {st.get('elevation_m')} m"
              + (f" vs site {site_elevation_m:.0f} m" if site_elevation_m is not None else "")
              + f"; {rec}; months {epw.source_months or 'not stated'}; {solar}"
              + (f"; skipped nearer: {', '.join(choice.skipped)}" if choice.skipped else ""))
    return TypicalYear(csv_text=epw_to_csv(epw, columns), timezone=zone, source=source,
                       detail=detail, choice=choice)
