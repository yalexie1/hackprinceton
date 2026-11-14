"""A24: costs, useful life, O&M and incentives against the worked examples of physics 04."""
import json
from pathlib import Path
from typing import get_args

import pytest

from backend.analysis.finance.costs import (NoCostData, adjust_cost, annual_om_change, cost_fields,
                                            cost_table, counts_toward_net_upfront, incentives_for,
                                            measure_cost, net_upfront, quantity_of, registry,
                                            useful_life, utility_of)
from backend.schema import (Incentive, MeasureId, MeasureResult, PropertySummary, Ranged,
                            RunResult)

EX = Path(__file__).resolve().parents[5] / "specs" / "examples"
FLAVORS = sorted(p.name for p in EX.iterdir() if (p / "run_result.json").is_file())
ALL_IDS = list(get_args(MeasureId))


def usd(low, expected, high):
    return Ranged(low=low, expected=expected, high=high, unit="USD")


def summary(city="Los Angeles", state="CA", segment="residential"):
    return PropertySummary(sid="x", name="n", segment=segment, use_type="single_family", address="a",
                           city=city, state=state, lat=0, lon=0, has_splat=False, has_defurnished=False,
                           pano_count=0, room_count=0, floor_count=1)


def measure(measure_id, **kw):
    return MeasureResult(measure_id=measure_id, title=measure_id, applicable=True, **kw)


# ---- COST-00 to COST-02 worked examples ----

def test_cpi_adjustment_example():
    assert adjust_cost(1.91, 2019) * 10.7639 == pytest.approx(27.14, abs=0.01)


def test_attic_120_m2():
    cost, source = measure_cost("ENV_ATTIC", 120, "residential")
    assert (cost.low, cost.expected, cost.high) == (pytest.approx(2490, abs=1), pytest.approx(3257, abs=1), pytest.approx(4912, abs=1))
    assert "LBNL-2021" in source and "CPI-U adjusted to Oct 2026" in source and "27.14 USD per m2" in source


def test_heat_pump_3_tons():
    cost, _ = measure_cost("HVAC_HP", 3, "residential")
    assert (cost.low, cost.expected, cost.high) == (8004, 13416, 17415)


def test_home_pv_6_kw_and_om():
    cost, source = measure_cost("PV_ROOF", 6000, "residential")
    assert (cost.low, cost.expected, cost.high) == (16080, 25200, 31200)
    assert "not CPI-adjusted" in source
    assert annual_om_change("PV_ROOF", 6000) == pytest.approx(210, abs=0.1)
    assert annual_om_change("LGT_LED", 30) == 0.0


def test_office_pv_is_priced_small_or_large_by_size():
    small, _ = measure_cost("PV_ROOF", 99_000, "commercial")
    large, _ = measure_cost("PV_ROOF", 100_000, "commercial")
    assert small.expected / 99_000 == pytest.approx(3.35) and large.expected / 100_000 == pytest.approx(2.20)


def test_lighting_is_priced_by_sector():
    assert measure_cost("LGT_LED", 10, "residential")[0].expected == pytest.approx(90.8)
    assert measure_cost("LGT_LED", 10, "commercial")[0].expected == pytest.approx(3900)


def test_every_measure_id_has_a_cost_entry_with_a_named_source():
    by_id = {}
    for row in cost_table():
        by_id.setdefault(row["measure_id"], []).append(row)
    assert set(by_id) == set(ALL_IDS)
    assert all(row["source"].strip() for rows in by_id.values() for row in rows)
    for measure_id in ALL_IDS:
        assert useful_life(measure_id, "residential")[0] > 0


@pytest.mark.parametrize("measure_id", ["WIN_FILM", "WIN_SHADE", "PLUG_MGMT"])
def test_measures_without_a_verified_cost_are_never_given_one(measure_id):
    with pytest.raises(NoCostData) as err:
        measure_cost(measure_id, 10, "commercial")
    assert err.value.code == "no_cost_data"


def test_zero_cost_layout():
    assert measure_cost("LAYOUT", 1, "commercial")[0].expected == 0.0


def test_unverified_life_is_flagged():
    assert useful_life("HVAC_HP", "residential") == (15, "verified")
    assert useful_life("ENV_ATTIC", "residential")[1] == "unverified"
    fields = cost_fields(measure("ENV_ATTIC", params={"area_m2": 82.04}), summary())
    assert fields.notes and "unverified" in fields.notes[0]


# ---- incentives: worked examples (INC-40) ----

def only(incentives, name_part):
    return next(i for i in incentives if name_part in i.name)


def test_cool_roof_example_968_75():
    m = measure("ROOF_COOL")
    extra = {"roof_area_m2": 150, "sri_3yr": 86, "roof_slope": "low"}
    unconfirmed = only(incentives_for(m, summary(), extra=extra), "cool roof")
    assert unconfirmed.eligibility == "needs_confirmation"
    assert (unconfirmed.amount_usd.low, unconfirmed.amount_usd.expected) == (0, 0)
    assert unconfirmed.amount_usd.high == pytest.approx(968.75, abs=0.01)
    confirmed = only(incentives_for(m, summary(), extra={**extra, "confirmed": True}), "cool roof")
    assert confirmed.eligibility == "confirmed" and confirmed.amount_usd.expected == pytest.approx(968.75, abs=0.01)
    low_sri = only(incentives_for(m, summary(), extra={**extra, "sri_3yr": 70}), "cool roof")
    assert low_sri.eligibility == "not_eligible"


def test_office_hvac_per_kwh_example_24000():
    m = measure("HVAC_RTU", savings={"electricity_kwh": Ranged(low=30000, expected=40000, high=50000, unit="kWh"),
                                     "gas_kwh": Ranged(low=0, expected=0, high=0, unit="kWh"),
                                     "cost_usd": usd(0, 0, 0), "co2_kg": Ranged(low=0, expected=0, high=0, unit="kg")})
    boss = only(incentives_for(m, summary(segment="commercial"), extra={"confirmed": True}), "BOSS")
    assert (boss.amount_usd.low, boss.amount_usd.expected, boss.amount_usd.high) == (18000, 24000, 30000)
    unconfirmed = only(incentives_for(m, summary(segment="commercial")), "BOSS")
    assert unconfirmed.eligibility == "needs_confirmation" and unconfirmed.amount_usd.expected == 0


def test_houston_home_pv_example_and_cap():
    def rebate(kw):
        m = measure("PV_ROOF", solar={"system_kw_dc": kw, "panel_count": 1, "panels": [], "annual_kwh": Ranged(low=0, expected=0, high=0, unit="kWh"),
                                      "electrical": {"key": "e", "status": "unknown", "message": "m"},
                                      "structural": {"key": "s", "status": "unknown", "message": "m"}})
        return only(incentives_for(m, summary("Houston", "TX")), "Residential Solar").amount_usd.expected
    assert rebate(8) == 1080 and rebate(20) == 2025


def test_commercial_pv_credit_example_33000():
    m = measure("PV_ROOF")
    cost = usd(110000, 110000, 110000)
    s = summary("Los Angeles", "CA", "commercial")
    credit = only(incentives_for(m, s, cost=cost), "48E")
    assert credit.status == "verified" and credit.eligibility == "needs_confirmation"
    assert (credit.amount_usd.low, credit.amount_usd.expected, credit.amount_usd.high) == (0, 0, 33000)
    sure = only(incentives_for(m, s, cost=cost, extra={"owner_is_business": True, "pfe_compliant": True,
                                                       "placed_in_service_by_2027": True}), "48E")
    assert sure.eligibility == "confirmed" and sure.amount_usd.expected == 33000


def test_attic_rebate_example_645_83():
    m = measure("ENV_ATTIC")
    extra = {"area_m2": 120, "installed_r_value": 38, "confirmed": True}
    got = only(incentives_for(m, summary(), extra=extra), "Attic Insulation Rebate Program (")
    assert got.amount_usd.expected == pytest.approx(645.83, abs=0.01)
    at_19 = only(incentives_for(m, summary(), extra={**extra, "installed_r_value": 19}), "Attic Insulation Rebate Program (")
    assert at_19.amount_usd.expected == pytest.approx(0.30 * 120 * 10.7639, abs=0.01)
    extra_launch = only(incentives_for(m, summary(), extra=extra), "Launch Special")
    assert extra_launch.status == "unverified"


def test_heat_pump_tiers_and_floor():
    m = measure("HVAC_HP", params={"capacity_tons": 3, "seer2": 16.5, "hspf2": 8.2})
    assert only(incentives_for(m, summary()), "heat pump HVAC").amount_usd.expected == 3150     # tier 1 050 per ton
    below = measure("HVAC_HP", params={"capacity_tons": 3, "seer2": 15.0, "hspf2": 8.2})
    assert only(incentives_for(below, summary()), "heat pump HVAC").eligibility == "not_eligible"
    houston = only(incentives_for(m, summary("Houston", "TX")), "HVAC replacement")
    assert houston.kind == "upfront_rebate" and houston.amount_usd.expected == 200


# ---- registry rules ----

def test_federal_entries_state_their_status_and_never_enter_a_total():
    fed = [e for e in registry() if e["region"] == "US"]
    assert fed and {e["status"] for e in fed} <= {"expired", "verified"}
    m = measure("PV_ROOF")
    cost = usd(10000, 10000, 10000)
    for seg in ("residential", "commercial"):
        incentives = incentives_for(m, summary(segment=seg), cost=cost,
                                    extra={"owner_is_business": True, "pfe_compliant": True, "placed_in_service_by_2027": True})
        federal = [i for i in incentives if "Federal" in i.name]
        assert federal and all(i.kind in ("tax_credit", "tax_deduction") for i in federal)
        assert not any(counts_toward_net_upfront(i) for i in federal)
    expired = only(incentives_for(m, summary()), "25D")
    assert expired.status == "expired" and expired.eligibility == "not_eligible" and expired.amount_usd.high == 0


def test_net_upfront_subtracts_verified_upfront_rebates_only():
    cost = usd(1000, 2000, 3000)

    def inc(kind, status="verified", eligibility="confirmed", amount=500):
        return Incentive(name=f"{kind}-{status}", kind=kind, amount_usd=usd(amount, amount, amount),
                         status=status, eligibility=eligibility, citation="c")
    net = net_upfront(cost, [inc("upfront_rebate"), inc("rebate_after_install"), inc("tax_credit"),
                             inc("tax_deduction"), inc("performance_payment"),
                             inc("upfront_rebate", status="unverified"),
                             inc("upfront_rebate", status="expired", eligibility="not_eligible")])
    assert (net.low, net.expected, net.high) == (500, 1500, 2500)
    assert net_upfront(cost, [inc("upfront_rebate", amount=9999)]).expected == 0        # never below zero


def test_utility_follows_the_city_not_the_state():
    assert utility_of(summary()) == "LADWP" and utility_of(summary("Houston", "TX")) == "CenterPoint"
    assert utility_of(summary("Pasadena", "CA")) is None
    pasadena = incentives_for(measure("ROOF_COOL"), summary("Pasadena", "CA"), extra={"roof_area_m2": 10})
    assert not any("LADWP" in i.name for i in pasadena)


def test_every_registry_entry_cites_a_source_and_date():
    for e in registry():
        assert e["citation"].strip() and e["date_checked"] and e["status"] in ("verified", "unverified", "expired")
        assert e["kind"] in ("upfront_rebate", "rebate_after_install", "tax_credit", "tax_deduction", "performance_payment")


def test_missing_quantity_is_reported_not_guessed():
    with pytest.raises(NoCostData) as err:
        cost_fields(measure("ENV_AIRSEAL"), summary())
    assert err.value.code == "no_quantity"
    fields = cost_fields(measure("ENV_AIRSEAL"), summary(), quantity=383.42)
    assert fields.installed_cost_usd.expected == pytest.approx(7.67 * 383.42, abs=0.01)


# ---- cross-check against the priced example measures ----

@pytest.mark.parametrize("flavor", FLAVORS)
def test_costs_match_the_example_measures(flavor):
    run = RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())
    checked = 0
    for m in run.measures:
        if not m.finance or quantity_of(m) is None:
            continue
        fields = cost_fields(m, run.property)
        assert fields.installed_cost_usd.expected == pytest.approx(m.finance.installed_cost_usd.expected, abs=0.02), m.measure_id
        assert fields.useful_life_years == m.finance.useful_life_years, m.measure_id
        assert fields.annual_om_change_usd == pytest.approx(m.finance.annual_om_change_usd, abs=0.02), m.measure_id
        assert fields.net_upfront_usd.expected <= fields.installed_cost_usd.expected
        checked += 1
    assert checked >= 3


def test_results_are_deterministic():
    m = measure("HVAC_HP", params={"capacity_tons": 3, "seer2": 16.5, "hspf2": 8.2})
    a, b = cost_fields(m, summary()), cost_fields(m, summary())
    assert a == b


def test_a_per_kwh_incentive_is_never_negative_when_the_measure_costs_energy():
    m = measure("HVAC_RTU", savings={"electricity_kwh": Ranged(low=-900, expected=-400, high=-100, unit="kWh"),
                                     "gas_kwh": Ranged(low=0, expected=0, high=0, unit="kWh"),
                                     "cost_usd": usd(-90, -40, -10), "co2_kg": Ranged(low=0, expected=0, high=0, unit="kg")})
    for confirmed in ({}, {"confirmed": True}):
        boss = only(incentives_for(m, summary(segment="commercial"), extra=confirmed), "BOSS")
        assert boss.amount_usd.low == boss.amount_usd.expected == boss.amount_usd.high == 0.0
