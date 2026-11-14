"""A28: the C-PACE scenario against the worked examples of ECO-12 and ECO-12b, the legal rules
of Texas and California, and the example measures."""
from pathlib import Path

import pytest

from backend import config
from backend.analysis.finance.cpace import cpace_scenario, level_payment, program_sir
from backend.schema import EnergyUse, MeasureResult, PropertySummary, Ranged, RunResult

EX = Path(__file__).resolve().parents[5] / "specs" / "examples"


def usd(low, expected=None, high=None, unit="USD"):
    expected = low if expected is None else expected
    return Ranged(low=low, expected=expected, high=expected if high is None else high, unit=unit)


def summary(state="TX", segment="commercial", city="Houston"):
    return PropertySummary(sid="x", name="n", segment=segment, use_type="office", address="a", city=city,
                           state=state, lat=0, lon=0, has_splat=False, has_defurnished=False,
                           pano_count=0, room_count=0, floor_count=1)


def measure(cost=100_000, savings=12_000, om_cost=500, life=25, mid="HVAC_RTU", sav_low=None, sav_high=None):
    from backend.schema import FinancialBreakdown
    f = FinancialBreakdown.model_construct(
        installed_cost_usd=usd(cost), cost_source="t", incentives=[], net_upfront_usd=usd(cost),
        annual_savings_usd=usd(savings), annual_om_change_usd=float(om_cost), useful_life_years=life,
        npv_usd=usd(0), discount_rate=0.03, electricity_escalation=0.0, gas_escalation=0.0,
        analysis_period_years=life, financing=[])
    z = Ranged(low=0, expected=0, high=0, unit="kWh")
    e = EnergyUse(electricity_kwh=z, gas_kwh=z, cost_usd=usd(savings if sav_low is None else sav_low, savings, savings if sav_high is None else sav_high),
                  co2_kg=usd(0, unit="kg"))
    return MeasureResult(measure_id=mid, title=mid, applicable=True, finance=f, savings=e)


def scenario(m=None, **kw):
    kw.setdefault("rate", 0.07)
    kw.setdefault("term_years", 20)
    kw.setdefault("in_pace_region", True)
    return cpace_scenario(m or measure(), summary(), **kw)


# ---- ECO-12 and ECO-12b worked examples ----

def test_level_payment_example():
    assert level_payment(100_000, 0.07, 20) == pytest.approx(9439.29, abs=0.01)
    assert level_payment(100_000, 0.07, 20, payments_per_year=2) == pytest.approx(4682.73, abs=0.01)
    assert level_payment(1200, 0.0, 12) == 100.0
    assert 20 * level_payment(100_000, 0.07, 20) == pytest.approx(188_785.85, abs=0.05)


def test_the_scenario_reproduces_the_worked_example():
    s = scenario()                         # P 100 000, 7 percent, 20 years, S0 12 000, O&M +500
    assert s.kind == "cpace" and s.financed_usd == 100_000 and s.rate == 0.07 and s.term_years == 20
    assert s.annual_payment_usd == pytest.approx(9439.29, abs=0.01)
    assert s.net_cashflow_year1_usd.expected == pytest.approx(2060.71, abs=0.01)
    assert s.program_sir == pytest.approx(1.218, abs=1e-3) and s.eligible
    assert any("Savings-to-debt-service ratio 1.22" in n for n in s.notes)


def test_program_sir_variant_with_cash_and_fees():
    assert program_sir(11_500, 9439.29, 20) == pytest.approx(1.218, abs=1e-3)
    assert program_sir(11_500, 8750.22, 20, cash_portion_usd=10_000) == pytest.approx(1.243, abs=1e-3)
    assert program_sir([11_500] * 20, 9439.29, 20) == pytest.approx(1.218, abs=1e-3)
    assert program_sir(0, 0, 10) == 0.0


# ---- eligibility ----

def test_a_house_or_any_residential_property_under_five_units_is_not_eligible():
    house = summary("CA", "residential", "Los Angeles")
    for units in (None, 1, 4):
        s = cpace_scenario(measure(), house, rate=0.07, term_years=20, units=units, ca_programme_confirmed=True)
        assert not s.eligible and any("five or more units" in n for n in s.notes)
    five = cpace_scenario(measure(), summary("TX", "residential"), rate=0.07, term_years=20, units=5, in_pace_region=True)
    assert five.eligible


def test_the_term_is_never_longer_than_the_useful_life():
    s = scenario(measure(life=15), term_years=25)
    assert s.term_years == 15 and any("shortened" in n for n in s.notes)
    assert scenario(measure(life=30), term_years=20).term_years == 20


def test_texas_program_sir_below_one_makes_it_ineligible_and_is_kept_apart():
    m = measure(cost=100_000, savings=4_000, om_cost=0)
    s = scenario(m)
    assert s.program_sir < 1 and not s.eligible
    assert any("does not pass" in n for n in s.notes)
    thin = scenario(measure(cost=100_000, savings=9_700, om_cost=0), rate=0.07)
    assert 1.0 <= thin.program_sir < 1.05 and thin.eligible and any("below 1.05" in n for n in thin.notes)


def test_texas_needs_a_confirmed_pace_region():
    for flag in (None, False):
        s = scenario(in_pace_region=flag)
        assert not s.eligible and any("PACE region" in n for n in s.notes)


def test_california_is_hypothetical_until_a_programme_is_confirmed():
    la = summary("CA", "commercial", "Los Angeles")
    s = cpace_scenario(measure(), la, rate=0.065, term_years=15)
    assert not s.eligible and any(n.startswith("Hypothetical") for n in s.notes)
    assert s.program_sir is not None and any("screen only" in n for n in s.notes)         # no statutory SIR test
    confirmed = cpace_scenario(measure(), la, rate=0.065, term_years=15, ca_programme_confirmed=True)
    assert confirmed.eligible


def test_california_five_percent_test():
    la = summary("CA", "commercial", "Los Angeles")
    s = cpace_scenario(measure(), la, rate=0.07, term_years=20, market_value_usd=2_000_000, annual_property_tax_usd=24_000)
    assert any("5898.15" in n and "within the limit" in n for n in s.notes)
    over = cpace_scenario(measure(), la, rate=0.07, term_years=20, market_value_usd=200_000, annual_property_tax_usd=24_000)
    assert any("over the limit" in n for n in over.notes)
    assert any("cannot be completed" in n for n in cpace_scenario(measure(), la, rate=0.07, term_years=20).notes)


def test_other_states_are_not_offered():
    ny = summary("TX", city="New York").model_copy(update={"state": "NY"})       # the contract only allows CA and TX
    s = cpace_scenario(measure(), ny, rate=0.07, term_years=20)
    assert not s.eligible and any("No C-PACE rules were read for NY" in n for n in s.notes)


def test_the_notes_carry_the_lien_and_lender_consent_statements():
    tx = scenario()
    assert any("first and prior lien" in n for n in tx.notes) and any("written consent" in n and "399.010" in n for n in tx.notes)
    ca = cpace_scenario(measure(), summary("CA", "commercial", "Los Angeles"), rate=0.07, term_years=20)
    assert any("lien on the parcel" in n for n in ca.notes) and any("not a California statutory condition" in n for n in ca.notes)


def test_without_a_quote_nothing_is_invented():
    assert config.CPACE_RATE is None and config.CPACE_TERM_YEARS is None
    s = cpace_scenario(measure(), summary(), in_pace_region=True)
    assert s.annual_payment_usd == 0 and s.rate is None and s.term_years is None and s.program_sir is None
    assert not s.eligible and any("market quotes" in n for n in s.notes)
    assert s.financed_usd == 100_000


def test_not_permanent_improvements_and_unpriced_measures_are_not_financed():
    layout = scenario(measure(cost=0, mid="LAYOUT"))
    assert not layout.eligible and layout.financed_usd == 0 and layout.rate is None
    plug = scenario(measure(cost=500, mid="PLUG_MGMT"))
    assert plug.financed_usd == 0 and any("not a permanent improvement" in n for n in plug.notes)
    unpriced = cpace_scenario(MeasureResult(measure_id="WIN_FILM", title="t", applicable=True), summary())
    assert not unpriced.eligible and unpriced.financed_usd == 0


def test_upfront_rebates_and_cash_reduce_the_financed_amount():
    assert scenario(cash_portion_usd=10_000).financed_usd == 90_000


def test_first_year_cash_flow_range_follows_the_savings_range():
    s = scenario(measure(sav_low=10_000, sav_high=14_000))
    assert s.net_cashflow_year1_usd.low < s.net_cashflow_year1_usd.expected < s.net_cashflow_year1_usd.high
    assert s.net_cashflow_year1_usd.low == pytest.approx(10_000 - 500 - 9439.29, abs=0.01)


def test_deterministic():
    assert scenario().model_dump_json() == scenario().model_dump_json()


# ---- the example measures: financed amount, payment, program SIR and year-one cash flow ----

@pytest.mark.parametrize("flavor,region", [("office_houston", True), ("office", None)])
def test_the_example_scenarios_are_reproduced(flavor, region):
    run = RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())
    checked = 0
    for m in run.measures:
        want = next((f for f in (m.finance.financing if m.finance else []) if f.kind == "cpace"), None)
        if want is None or want.rate is None:
            continue
        got = cpace_scenario(m, run.property, rate=want.rate, term_years=want.term_years, in_pace_region=region)
        assert got.financed_usd == pytest.approx(want.financed_usd, abs=0.01), m.measure_id
        assert got.annual_payment_usd == pytest.approx(want.annual_payment_usd, abs=0.02), m.measure_id
        assert got.program_sir == pytest.approx(want.program_sir, abs=2e-3), m.measure_id
        assert got.net_cashflow_year1_usd.expected == pytest.approx(want.net_cashflow_year1_usd.expected, abs=0.05), m.measure_id
        assert got.eligible == want.eligible, m.measure_id
        checked += 1
    assert checked >= 4


def test_a_property_with_no_state_is_not_offered_and_does_not_fail():
    blank = summary("TX").model_copy(update={"state": None})
    out = cpace_scenario(measure(), blank, rate=0.07, term_years=20)
    assert not out.eligible and any("No C-PACE rules were read" in n for n in out.notes)
