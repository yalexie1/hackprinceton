"""Tests for package D9 (weather and tariff).

Offline set injects fake getters built from responses actually observed on
2026-11-14. Live set runs only when the relevant key or network is available.
"""
from __future__ import annotations

import csv
import io
import os

import pytest

from backend.data_layer import external as ex
from backend.schema import ClimateSite, Tariff

# Three hours shaped like a real Open-Meteo archive response, including the
# sunrise boundary that proves the hour_end convention.
HOURLY = {
    "timezone": "America/Los_Angeles",
    "hourly_units": {"shortwave_radiation": "W/m²", "wind_speed_10m": "km/h"},
    "hourly": {
        "time": ["2024-06-21T04:00", "2024-06-21T05:00", "2024-06-21T06:00"],
        "temperature_2m": [16.5, 16.8, 18.0],
        "relative_humidity_2m": [80, 78, 70],
        "shortwave_radiation": [0.0, 2.0, 85.0],
        "direct_normal_irradiance": [0.0, 1.0, 180.0],
        "diffuse_radiation": [0.0, 1.0, 40.0],
        "wind_speed_10m": [3.6, 7.2, 18.0],          # km/h -> 1.0, 2.0, 5.0 m/s
    },
}

PVGIS = {"inputs": {"meteo_data": {"radiation_db": "PVGIS-ERA5"}},
         "outputs": {"totals": {"fixed": {"E_y": 1754.23, "SD_y": 40.36}}}}

# EIA returns numbers as JSON **strings**, and these fixtures copy that exactly.
# An earlier version used floats here, which made the offline suite pass against a
# response shape the API never sends; the live test was the only thing that caught it.
EIA_TX_COM = {"response": {"data": [
    {"period": "2026-08", "stateid": "TX", "sectorid": "COM",
     "price": "8.96", "price-units": "cents per kilowatt-hour"}]}}
EIA_CA_RES = {"response": {"data": [
    {"period": "2026-08", "stateid": "CA", "sectorid": "RES",
     "price": "29.75", "price-units": "cents per kilowatt-hour"}]}}


def _getter(mapping):
    """Routes by URL so one fake serves Open-Meteo, PVGIS and EIA."""
    def get(url, params):
        for frag, payload in mapping.items():
            if frag in url:
                return payload
        raise AssertionError(f"unexpected URL: {url}")
    return get


# ---------- weather ----------

def test_csv_format_and_wind_conversion():
    text = ex.hourly_csv(HOURLY)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == list(ex.CSV_COLUMNS)
    assert len(rows) == 4
    # km/h -> m/s, the one unit Open-Meteo does not give us in SI
    assert [r[-1] for r in rows[1:]] == ["1.0", "2.0", "5.0"]
    assert rows[2][:4] == ["2024-06-21T05:00", "16.8", "78", "2.0"]


def test_ghi_dni_dhi_are_all_carried():
    """Open-Meteo separates them, so no decomposition step is needed downstream."""
    rows = list(csv.DictReader(io.StringIO(ex.hourly_csv(HOURLY))))
    assert rows[2]["ghi_w_m2"] == "85.0"
    assert rows[2]["dni_w_m2"] == "180.0"
    assert rows[2]["dhi_w_m2"] == "40.0"


def test_time_convention_is_hour_end_and_matches_the_sunrise_boundary():
    """Sunrise was 04:42: 04:00 reads 0.0 and 05:00 only 2.0, which fits the stamp
    labelling the hour that ENDS at it. Under hour_start the 05:00 value would have
    to be far larger, since the sun would already have been up 18-78 minutes."""
    assert ex.TIME_CONVENTION == "hour_end"
    rows = list(csv.DictReader(io.StringIO(ex.hourly_csv(HOURLY))))
    assert float(rows[0]["ghi_w_m2"]) == 0.0
    assert 0.0 < float(rows[1]["ghi_w_m2"]) < 10.0
    assert float(rows[2]["ghi_w_m2"]) > 50.0


def test_climate_site_is_built_and_labelled_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "_ROOT", tmp_path)
    site, notes = ex.get_climate_site(
        "SID1", 34.0935, -118.3171, 2024,
        get=_getter({"open-meteo": HOURLY, "jrc.ec.europa.eu": PVGIS}))
    ClimateSite.model_validate(site.model_dump(mode="json"))
    assert site.weather_path == "data/cache/SID1/weather/typical_year_hourly.csv"
    assert (tmp_path / site.weather_path).is_file()
    assert site.weather_time_convention == "hour_end"
    assert site.timezone == "America/Los_Angeles"
    # the file is one real year and says so, rather than claiming to be a TMY
    assert "2024" in site.weather_source and "not a TMY" in site.weather_source
    # 3 rows is far short of a year, so the note says so rather than passing silently
    weather = [n for n in notes if n.what == "open-meteo/archive"][0]
    assert weather.status == "fallback" and "short year" in weather.detail


def test_pvgis_supplies_the_uncertainty_band(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "_ROOT", tmp_path)
    site, notes = ex.get_climate_site(
        "SID1", 34.0935, -118.3171, 2024, write=False,
        get=_getter({"open-meteo": HOURLY, "jrc.ec.europa.eu": PVGIS}))
    assert site.pvgis_annual_kwh_per_kw == pytest.approx(1754.23)
    # SD_y / E_y: a measured inter-annual spread instead of an invented one
    assert site.pvgis_sd_fraction == pytest.approx(40.36 / 1754.23)
    assert any(n.what == "pvgis/PVcalc" and n.status == "ok" for n in notes)


def test_pvgis_failure_is_never_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "_ROOT", tmp_path)

    def get(url, params):
        if "open-meteo" in url:
            return HOURLY
        raise RuntimeError("PVGIS down")

    site, notes = ex.get_climate_site("SID1", 34.0, -118.0, 2024, write=False, get=get)
    assert site.pvgis_annual_kwh_per_kw is None and site.pvgis_sd_fraction is None
    assert any(n.what == "pvgis/PVcalc" and n.status == "error" for n in notes)


def test_pvgis_zero_yield_is_treated_as_missing():
    assert ex._pvgis_annual_and_sd({"outputs": {"totals": {"fixed": {"E_y": 0}}}}) == (None, None)
    assert ex._pvgis_annual_and_sd({}) == (None, None)


# ---------- tariff ----------

def test_eia_tariff_is_always_labelled_a_fallback(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "x")
    tariff, notes = ex.get_tariff("TX", "COM", get=_getter({"api.eia.gov": EIA_TX_COM}))
    Tariff.model_validate(tariff.model_dump(mode="json"))
    # 8.96 cents -> USD per kWh
    assert tariff.electricity_usd_per_kwh == pytest.approx(0.0896)
    assert tariff.retrieved == "2026-08"
    assert "EIA state average" in tariff.source and "TX COM" in tariff.source
    assert notes[0].layer == "tariff" and notes[0].status == "fallback"


def test_cents_conversion_on_a_second_state(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "x")
    tariff, _ = ex.get_tariff("CA", "RES", get=_getter({"api.eia.gov": EIA_CA_RES}))
    assert tariff.electricity_usd_per_kwh == pytest.approx(0.2975)


def test_export_regime_follows_the_state(monkeypatch):
    """The contract documents `export_regime` as "None where no export price is
    mandated (Texas)". California mandates one, ERCOT does not, and leaving the field
    unset discarded something the schema asked for."""
    monkeypatch.setenv("EIA_API_KEY", "x")
    ca, _ = ex.get_tariff("CA", "RES", get=_getter({"api.eia.gov": EIA_CA_RES}))
    tx, _ = ex.get_tariff("TX", "COM", get=_getter({"api.eia.gov": EIA_TX_COM}))
    assert ca.export_regime == "net_metering"
    assert tx.export_regime == "none"
    # An unknown state must not be given a regime it may not have.
    assert ex.EXPORT_REGIME.get("NY") is None


def test_the_utility_is_never_inferred_from_a_city(monkeypatch):
    """Deriving the utility from the CoStar `City` field would repeat the mistake the
    PACE work caught: `cityId` 5316 "Houston" included a property outside the
    incorporated city, and LADWP/SCE splits the same way around Los Angeles. Absent a
    verified utility the field says what the number actually is."""
    monkeypatch.setenv("EIA_API_KEY", "x")
    tariff, _ = ex.get_tariff("CA", "COM", get=_getter({"api.eia.gov": EIA_CA_RES}))
    assert "state average" in tariff.utility
    assert "LADWP" not in tariff.utility


def test_a_known_utility_name_is_kept(monkeypatch):
    """URDB gives LADWP for the LA properties; the price still comes from EIA, and
    the fallback status still says so."""
    monkeypatch.setenv("EIA_API_KEY", "x")
    tariff, notes = ex.get_tariff("CA", "RES", utility="Los Angeles Department of Water & Power",
                                  get=_getter({"api.eia.gov": EIA_CA_RES}))
    assert tariff.utility.startswith("Los Angeles Department")
    assert notes[0].status == "fallback"


def test_price_parses_from_a_string_and_from_a_number():
    """The API sends strings; a number is accepted too so a hand-made payload works."""
    assert ex._as_number("8.96") == pytest.approx(8.96)
    assert ex._as_number(8.96) == pytest.approx(8.96)
    assert ex._as_number(" 29.75 ") == pytest.approx(29.75)
    assert ex._as_number("") is None
    assert ex._as_number("n/a") is None
    assert ex._as_number(None) is None
    assert ex._as_number(True) is None           # a bool is not a price


def test_unparseable_price_is_a_note(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "x")
    body = {"response": {"data": [{"period": "2026-08", "price": "n/a"}]}}
    tariff, notes = ex.get_tariff("TX", "COM", get=_getter({"api.eia.gov": body}))
    assert tariff is None and notes[0].status == "missing"


def test_no_key_is_a_note_not_a_crash(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    tariff, notes = ex.get_tariff("TX", "COM")
    assert tariff is None
    assert notes[0].status == "missing" and "EIA_API_KEY" in notes[0].detail


def test_empty_eia_response_is_a_note(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "x")
    tariff, notes = ex.get_tariff("TX", "COM",
                                  get=_getter({"api.eia.gov": {"response": {"data": []}}}))
    assert tariff is None and notes[0].status == "missing"


# ---------- live ----------

#: Network tests are **opt-in**, so `pytest backend -q` is always offline. The
#: server lane's checkpoint asserts the whole suite makes no network call, and a
#: test that fires whenever a key happens to be present would quietly break that.
RUN_LIVE = os.environ.get("RUN_LIVE_NETWORK") == "1"
live_net = pytest.mark.skipif(not RUN_LIVE, reason="set RUN_LIVE_NETWORK=1 to run")
live_eia = pytest.mark.skipif(not (RUN_LIVE and os.environ.get("EIA_API_KEY")),
                              reason="set RUN_LIVE_NETWORK=1 and EIA_API_KEY to run")


@live_net
def test_live_open_meteo_hour_end_reconciles_with_the_daily_total():
    """The decisive check, re-run: hourly values are full-hour means, so their sum
    equals the daily total. If they were instantaneous samples it would not."""
    payload = ex._default_get(ex.OPEN_METEO, {
        "latitude": 34.093491667, "longitude": -118.3171,
        "start_date": "2024-06-21", "end_date": "2024-06-21",
        "hourly": "shortwave_radiation", "daily": "shortwave_radiation_sum",
        "timezone": "auto",
    })
    hourly = [v for v in payload["hourly"]["shortwave_radiation"] if v is not None]
    assert len(hourly) == 24
    mj = sum(hourly) * 3600 / 1e6
    assert mj == pytest.approx(payload["daily"]["shortwave_radiation_sum"][0], rel=1e-3)


@live_net
@pytest.mark.parametrize("lat,lon", [(34.093491667, -118.3171),
                                     (29.74602759879178, -95.45754572577202)])
def test_live_pvgis_gives_a_spread_for_both_cities(lat, lon):
    annual, sd = ex._pvgis_annual_and_sd(ex.fetch_pvgis(lat, lon))
    assert annual and annual > 500
    assert sd and 0.0 < sd < 0.2       # a real inter-annual spread, a few per cent


@live_eia
@pytest.mark.parametrize("state,sector", [("TX", "COM"), ("TX", "RES"),
                                          ("CA", "COM"), ("CA", "RES")])
def test_live_eia_prices(state, sector):
    tariff, notes = ex.get_tariff(state, sector)
    assert tariff and 0.02 < tariff.electricity_usd_per_kwh < 1.0
    assert notes[0].status == "fallback"
