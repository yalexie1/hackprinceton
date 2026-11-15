"""Guards on the weather arms.

These exist because a unit error here is invisible: Open-Meteo returns
windspeed_10m in km/h by default, the column is named wind_m_s, and nothing
downstream complains about a 3.6x wind. It just quietly inflates infiltration.
"""
from __future__ import annotations

import pytest

from backend.evals.prep_weather import check_wind_units


def test_accepts_a_plausible_m_s_wind_year():
    # Annual mean wind at 10 m is typically 2-6 m/s.
    check_wind_units([3.1] * 8000 + [18.0] * 760, site="Test")


def test_rejects_a_km_h_wind_year_mislabelled_as_m_s():
    # What the bug actually produced: mean ~11, max ~42.
    with pytest.raises(ValueError, match="km/h"):
        check_wind_units([10.9] * 8000 + [41.6] * 760, site="Bear")


def test_rejects_an_implausible_maximum_even_when_the_mean_looks_fine():
    # A 60 m/s hourly mean is a category-4 hurricane, not a weather year.
    with pytest.raises(ValueError, match="km/h"):
        check_wind_units([3.0] * 8700 + [60.0] * 60, site="Test")


def test_empty_input_is_not_silently_accepted():
    with pytest.raises(ValueError):
        check_wind_units([], site="Test")
