"""A30: the worked examples of VAL-01 and VAL-03, and the cases that must return nothing."""
from pathlib import Path

import pytest

from backend.analysis.finance.value import (MIN_COMPS, home_pv_uplift, plan_value_uplift,
                                            value_uplift_home_pv, value_uplift_income)
from backend.schema import MarketData, PropertyBundle, Ranged, RunResult, ValueUplift

EX = Path(__file__).resolve().parents[5] / "specs" / "examples"


def r(low, expected, high, unit="USD"):
    return Ranged(low=low, expected=expected, high=high, unit=unit)


PHI = r(1, 1, 1, "-")
CAP = r(0.06, 0.07, 0.08, "1/year")           # R_low, R_mid, R_high: 25th, 50th, 75th percentile
SAVING = r(9000, 11500, 14000)
MARKET = MarketData(cap_rate=CAP, sale_price_usd_per_m2=r(5400, 6500, 7500), comp_count=18)


# ---- VAL-01 ----

def test_val01_worked_example():
    v = value_uplift_income(SAVING, PHI, CAP)
    assert v.low == 0.0
    assert v.expected == pytest.approx(71_875, abs=0.5)          # 0.5 * 11 500 / 0.08
    assert v.high == pytest.approx(233_333, abs=0.5)             # 14 000 / 0.06
    # the cross-checks of the entry: both lie between expected and high
    for check in (11_500 / 0.07, 11_500 * 18.32):
        assert v.expected < check < v.high


def test_low_expected_high_are_ordered_and_low_is_zero():
    v = value_uplift_income(SAVING, PHI, CAP)
    assert v.low <= v.expected <= v.high and v.low == 0.0


def test_tenants_who_pay_the_utilities_get_nothing():
    v = value_uplift_income(SAVING, r(0, 0, 0, "-"), CAP)
    assert (v.low, v.expected, v.high) == (0.0, 0.0, 0.0)


def test_the_high_is_capped_at_sixteen_percent_of_property_value():
    v = value_uplift_income(SAVING, PHI, CAP, property_value_usd=1_000_000)
    assert v.high == pytest.approx(160_000) and v.expected == pytest.approx(71_875, abs=0.5)
    tiny = value_uplift_income(SAVING, PHI, CAP, property_value_usd=100_000)
    assert tiny.high == pytest.approx(16_000) and tiny.expected <= tiny.high


def test_no_saving_or_no_usable_cap_rate_gives_none():
    assert value_uplift_income(r(0, 0, 0), PHI, CAP) is None
    assert value_uplift_income(r(-5, -1, 0), PHI, CAP) is None
    assert value_uplift_income(SAVING, PHI, r(0, 0.05, 0.06, "1/year")) is None


# ---- VAL-03 ----

def test_val03_worked_example():
    v = value_uplift_home_pv(6, 25_200)
    assert (v.low, v.expected, v.high) == (0.0, 24_000.0, 24_000.0)
    cheap = value_uplift_home_pv(6, 18_000)
    assert cheap.expected == 18_000 and cheap.high == 24_000
    full = home_pv_uplift(6, 25_200)
    assert full.method == "VAL-03" and full.value_usd.expected == 24_000 and full.comp_count == 0 and full.notes


# ---- the plan's uplift ----

def test_plan_value_uplift_echoes_method_cap_rate_and_comps():
    u = plan_value_uplift(MARKET, SAVING)
    assert isinstance(u, ValueUplift) and u.method == "VAL-01" and u.comp_count == 18 and u.cap_rate == CAP
    assert u.value_usd.expected == pytest.approx(71_875, abs=0.5)
    assert any("never added" in n.lower() for n in u.notes) and any("Not an appraisal" in n for n in u.notes)
    assert any("owner pays the utilities" in n for n in u.notes)


def test_no_market_data_no_cap_rate_or_too_few_comparables_gives_none_not_a_guess():
    assert plan_value_uplift(None, SAVING) is None
    assert plan_value_uplift(MarketData(), SAVING) is None
    assert plan_value_uplift(MarketData(cap_rate=CAP, comp_count=0), SAVING) is None
    assert plan_value_uplift(MarketData(cap_rate=CAP, comp_count=MIN_COMPS - 1), SAVING) is None
    assert plan_value_uplift(MarketData(cap_rate=CAP, comp_count=MIN_COMPS), SAVING) is not None
    assert plan_value_uplift(MARKET, r(0, 0, 0)) is None


def test_the_cap_applies_when_the_floor_area_is_known():
    capped = plan_value_uplift(MARKET, SAVING, floor_area_m2=20)           # 6 500 * 20 = 130 000 -> cap 20 800
    assert capped.value_usd.high == pytest.approx(20_800) and any("capped at 16 percent" in n for n in capped.notes)
    free = plan_value_uplift(MARKET, SAVING, floor_area_m2=100_000)
    assert free.value_usd.high == pytest.approx(233_333, abs=0.5)


def test_owner_share_is_stated_when_it_is_not_one():
    u = plan_value_uplift(MARKET, SAVING, owner_share=r(0.5, 0.75, 1, "-"))
    assert u.value_usd.expected == pytest.approx(0.5 * 0.75 * 11_500 / 0.08, abs=0.5)
    assert any("Owner share" in n for n in u.notes)


def test_deterministic_and_validates():
    a, b = plan_value_uplift(MARKET, SAVING), plan_value_uplift(MARKET, SAVING)
    assert a.model_dump_json() == b.model_dump_json()
    ValueUplift.model_validate_json(a.model_dump_json())


# ---- against the office example ----

@pytest.mark.parametrize("flavor", ["office", "office_houston"])
def test_the_example_market_data_gives_an_uplift_in_the_shape_of_the_example_plan(flavor):
    bundle = PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())
    run = RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())
    want = run.plan.value_uplift
    market = bundle.costar.market
    got = plan_value_uplift(market, run.plan.total_annual_savings_usd)
    if want is None:
        assert got is None or market is None or market.comp_count >= MIN_COMPS
        return
    assert got.method == want.method and got.comp_count == want.comp_count and got.cap_rate == want.cap_rate
    assert got.value_usd.low == 0.0 == want.value_usd.low
    # the examples were built on the saving net of the O&M change, which the plan total does not show:
    # within 2 percent of the same formula on the total
    assert got.value_usd.expected == pytest.approx(want.value_usd.expected, rel=0.02)
    assert got.value_usd.high == pytest.approx(want.value_usd.high, rel=0.02)
