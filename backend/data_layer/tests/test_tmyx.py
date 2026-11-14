"""Tests for the TMYx typical-year weather source (#295).

Offline: a synthetic KML index and synthetic EPW files built here, shaped like the
real ones read on 2026-11-14 (Region 4 USA index; `..._TMYx.2011-2025.epw`). The live
test is opt-in, as everywhere in the lane.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
import os
import zipfile

import numpy as np
import pytest

from backend.data_layer import external as ex
from backend.data_layer import tmyx
from backend.schema import ClimateSite

HOUSE = (34.0934917, -118.3171)

BASE = "WMO_Region_4_North_and_Central_America/USA_United_States_of_America/CA_California/"


def _placemark(state, name, wmo, variant, lat, lon, elev, years, start, end, tz=-8.0):
    stem = f"USA_{state}_{name}.{wmo}_{variant}"
    return f"""  <Placemark>
    <name>{name} {state} USA</name>
    <description><![CDATA[<table><tr><td colspan="2"><b>USA {state} {name}.{wmo} {variant}</b></td></tr>
       <tr><td>NCEI ISD/ERA5 - #years=[{years}] Period of Record={start}-{end}</td></tr>
       <tr><td>WMO <b>{wmo}</b></td></tr>
       <tr><td>Elevation <b>{elev}</b> m</td></tr>
       <tr><td>Time Zone {{GMT <b>{tz}</b> hours}}</td></tr>
       <tr><td>URL https://climate.onebuilding.org/{BASE}{stem}.zip</td></tr></table>]]></description>
   <Point>
     <altitudeMode>absolute</altitudeMode>
     <coordinates>{lon},{lat},{elev}</coordinates>
   </Point>
  </Placemark>
"""


#: Real coordinates, elevations and record lengths from the 2026 index.
KML = (
    "<kml><Document>\n"
    # the region marker: no URL, must be skipped
    "  <Placemark> id=\"Reg4\">\n    <name>Reg4_USA_TMYx Data</name>\n"
    "    <Point><coordinates>-121.7670,36.7330,43.0</coordinates></Point>\n  </Placemark>\n"
    + _placemark("CA", "Los.Angeles.Downtown-USC.Campus", "722874", "TMYx", 34.024, -118.291, 55, 26, 1999, 2024)
    + _placemark("CA", "Los.Angeles.Downtown-USC.Campus", "722874", "TMYx.2009-2023", 34.024, -118.291, 55, 15, 2009, 2023)
    + _placemark("CA", "Los.Angeles.Downtown-USC.Campus", "722874", "TMYx.2011-2025", 34.024, -118.291, 55, 14, 2011, 2024)
    + _placemark("CA", "Hollywood.Burbank.AP", "722880", "TMYx", 34.2005, -118.3575, 236, 78, 1943, 2025)
    + _placemark("CA", "Santa.Monica.AP", "722885", "TMYx", 34.016, -118.451, 53, 53, 1973, 2025)
    # a short-record heliport nearer than anything else
    + _placemark("CA", "Some.Heli", "720000", "TMYx", 34.09, -118.32, 60, 18, 2008, 2025)
    + "</Document></kml>\n"
)


def _epw_text(wmo="722874", lat=34.024, lon=-118.291, tz=-8.0, *, lag_h=0.5,
              weekday="Sunday", rows=8760, missing_temp_hours=()):
    """A year whose GHI is a symmetric bell around mean solar noon, sampled so that the
    value stamped hour `h` is centred `lag_h` before `h` (0.5 = hour-ending)."""
    noon = 12.0 - (lon - 15.0 * tz) / 15.0
    head = [
        f"LOCATION,Los.Angeles.Downtown-USC.Campus,CA,USA,SRC-TMYx,{wmo},{lat},{lon},{tz},54.6",
        "DESIGN CONDITIONS,0", "TYPICAL/EXTREME PERIODS,0", "GROUND TEMPERATURES,0",
        "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
        'COMMENTS 1,"NCEI ISD/ERA5 - #years=[14] Period of Record=2011-2024; Jan=2022; '
        'Feb=2014; Mar=2019; Apr=2015; May=2017; Jun=2013; Jul=2019; Aug=2014; Sep=2014; '
        'Oct=2020; Nov=2016; Dec=2018"',
        "COMMENTS 2,synthetic",
        f"DATA PERIODS,1,1,Data,{weekday},1/ 1,12/31",
    ]
    lines = []
    day = dt.date(2017, 1, 1)
    i = 0
    while len(lines) < rows:
        for h in range(1, 25):
            t = h - lag_h
            x = (t - noon) / 6.0             # one bell, 6 h either side of noon
            ghi = 900.0 * math.cos(x * math.pi / 2) if abs(x) < 1 else 0.0
            temp = 99.9 if i in missing_temp_hours else 15.0 + 5.0 * math.sin((h - 9) / 24 * 2 * math.pi)
            f = ["2022", str(day.month), str(day.day), str(h), "0", "flags",
                 f"{temp:.1f}", "6.1", "80", "100659", "0", "0", "284",
                 f"{ghi:.0f}", f"{ghi * 0.7:.0f}", f"{ghi * 0.3:.0f}",
                 "0", "0", "0", "0", "270", "3.5", "5", "5"]
            lines.append(",".join(f))
            i += 1
        day += dt.timedelta(days=1)
    return "\n".join(head + lines[:rows]) + "\n"


def _zip(text, name="USA_CA_Los.Angeles.Downtown-USC.Campus.722874_TMYx.2011-2025.epw"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, text)
        zf.writestr(name.replace(".epw", ".stat"), "stat")
    return buf.getvalue()


def _bytes_getter(zip_bytes, calls=None):
    def get(url):
        if calls is not None:
            calls.append(url)
        if url == tmyx.INDEX_URL:
            return KML.encode()
        if url.endswith(".zip"):
            if isinstance(zip_bytes, Exception):
                raise zip_bytes
            return zip_bytes
        raise AssertionError(f"unexpected URL {url}")
    return get


HOURLY = {
    "timezone": "America/Los_Angeles",
    "hourly": {"time": ["2024-06-21T04:00"], "temperature_2m": [16.5],
               "relative_humidity_2m": [80], "shortwave_radiation": [0.0],
               "direct_normal_irradiance": [0.0], "diffuse_radiation": [0.0],
               "wind_speed_10m": [3.6]},
}
PVGIS = {"inputs": {"location": {"elevation": 102.0}},
         "outputs": {"totals": {"fixed": {"E_y": 1754.23, "SD_y": 40.36}}}}


def _json_getter(url, params):
    if "open-meteo" in url:
        return HOURLY
    if "jrc.ec.europa.eu" in url:
        return PVGIS
    raise AssertionError(url)


# ---------- the index ----------

def test_index_parses_every_tmyx_placemark_and_skips_the_region_marker():
    rows = tmyx.parse_index(KML)
    assert len(rows) == 6
    usc = [r for r in rows if r["wmo"] == "722874" and r["variant"] == "TMYx"][0]
    assert usc["state"] == "CA" and usc["name"] == "Los.Angeles.Downtown-USC.Campus"
    assert (usc["lat"], usc["lon"], usc["elevation_m"]) == (34.024, -118.291, 55.0)
    assert (usc["record_years"], usc["record_start"], usc["record_end"]) == (26, 1999, 2024)
    assert usc["tz_offset_h"] == -8.0


def test_the_index_keeps_paths_not_urls():
    """D4 replaces every URL in a cached payload, so a cached index of URLs would
    download `<url-not-cached>`. The first live run did exactly that."""
    for row in tmyx.parse_index(KML):
        assert not row["path"].startswith("http")
        assert tmyx.file_url(row).startswith("https://climate.onebuilding.org/WMO_Region_4")


# ---------- the station rule ----------

def test_a_short_record_nearer_station_is_skipped():
    choice = tmyx.choose_station(*HOUSE, tmyx.parse_index(KML), site_elevation_m=102.0)
    assert choice.station["wmo"] == "722874"
    assert choice.distance_km == pytest.approx(8.1, abs=0.2)
    assert any("Some.Heli" in s and "18 years" in s for s in choice.skipped)


def test_the_newest_window_is_downloaded():
    choice = tmyx.choose_station(*HOUSE, tmyx.parse_index(KML))
    assert choice.file["variant"] == "TMYx.2011-2025"
    # eligibility still comes from the station's full record, not the 14-year window
    assert choice.station["variant"] == "TMYx" and choice.station["record_years"] == 26


def test_the_full_record_file_when_there_is_no_window():
    rows = [r for r in tmyx.parse_index(KML) if r["wmo"] == "722885"]
    choice = tmyx.choose_station(34.03075, -118.3889, rows)
    assert choice.file["variant"] == "TMYx"


def test_a_station_on_different_ground_is_skipped():
    """Burbank sits in the valley at 236 m; a basin site at 102 m must not take it."""
    rows = [r for r in tmyx.parse_index(KML) if r["wmo"] in ("722880", "722885")]
    choice = tmyx.choose_station(34.17, -118.33, rows, site_elevation_m=102.0)
    assert choice.station["wmo"] == "722885"
    assert any("Hollywood.Burbank" in s and "236 m" in s for s in choice.skipped)
    # without an elevation the rule is distance only
    assert tmyx.choose_station(34.17, -118.33, rows).station["wmo"] == "722880"


def test_no_station_beyond_the_distance_limit():
    assert tmyx.choose_station(36.5, -116.0, tmyx.parse_index(KML)) is None


def test_distance_is_great_circle():
    # one degree of latitude is 111.2 km on a 6,371 km sphere
    assert tmyx.distance_km(34.0, -118.0, 35.0, -118.0) == pytest.approx(111.19, abs=0.05)


# ---------- the EPW ----------

def test_epw_header_and_columns_are_read():
    epw = tmyx.parse_epw(_epw_text())
    assert epw.location["wmo"] == "722874" and epw.location["tz_offset_h"] == -8.0
    assert epw.start_weekday == 6                      # Sunday
    assert epw.source_months.startswith("Jan=2022") and epw.source_months.endswith("Dec=2018")
    assert len(epw.hour) == 8760 and epw.hour[0] == 1 and epw.hour[23] == 24


def test_missing_values_become_blank_cells():
    epw = tmyx.parse_epw(_epw_text(missing_temp_hours=(5,)))
    assert math.isnan(epw.columns["temp_c"][5])
    rows = list(csv.reader(io.StringIO(tmyx.epw_to_csv(epw))))
    assert rows[6][1] == ""                            # the A1 reader interpolates gaps


@pytest.mark.parametrize("text,reason", [
    ("garbage", "LOCATION"),
    (_epw_text(rows=8000), "8000 hourly rows"),
    (_epw_text(missing_temp_hours=tuple(range(300))), "temp_c has 300 missing"),
])
def test_an_invalid_epw_is_refused(text, reason):
    with pytest.raises(tmyx.Unavailable, match=reason):
        tmyx.parse_epw(text)


def test_stamps_are_hour_ending_on_a_nominal_year_with_the_files_weekday():
    """EPW hour h is the hour ending at h, so hour 1 of 1 January is 01:00 and hour 24
    of 31 December is the next year's 00:00. 2017 starts on a Sunday, as the file says."""
    epw = tmyx.parse_epw(_epw_text())
    rows = list(csv.reader(io.StringIO(tmyx.epw_to_csv(epw))))
    assert rows[0] == list(tmyx.CSV_COLUMNS)
    assert len(rows) == 8761
    assert rows[1][0] == "2017-01-01T01:00"
    assert rows[24][0] == "2017-01-02T00:00"
    assert rows[-1][0] == "2018-01-01T00:00"
    assert dt.date(2017, 1, 1).weekday() == 6
    # contiguous hourly, no 29 February: what the A1 reader needs for 8,760 hours
    stamps = [dt.datetime.fromisoformat(r[0]) for r in rows[1:]]
    assert all((b - a) == dt.timedelta(hours=1) for a, b in zip(stamps, stamps[1:]))


def test_the_nominal_year_follows_the_start_weekday():
    assert tmyx.nominal_year(tmyx.parse_epw(_epw_text(weekday="Monday"))) == 2018
    for weekday, year in tmyx.NOMINAL_YEAR_BY_WEEKDAY.items():
        assert dt.date(year, 1, 1).weekday() == weekday
        assert not (year % 4 == 0)                      # never a leap year


def test_a_conforming_file_is_kept_as_it_is():
    epw = tmyx.parse_epw(_epw_text(lag_h=0.5))
    cols, offset, shift = tmyx.realigned_solar(epw)
    assert abs(offset) < 0.05 and shift == 0.0
    assert np.array_equal(cols["ghi_w_m2"], epw.columns["ghi_w_m2"])


def test_a_half_hour_late_file_is_realigned_and_keeps_its_annual_total():
    """The 2026 TMYx release measures +0.47 to +0.57 h at eight stations."""
    epw = tmyx.parse_epw(_epw_text(lag_h=1.0))
    cols, offset, shift = tmyx.realigned_solar(epw)
    assert offset == pytest.approx(0.5, abs=0.05) and shift == 0.5
    assert cols["ghi_w_m2"].sum() == pytest.approx(epw.columns["ghi_w_m2"].sum())
    realigned = tmyx.Epw(**{**epw.__dict__, "columns": cols})
    assert abs(tmyx.solar_offset_hours(realigned)) < 0.05


def test_an_offset_it_cannot_repair_is_refused():
    with pytest.raises(tmyx.Unavailable, match="off hour-ending"):
        tmyx.realigned_solar(tmyx.parse_epw(_epw_text(lag_h=2.0)))


def test_time_zone_comes_from_the_files_offset():
    assert tmyx.iana_zone("CA", -8.0) == "America/Los_Angeles"
    assert tmyx.iana_zone("TX", -6.0) == "America/Chicago"
    assert tmyx.iana_zone("AZ", -7.0) == "America/Phoenix"   # no daylight saving
    with pytest.raises(tmyx.Unavailable):
        tmyx.iana_zone("XX", 3.5)


# ---------- through get_climate_site ----------

def test_the_typical_year_is_the_source_when_a_station_qualifies(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(ex, "_ROOT", tmp_path)
    site, notes = ex.get_climate_site(
        "SID1", *HOUSE, 2024, get=_json_getter,
        get_bytes=_bytes_getter(_zip(_epw_text(lag_h=1.0))))
    ClimateSite.model_validate(site.model_dump(mode="json"))
    assert site.weather_time_convention == "hour_end"
    assert site.timezone == "America/Los_Angeles"
    assert "TMYx" in site.weather_source and "WMO 722874" in site.weather_source
    assert "8.1 km" in site.weather_source and "2011-2025" in site.weather_source
    rec = [n for n in notes if n.what == "onebuilding/tmyx"][0]
    assert rec.status == "ok" and "realigned by 0.5 h" in rec.detail
    assert "Some.Heli" in rec.detail                      # what was passed over is said
    assert not any(n.what == "open-meteo/archive" for n in notes)
    written = list(csv.reader(open(ex._ROOT / site.weather_path)))
    assert len(written) == 8761 and written[1][0] == "2017-01-01T01:00"
    assert site.pvgis_annual_kwh_per_kw == pytest.approx(1754.23)


@pytest.mark.parametrize("zip_bytes,why", [
    (RuntimeError("HTTP 503"), "download failed"),
    (b"not a zip", "not a ZIP"),
    (_zip(_epw_text(rows=100)), "100 hourly rows"),
    (_zip(_epw_text(wmo="999999")), "WMO 999999"),
    (_zip(_epw_text(lag_h=2.0)), "off hour-ending"),
])
def test_open_meteo_is_the_fallback_and_says_why(tmp_path, monkeypatch, zip_bytes, why):
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(ex, "_ROOT", tmp_path)
    site, notes = ex.get_climate_site("SID1", *HOUSE, 2024, get=_json_getter,
                                      get_bytes=_bytes_getter(zip_bytes))
    rec = [n for n in notes if n.what == "onebuilding/tmyx"][0]
    assert rec.status == "fallback" and why in rec.detail and "Open-Meteo" in rec.detail
    om = [n for n in notes if n.what == "open-meteo/archive"][0]
    assert om.status == "fallback"
    assert site.weather_source.startswith("Open-Meteo archive, calendar year 2024")
    assert why in site.weather_source


def test_no_station_in_range_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(ex, "_ROOT", tmp_path)
    site, notes = ex.get_climate_site("SID1", 40.0, -100.0, 2024, get=_json_getter,
                                      get_bytes=_bytes_getter(_zip(_epw_text())))
    rec = [n for n in notes if n.what == "onebuilding/tmyx"][0]
    assert rec.status == "fallback" and "within 50 km" in rec.detail
    assert "Open-Meteo" in site.weather_source


def test_an_injected_json_transport_alone_makes_no_tmyx_attempt(tmp_path, monkeypatch):
    """The suite makes no network call: injecting `get` without `get_bytes` must not
    send the TMYx step to the real site."""
    monkeypatch.setattr(ex, "_ROOT", tmp_path)

    def boom(url):
        raise AssertionError("network")
    monkeypatch.setattr(tmyx, "_default_get_bytes", boom)
    site, notes = ex.get_climate_site("SID1", *HOUSE, 2024, write=False, get=_json_getter)
    rec = [n for n in notes if n.what == "onebuilding/tmyx"][0]
    assert rec.status == "fallback" and "not tried" in rec.detail


def test_a_second_run_replays_the_cached_zip(tmp_path, monkeypatch):
    """Offline replay: the ZIP sits in `data/cache/<sid>/weather/`, so a live run that
    found it there downloads nothing but the (cached) index."""
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path))
    calls: list[str] = []
    zip_bytes = _zip(_epw_text())
    get = _bytes_getter(zip_bytes, calls)
    monkeypatch.setattr(tmyx, "_default_get_bytes", get)
    first = tmyx.typical_year("SID1", *HOUSE)
    assert (tmp_path / "SID1" / "weather"
            / "USA_CA_Los.Angeles.Downtown-USC.Campus.722874_TMYx.2011-2025.zip").is_file()
    assert len(calls) == 2
    second = tmyx.typical_year("SID1", *HOUSE)
    assert len(calls) == 2                               # index and ZIP both from the cache
    assert second.csv_text == first.csv_text


# ---------- live ----------

RUN_LIVE = os.environ.get("RUN_LIVE_NETWORK") == "1"
live_net = pytest.mark.skipif(not RUN_LIVE, reason="set RUN_LIVE_NETWORK=1 to run")


@live_net
@pytest.mark.parametrize("lat,lon,elev,wmo", [
    (34.0934917, -118.3171, 102.0, "722874"),    # golden house -> Downtown USC
    (34.03075, -118.3889, 38.0, "722885"),       # Culver Connect -> Santa Monica AP
    (29.7452, -95.4567, 23.0, "722440"),         # Houston office -> Hobby
])
def test_live_station_choice_for_the_golden_properties(tmp_path, monkeypatch, lat, lon, elev, wmo):
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path))
    choice = tmyx.choose_station(lat, lon, tmyx.load_index(), site_elevation_m=elev)
    assert choice.station["wmo"] == wmo
    assert choice.file["variant"] == "TMYx.2011-2025"
