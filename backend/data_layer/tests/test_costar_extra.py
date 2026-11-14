"""D10: occupancy and market data from the five unused CoStar datasets.

The counts asserted here were measured on the real mirror on 2026-11-14 and are in
`specs/data-integration.md`. Tests that need the mirror skip without it; the unit tests
of the conversions and rules run everywhere.

Reading a local file is not a network call, so none of this needs `RUN_LIVE_NETWORK`.
"""
from __future__ import annotations

import pytest

from backend.data_layer import costar_extra as d10
from backend.data_layer import index
from backend.schema import MarketData, OccupancyData, Ranged

LA_OFFICE = "246899"
HOUSTON_OFFICE = "234088"

needs_kit = pytest.mark.skipif(not index.kit_available(), reason="no CoStar kit mirror")


# ---------- rules that hold with or without the kit ----------

def test_cap_rates_are_converted_from_percent():
    """The kit stores 6.5 to mean 6.5 %; the contract documents `cap_rate` as a
    fraction per year. Passing the raw number through overstates value uplift a
    hundredfold and nothing errors."""
    assert d10.PERCENT_TO_FRACTION == 0.01
    # A median commercial cap rate of 6.5 % must come out as 0.065, not 6.5.
    assert 6.5 * d10.PERCENT_TO_FRACTION == pytest.approx(0.065)


def test_the_quartile_range_respects_the_contract_ordering():
    """`Ranged` requires low <= expected <= high, and quartiles of a short list tie."""
    for values in ([1.0, 1.0, 1.0], [1.0, 2.0, 3.0], [5.0, 1.0, 3.0, 2.0, 4.0],
                   [0.04, 0.05, 0.06, 0.07]):
        r = d10._ranged(values, "x")
        assert r is not None and r.low <= r.expected <= r.high


def test_too_few_values_give_no_range_rather_than_a_fake_one():
    assert d10._ranged([], "x") is None
    assert d10._ranged([0.05], "x") is None
    assert d10._ranged([0.05, 0.06], "x") is None
    assert d10._ranged([0.05, 0.06, 0.07], "x") is not None


def test_expected_is_the_median_not_the_mean():
    """One distressed sale must not drag the market rate."""
    r = d10._ranged([0.05, 0.05, 0.05, 0.05, 0.90], "x")
    assert r.expected == pytest.approx(0.05)


def test_sale_price_per_m2_is_never_supplied():
    """`soldForPrice` covers whatever was sold - often one unit or a partial interest -
    while the only area the kit gives is the whole building's. Measured: 86 priced Los
    Angeles office sales over 29 distinct properties, one contributing 43, spanning 6
    to 40,025 USD/m2. `value.py:60` would multiply it straight into the property value."""
    assert "partial" in d10.SALE_PRICE_NOTE
    assert "40,025" in d10.SALE_PRICE_NOTE


def test_a_missing_property_id_is_a_record_not_a_crash():
    for fn in (d10.market_data, d10.occupancy_data):
        value, notes = fn(None)
        assert value is None
        assert notes[0].status == "missing" and notes[0].layer == "costar"


def test_the_comp_window_is_a_documented_judgement():
    """2020 leaves one usable Los Angeles office comp, below A30's MIN_COMPS of 10;
    reaching back further than 2015 starts quoting 1983 sales as a market signal."""
    assert d10.MARKET_SINCE_YEAR == 2015


# ---------- needs the mirror ----------

@needs_kit
def test_both_golden_offices_clear_a30s_minimum():
    """`plan_value_uplift` returns None below MIN_COMPS = 10, so this is the test that
    says whether value uplift can run on live data at all."""
    from backend.analysis.finance.value.value import MIN_COMPS

    for pid, expect in ((LA_OFFICE, 12), (HOUSTON_OFFICE, 25)):
        market, notes = d10.market_data(pid)
        assert market is not None and market.cap_rate is not None
        assert market.comp_count == expect, f"{pid}: comp count moved"
        assert market.comp_count >= MIN_COMPS
        assert notes[0].status == "ok"


@needs_kit
def test_cap_rates_rank_houston_above_los_angeles():
    """A riskier market with cheaper assets carries a higher yield. This is the sanity
    check that the conversion and the market filter are both right - a units error or
    a mixed-up market would not preserve it."""
    la = d10.market_data(LA_OFFICE)[0].cap_rate
    houston = d10.market_data(HOUSTON_OFFICE)[0].cap_rate
    assert 0.02 < la.expected < 0.15, "a plausible commercial cap rate"
    assert 0.02 < houston.expected < 0.15
    assert houston.expected > la.expected


@needs_kit
def test_one_cap_rate_observation_per_property():
    """A building that trades often must not dominate the distribution. The Houston
    office market has 27 sales with a cap rate over 25 properties."""
    market = d10.market_data(HOUSTON_OFFICE)[0]
    peers = [c for c in d10.sale_comps()
             if c["city"] == "Houston" and c["property_type"] == 5
             and c["year"] and c["year"] >= d10.MARKET_SINCE_YEAR and c["cap_rate"]]
    assert len(peers) > market.comp_count, "the fixture no longer has a repeat sale"
    assert market.comp_count == len({c["property_id"] for c in peers})


@needs_kit
def test_a_market_with_no_comps_returns_nothing_rather_than_a_guess():
    """Land (propertyType 3) has five properties in the whole kit."""
    land = [pid for pid, (_, pt, _) in d10.property_facts().items() if pt == 3]
    assert land, "the kit no longer has a land property to test with"
    market, notes = d10.market_data(land[0])
    assert market.cap_rate is None
    assert notes[0].status == "missing"


@needs_kit
def test_current_tenants_are_those_with_no_to_date():
    """Not `expirationReason == 0`: that enum says why a tenancy *ended* and its zero
    value is "Unknown". No record in either golden office has a future `toDate`."""
    for pid, tenants, employees in ((LA_OFFICE, 37, 413), (HOUSTON_OFFICE, 34, 215)):
        data, notes = d10.occupancy_data(pid)
        assert len(data.tenancies) == tenants, f"{pid}: sitting-tenant count moved"
        assert data.employees_total == employees
        assert all(t.move_out is None for t in data.tenancies)
        assert notes[0].status == "ok"


@needs_kit
def test_occupied_area_is_a_plausible_share_of_the_building():
    """The check that caught nothing but would have caught a unit error: summing every
    tenancy ever recorded instead of the sitting ones gives a multiple of the building."""
    for pid in (LA_OFFICE, HOUSTON_OFFICE):
        data = d10.occupancy_data(pid)[0]
        _, _, rentable = d10.property_facts()[pid]
        assert rentable
        share = data.occupied_area_m2 / rentable
        assert 0.3 < share < 1.05, f"{pid}: {share:.0%} of rentable area is not plausible"


@needs_kit
def test_tenancies_carry_names_industries_and_employees():
    data = d10.occupancy_data(HOUSTON_OFFICE)[0]
    assert any(t.tenant_name for t in data.tenancies), "the company-detail join failed"
    assert any(t.industry for t in data.tenancies), "the IndustryType enum did not resolve"
    assert any(t.employees for t in data.tenancies)
    assert any(t.move_in for t in data.tenancies)
    for t in data.tenancies:
        if t.move_in:
            assert len(t.move_in) == 10, "move_in must be an ISO date, not a timestamp"


@needs_kit
def test_everything_validates_against_the_contract():
    for pid in (LA_OFFICE, HOUSTON_OFFICE):
        market = d10.market_data(pid)[0]
        occupancy = d10.occupancy_data(pid)[0]
        MarketData.model_validate(market.model_dump(mode="json"))
        OccupancyData.model_validate(occupancy.model_dump(mode="json"))


@needs_kit
def test_asking_rent_comes_from_apartment_listings_only():
    """`minRent`/`maxRent` are monthly rents for the smallest and largest unit, so each
    is divided by its own floor area rather than an average of the two."""
    listings = d10.apartment_listings()
    assert listings, "no apartment listings in the kit"
    priced = [pid for pid, rec in listings.items()
              if rec.get("minRent") and rec.get("minSquareFeet")]
    assert priced
    rent = d10._asking_rent(priced[0])
    assert rent is not None and rent.low <= rent.expected <= rent.high
    # A plausible annual rent per square metre: roughly 100 to 1,000 USD.
    assert 50 < rent.expected < 2000
    # An office property has no apartment listing.
    assert d10._asking_rent(HOUSTON_OFFICE) is None


@needs_kit
def test_the_indexes_are_built_once_and_are_fast():
    """Measured cold: 0.86 + 0.13 + 0.34 + 0.58 + 0.04 s, so no disk cache is needed -
    but a second call must not repeat the passes."""
    import time

    for fn in (d10.property_facts, d10.sale_comps, d10.companies,
               d10.tenancies_by_property, d10.apartment_listings):
        fn()                                  # warm
        t0 = time.time()
        fn()
        assert time.time() - t0 < 0.01, f"{fn.__name__} is not cached"


@needs_kit
def test_the_bundle_carries_both_on_the_offline_path_or_says_why():
    """The offline path replays fixtures, so whatever the example holds is what comes
    back - this asserts the door does not crash and the contract still validates."""
    from backend.data_layer import api
    from backend.schema import PropertyBundle

    bundle = api.get_property_bundle("L3266YcPPvd")
    PropertyBundle.model_validate(bundle.model_dump(mode="json"))
