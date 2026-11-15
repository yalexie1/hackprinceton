"""Installed-cost check against the Tracking the Sun market distribution."""
from __future__ import annotations

import pytest

from backend.evals.run_cost import cost_row, market_stats


def test_verdict_is_inside_iqr_when_our_price_sits_in_the_middle():
    row = cost_row(sid="x", state="CA", segment="commercial", our_usd_per_w=3.1,
                   stats={"p25": 2.8, "median": 3.2, "p75": 3.6, "n": 500, "year": 2023})
    assert row["verdict"] == "inside_iqr"


def test_verdict_flags_a_price_above_the_market():
    row = cost_row(sid="x", state="CA", segment="commercial", our_usd_per_w=5.0,
                   stats={"p25": 2.8, "median": 3.2, "p75": 3.6, "n": 500, "year": 2023})
    assert row["verdict"] == "above_iqr"


def test_verdict_flags_a_price_below_the_market():
    row = cost_row(sid="x", state="CA", segment="commercial", our_usd_per_w=1.0,
                   stats={"p25": 2.8, "median": 3.2, "p75": 3.6, "n": 500, "year": 2023})
    assert row["verdict"] == "below_iqr"


def test_a_thin_band_is_marked_indicative_so_it_is_not_read_as_a_verdict():
    # A percentile from a handful of systems is not a market distribution.
    row = cost_row(sid="x", state="TX", segment="commercial", our_usd_per_w=3.1,
                   stats={"p25": 2.8, "median": 3.2, "p75": 3.6, "n": 7, "year": 2023})
    assert row["indicative"] is True
    row_many = cost_row(sid="x", state="TX", segment="commercial", our_usd_per_w=3.1,
                        stats={"p25": 2.8, "median": 3.2, "p75": 3.6, "n": 700, "year": 2023})
    assert row_many["indicative"] is False


def test_no_market_data_is_not_checked_rather_than_a_pass():
    row = cost_row(sid="x", state="WY", segment="commercial", our_usd_per_w=3.1, stats=None)
    assert row["verdict"] == "not_checked"
    assert row["median_usd_per_w"] is None


def test_no_price_of_our_own_is_not_checked():
    row = cost_row(sid="x", state="CA", segment="commercial", our_usd_per_w=None,
                   stats={"p25": 2.8, "median": 3.2, "p75": 3.6, "n": 500, "year": 2023})
    assert row["verdict"] == "not_checked"


def test_market_stats_drops_non_positive_prices_and_sizes():
    # A zero-price or zero-size row is a data artefact, not a $0/W system.
    rows = [(10.0, 30000.0), (0.0, 30000.0), (10.0, 0.0), (10.0, -5.0), (20.0, 80000.0)]
    stats = market_stats(rows, min_year_rows=1)
    assert stats["n"] == 2
    assert stats["median"] == pytest.approx(3.5, abs=0.26)


def test_market_stats_is_none_when_nothing_survives():
    assert market_stats([(0.0, 0.0)], min_year_rows=1) is None


def test_segment_codes_pool_non_residential_and_exclude_unreported():
    from backend.evals.run_cost import SEGMENT_CODES

    assert SEGMENT_CODES["residential"] == {"RES"}
    # Tracking the Sun splits non-residential four ways; each is too thin per
    # state-year to give a stable band, so they are pooled.
    assert {"NON-RES", "COM", "GOV", "SCHOOL", "NON-PROFIT"} == SEGMENT_CODES["commercial"]
    # "-1" is "not reported" and must never be counted as either segment.
    for codes in SEGMENT_CODES.values():
        assert "-1" not in codes
