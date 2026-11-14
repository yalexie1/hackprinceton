"""D18: the ASHRAE 169 climate zone, measured from the weather year the lane already fetched.

Nothing passed `climate_zone`, so every live bundle carried `None` while the committed examples
carried `3B`, `3B` and `2A`. The model registry falls back on the state, so the vintage defaults
survived - but the A31 energy-use benchmark has no fallback and reported `not_checked: no climate
zone` on every live run, turning off the one sanity check on the model exactly when the numbers
are real. Nothing here touches the network.
"""
from __future__ import annotations

import pytest

from backend.data_layer import external
from backend.schema import ClimateSite

#: Measured on the three golden properties' own TMYx years (2026-11-14).
GOLDEN = [
    ("house, Los Angeles", 3156.0, 527.0, "CA", "3B"),
    ("Culver Connect, Los Angeles", 2620.0, 728.0, "CA", "3B"),
    ("Houston office", 4510.0, 552.0, "TX", "2A"),
]


def year_of(mean_c: float) -> list[float]:
    """A year of hourly temperature at a constant daily mean."""
    return [mean_c] * (365 * 24)


def test_the_thermal_digit_follows_the_ashrae_thresholds():
    assert external._thermal_digit(6500, 0) == "0"
    assert external._thermal_digit(5500, 0) == "1"
    assert external._thermal_digit(4000, 0) == "2"
    assert external._thermal_digit(3000, 0) == "3"
    assert external._thermal_digit(0, 1500) == "3", "warm winters are zone 3 however low the CDD"
    assert external._thermal_digit(0, 2500) == "4"
    assert external._thermal_digit(0, 3500) == "5"
    assert external._thermal_digit(0, 4500) == "6"
    assert external._thermal_digit(0, 6000) == "7"
    assert external._thermal_digit(0, 8000) == "8"


@pytest.mark.parametrize("name,cdd,hdd,state,expected", GOLDEN)
def test_the_golden_degree_days_give_the_examples_zone(name, cdd, hdd, state, expected):
    """The check that this is right at all: the measured degree-days of each golden property
    reproduce the zone its committed example carries."""
    digit = external._thermal_digit(cdd, hdd)
    assert f"{digit}{external._MOISTURE_BY_STATE[state]}" == expected, name


def test_a_constant_year_is_classified_and_the_record_says_how():
    zone, record = external.climate_zone_from_temperatures(year_of(19.0), "CA")
    assert zone == "3B"
    assert record.status == "ok"
    assert "measured" in record.detail and "CDD10" in record.detail
    assert "assumed from the state" in record.detail, "the letter's weakness must be stated"


def test_an_unknown_state_reports_no_zone_rather_than_guessing_a_letter():
    """The digit is a measurement; the letter needs precipitation this lane does not fetch. With
    no state there is nothing to take it from, and inventing one would put a wrong zone into the
    vintage tables."""
    zone, record = external.climate_zone_from_temperatures(year_of(19.0), None)
    assert zone is None
    assert record.status == "fallback" and "moisture letter" in record.detail
    assert "thermal zone 3" in record.detail, "the part that was measured is still reported"


def test_too_short_a_year_is_refused():
    zone, record = external.climate_zone_from_temperatures([19.0] * (24 * 100), "CA")
    assert zone is None and record.status == "missing"
    assert "too few" in record.detail


def test_a_zone_that_was_already_supplied_is_never_overwritten():
    """A bundle whose zone came from somewhere better than this estimate keeps it."""
    from backend.data_layer import api

    site = ClimateSite(lat=34.0, lon=-118.0, timezone="America/Los_Angeles", climate_zone="3C",
                       weather_path="data/cache/nope/weather/typical_year_hourly.csv",
                       weather_source="test")
    out, record = api._with_climate_zone(site, "CA")
    assert out.climate_zone == "3C" and record.status == "ok"
    assert "already supplied" in record.detail


def test_an_unreadable_weather_file_leaves_the_zone_unset_rather_than_raising():
    from backend.data_layer import api

    site = ClimateSite(lat=34.0, lon=-118.0, timezone="America/Los_Angeles",
                       weather_path="data/cache/__absent__/weather/typical_year_hourly.csv",
                       weather_source="test")
    out, record = api._with_climate_zone(site, "CA")
    assert out.climate_zone is None and record.status == "missing"
