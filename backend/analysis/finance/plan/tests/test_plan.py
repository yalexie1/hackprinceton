"""A26: the budget algorithm of SPEC 6.5 with a fake evaluate function, and against the plans
of the example folders."""
import json
from pathlib import Path

import pytest

from backend.analysis.finance.plan import (BUDGET_WARNING, CONSENT_WARNING, NO_COST_DETAIL, PriceGroup,
                                           role_allows, select_plan)
from backend.schema import (EnergyUse, FinancialBreakdown, MeasureResult, Plan, PropertyBundle, Ranged,
                            RunResult, ValueUplift)

EX = Path(__file__).resolve().parents[5] / "specs" / "examples"


def usd(low, expected=None, high=None, unit="USD"):
    expected = low if expected is None else expected
    high = expected if high is None else high
    return Ranged(low=low, expected=expected, high=high, unit=unit)


def use(cost=0.0, co2=0.0):
    z = Ranged(low=0, expected=0, high=0, unit="kWh")
    return EnergyUse(electricity_kwh=z, gas_kwh=z, cost_usd=usd(cost, unit="USD"), co2_kg=usd(co2, unit="kg"))


def finance(net_low, net, net_high):
    return FinancialBreakdown.model_construct(
        installed_cost_usd=usd(net_low, net, net_high), cost_source="t", incentives=[],
        net_upfront_usd=usd(net_low, net, net_high), annual_savings_usd=usd(0), annual_om_change_usd=0.0,
        useful_life_years=10, npv_usd=usd(0), discount_rate=0.03, electricity_escalation=0.0,
        gas_escalation=0.0, analysis_period_years=10, financing=[])


def measure(mid, savings, cost=None, high=None, low=None, co2=None, **kw):
    cost_fields = None if cost is None else finance(cost if low is None else low, cost, cost if high is None else high)
    return MeasureResult(measure_id=mid, title=mid, applicable=kw.pop("applicable", True), finance=cost_fields,
                         savings=EnergyUse(electricity_kwh=usd(0, unit="kWh"), gas_kwh=usd(0, unit="kWh"),
                                           cost_usd=savings if isinstance(savings, Ranged) else usd(savings),
                                           co2_kg=co2 if isinstance(co2, Ranged) else usd(co2 or 0, unit="kg")), **kw)


class Fake:
    """A building whose measures are looked up by id; a hook lets savings depend on the state."""

    def __init__(self, table, depends=None):
        self.table, self.depends, self.calls = table, depends or {}, []

    def evaluate(self, mid, state):
        self.calls.append((mid, tuple(state)))
        m = self.table[mid]
        if mid in self.depends:
            m = self.depends[mid](m, state)
        return m

    @staticmethod
    def apply(state, m):
        return (*state, m.measure_id)

    @staticmethod
    def energy(state):
        return use(cost=100.0 - len(state))


def run(fake, ids, budget, role="owner_occupier", **kw):
    return select_plan(ids, role, budget, (), fake.evaluate, fake.apply, fake.energy, **kw)


def ids_of(plan):
    return [i.measure.measure_id for i in plan.selected]


# ---- the algorithm ----

def test_when_the_top_measure_is_over_budget_the_next_one_is_taken():
    fake = Fake({"PV_ROOF": measure("PV_ROOF", 900, cost=9000), "LGT_LED": measure("LGT_LED", 100, cost=300),
                 "ENV_ATTIC": measure("ENV_ATTIC", 300, cost=2000)})
    plan = run(fake, list(fake.table), 3000)
    assert ids_of(plan) == ["ENV_ATTIC", "LGT_LED"]
    assert [m.measure_id for m in plan.financeable] == ["PV_ROOF"]
    assert [(s.measure_id, s.reason) for s in plan.skipped] == [("PV_ROOF", "over_budget")]
    assert [(i.cumulative_upfront_usd, i.remaining_budget_usd) for i in plan.selected] == [(2000, 1000), (2300, 700)]


def test_savings_are_evaluated_against_the_state_so_the_order_can_change():
    # attic insulation halves the saving of LED (shared heating penalty); after it, LED drops below the thermostat
    table = {"ENV_ATTIC": measure("ENV_ATTIC", 500, cost=100),
             "LGT_LED": measure("LGT_LED", 400, cost=100), "CTRL_TSTAT": measure("CTRL_TSTAT", 300, cost=100)}
    depends = {"LGT_LED": lambda m, st: measure("LGT_LED", 100 if "ENV_ATTIC" in st else 400, cost=100)}
    fake = Fake(table, depends)
    plan = run(fake, list(table), 10_000)
    assert ids_of(plan) == ["ENV_ATTIC", "CTRL_TSTAT", "LGT_LED"]
    assert ("LGT_LED", ("ENV_ATTIC",)) in fake.calls


def test_may_exceed_budget_when_only_the_high_cost_does_not_fit():
    fake = Fake({"PV_ROOF": measure("PV_ROOF", 900, cost=900, low=700, high=1300)})
    plan = run(fake, ["PV_ROOF"], 1000)
    assert ids_of(plan) == ["PV_ROOF"] and BUDGET_WARNING in plan.selected[0].measure.warnings
    plan = run(fake, ["PV_ROOF"], 1300)
    assert BUDGET_WARNING not in plan.selected[0].measure.warnings


def test_zero_cost_measures_come_first_and_always_fit():
    fake = Fake({"LAYOUT": measure("LAYOUT", 50, cost=0.0), "PV_ROOF": measure("PV_ROOF", 900, cost=500)})
    plan = run(fake, list(fake.table), 0)
    assert ids_of(plan) == ["LAYOUT"] and [m.measure_id for m in plan.financeable] == ["PV_ROOF"]
    plan = run(fake, list(fake.table), 1000)
    assert ids_of(plan) == ["LAYOUT", "PV_ROOF"]


def test_every_measure_is_selected_financeable_or_skipped_with_a_reason():
    table = {
        "PV_ROOF": measure("PV_ROOF", 900, cost=9000),                                   # over budget
        "LGT_LED": measure("LGT_LED", 100, cost=300),                                   # selected
        "ROOF_COOL": measure("ROOF_COOL", -20, cost=400),                                # no savings
        "WIN_SHADE": measure("WIN_SHADE", 30),                                           # no cost data
        "CTRL_TSTAT": measure("CTRL_TSTAT", 0, applicable=False, not_applicable_reason="A smart thermostat is already installed."),
        "DHW_HPWH": measure("DHW_HPWH", 0, applicable=False, not_applicable_reason="Flag dhw.space is blocked."),
        "HVAC_HP": measure("HVAC_HP", 0, applicable=False, not_applicable_reason="Blocked.", params={"skip_reason": "role"}),
    }
    plan = run(Fake(table), list(table), 1000)
    seen = set(ids_of(plan)) | {m.measure_id for m in plan.financeable} | {s.measure_id for s in plan.skipped}
    assert seen == set(table)
    reasons = {s.measure_id: (s.reason, s.detail) for s in plan.skipped}
    assert reasons["ROOF_COOL"][0] == "no_savings"
    assert reasons["WIN_SHADE"] == ("no_cost_data", NO_COST_DETAIL)
    assert reasons["CTRL_TSTAT"][0] == "already_done" and reasons["DHW_HPWH"][0] == "feasibility"
    assert reasons["HVAC_HP"][0] == "role" and reasons["PV_ROOF"][0] == "over_budget"
    assert all(s.detail for s in plan.skipped)


def test_role_rules_of_spec_6_2():
    assert role_allows("PV_ROOF", "tenant") == (False, False)
    assert role_allows("PV_ROOF", "landlord") == (True, False)
    assert role_allows("ENV_AIRSEAL", "tenant") == (True, True)
    assert role_allows("LGT_LED", "tenant") == (True, False) and role_allows("LGT_CTRL", "tenant") == (True, False)
    fake = Fake({"PV_ROOF": measure("PV_ROOF", 900, cost=100), "ENV_AIRSEAL": measure("ENV_AIRSEAL", 200, cost=100)})
    plan = run(fake, list(fake.table), 10_000, role="tenant")
    assert ids_of(plan) == ["ENV_AIRSEAL"] and CONSENT_WARNING in plan.selected[0].measure.warnings
    assert [(s.measure_id, s.reason) for s in plan.skipped] == [("PV_ROOF", "role")]
    assert "PV_ROOF" not in [c[0] for c in fake.calls]                 # a role-blocked measure is never evaluated


def test_a_value_uplift_is_placed_unchanged_and_changes_nothing_else():
    fake = Fake({"LGT_LED": measure("LGT_LED", 100, cost=300), "PV_ROOF": measure("PV_ROOF", 900, cost=500)})
    uplift = ValueUplift(value_usd=usd(1000, 2000, 3000), method="VAL-01", comp_count=4)
    without, with_ = run(fake, list(fake.table), 1000), run(fake, list(fake.table), 1000, value_uplift=uplift)
    assert with_.value_uplift == uplift and without.value_uplift is None
    assert with_.model_copy(update={"value_uplift": None}) == without


def test_the_same_inputs_give_an_identical_plan_twice():
    table = {k: measure(k, s, cost=c) for k, s, c in [("LGT_LED", 100, 300), ("PV_ROOF", 900, 500), ("CTRL_TSTAT", 100, 300)]}
    a = run(Fake(table), list(table), 700).model_dump_json()
    b = run(Fake(table), list(reversed(list(table))), 700).model_dump_json()
    assert a == b


def test_totals_follow_unc02_not_the_sum_of_lows():
    pv = measure("PV_ROOF", usd(886.86, 942.08, 979.55), cost=9030, low=5762, high=11180, co2=usd(691.9, 734.97, 764.21, "kg"))
    led = measure("LGT_LED", usd(88.32, 110.4, 132.48), cost=272.4, low=144.0, high=408.6, co2=usd(64.73, 80.91, 97.09, "kg"))
    plan = run(Fake({"PV_ROOF": pv, "LGT_LED": led}), ["PV_ROOF", "LGT_LED"], 10_000)
    assert plan.total_upfront_usd.low == pytest.approx(5906.0) and plan.total_upfront_usd.high == pytest.approx(11588.6)   # correlated: linear
    assert plan.total_annual_savings_usd.expected == pytest.approx(1052.48)
    assert plan.total_annual_savings_usd.low == pytest.approx(993.02, abs=0.02)                                           # quadrature
    assert plan.total_annual_savings_usd.high == pytest.approx(1095.98, abs=0.02)
    assert plan.total_annual_savings_usd.low > 886.86 + 88.32                                                             # not the sum of lows
    assert plan.total_co2_kg.unit == "kg" and plan.total_co2_kg.low <= plan.total_co2_kg.expected <= plan.total_co2_kg.high
    assert plan.baseline_after.cost_usd.expected == 98.0                                                                 # energy(final state)


def test_an_empty_plan_has_zero_totals():
    plan = run(Fake({"PV_ROOF": measure("PV_ROOF", 900, cost=9000)}), ["PV_ROOF"], 100)
    assert plan.selected == [] and plan.total_upfront_usd.expected == 0 and plan.total_annual_savings_usd.high == 0
    Plan.model_validate(json.loads(plan.model_dump_json()))


# ---- against the plans of the example folders ----

class FromRun:
    """Replays the measures of an example run (they were already evaluated and priced)."""

    def __init__(self, run_result, plan, bundle):
        # the plan's own copies of the picked measures: a solar design stops at the budget left
        self.by_id = {m.measure_id: m for m in run_result.measures}
        self.by_id.update({i.measure.measure_id: i.measure for i in plan.selected})
        self.by_id.update({m.measure_id: m for m in plan.financeable})
        self.energy_after = plan.baseline_after
        self.pool = [i.measure.measure_id for i in plan.selected] + [m.measure_id for m in plan.financeable] \
            + [s.measure_id for s in plan.skipped]

        def ranged(key):
            return next((a.value for a in run_result.building_model.assumptions
                         if a.key == key and hasattr(a.value, "low")), None)
        self.price_group = PriceGroup.from_assumptions(
            bundle.tariff.electricity_usd_per_kwh, bundle.tariff.gas_usd_per_kwh,
            ranged("tariff.electricity_usd_per_kwh"), ranged("tariff.gas_usd_per_kwh"))

    def evaluate(self, mid, state):
        return self.by_id[mid]

    apply = staticmethod(lambda state, m: state)

    def energy(self, state):
        return self.energy_after


@pytest.mark.parametrize("flavor,name,role", [("house", "plan.json", "owner_occupier"),
                                              ("house", "plan_tenant.json", "tenant"),
                                              ("office", "plan.json", "landlord"),
                                              ("office_houston", "plan.json", "landlord")])
def test_the_example_plans_are_reproduced(flavor, name, role):
    run_result = RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())
    bundle = PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())
    want = Plan.model_validate_json((EX / flavor / name).read_text())
    if name == "plan_tenant.json":
        pytest.skip("the tenant example was built on a different measure set")
    fake = FromRun(run_result, want, bundle)
    got = select_plan(sorted(set(fake.pool)), role, want.budget_usd, (), fake.evaluate, fake.apply, fake.energy,
                      price_group=fake.price_group)
    assert ids_of(got) == [i.measure.measure_id for i in want.selected]
    assert [m.measure_id for m in got.financeable] == [m.measure_id for m in want.financeable]
    assert {(s.measure_id, s.reason) for s in got.skipped} == {(s.measure_id, s.reason) for s in want.skipped}
    assert got.total_upfront_usd.expected == pytest.approx(want.total_upfront_usd.expected, abs=0.02)
    # the savings band is UNC-02 with the price as one group: the examples follow it to the cent
    for end in ("low", "expected", "high"):
        assert getattr(got.total_annual_savings_usd, end) == pytest.approx(getattr(want.total_annual_savings_usd, end), abs=0.02), end


# ---- the shared price group (UNC-02) ----

def priced(mid, expected, low, high, kwh=None, gas_kwh=0.0, cost=100):
    kwh = expected / 0.30 if kwh is None else kwh
    m = measure(mid, usd(low, expected, high), cost=cost)
    return m.model_copy(update={"savings": m.savings.model_copy(update={
        "electricity_kwh": usd(kwh, kwh, kwh, "kWh"), "gas_kwh": usd(gas_kwh, gas_kwh, gas_kwh, "kWh")})})


def total_of(measures, group):
    table = {m.measure_id: m for m in measures}
    plan = select_plan(list(table), "owner_occupier", 10_000, (), lambda mid, st: table[mid], lambda st, m: st,
                       lambda st: use(), price_group=group)
    return plan.total_annual_savings_usd


def test_a_price_range_that_is_the_whole_range_adds_linearly_across_measures():
    # two measures whose only uncertainty is the electricity price (+-10 %): fully correlated,
    # so the plan's band is the sum of the two bands, not their root-sum-square
    a, b = priced("LGT_LED", 1000, 900, 1100), priced("CTRL_TSTAT", 500, 450, 550)
    group = PriceGroup(0.30, 0.10, 0.10)
    t = total_of([a, b], group)
    assert (t.low, t.expected, t.high) == (pytest.approx(1350.0, abs=0.01), 1500.0, pytest.approx(1650.0, abs=0.01))
    independent = total_of([a, b], None)
    assert independent.low == pytest.approx(1500 - (100 ** 2 + 50 ** 2) ** 0.5, abs=0.01)
    assert t.low < independent.low and t.high > independent.high               # correlated: wider than independent


def test_what_is_not_price_stays_independent():
    # a measure whose range is price plus its own physics: the physics part adds in quadrature
    a = priced("LGT_LED", 1000, 800, 1200)                                     # +-200 in all, 100 of it price
    b = priced("CTRL_TSTAT", 1000, 800, 1200)
    group = PriceGroup(0.30, 0.10, 0.10)
    t = total_of([a, b], group)
    own = (200 ** 2 - 100 ** 2) ** 0.5
    expected_low = 2000 - ((100 + 100) ** 2 + own ** 2 + own ** 2) ** 0.5
    assert t.low == pytest.approx(expected_low, abs=0.01) and t.high == pytest.approx(4000 - expected_low, abs=0.01)


def test_no_price_range_is_the_old_independent_total():
    a, b = priced("LGT_LED", 1000, 900, 1100), priced("CTRL_TSTAT", 500, 450, 550)
    assert total_of([a, b], PriceGroup(0.30)).model_dump() == total_of([a, b], None).model_dump()


def test_gas_price_is_in_the_same_group_and_a_penalty_moves_the_other_way():
    # electricity saved 1000 USD, gas penalty 200 USD at 0.05 USD/kWh gas; both prices +-10 %
    m = priced("HVAC_HP", 800, 700, 900, kwh=1200 / 0.30, gas_kwh=-4000)
    t = total_of([m], PriceGroup(0.30, 0.10, 0.10, 0.05, 0.10, 0.10))
    # price low: electricity part (1000) falls 100, the gas penalty (-200) shrinks 20 -> net -80;
    # price high: +100 and -20 -> +80. The range of the one measure is not wider than its own +-100
    assert (t.low, t.high) == (pytest.approx(700.0, abs=0.01), pytest.approx(900.0, abs=0.01))


def test_the_group_total_stays_ordered_and_is_deterministic():
    ms = [priced("LGT_LED", 1000, 900, 1100), priced("CTRL_TSTAT", 500, 450, 550), priced("ROOF_COOL", 300, 280, 330)]
    g = PriceGroup(0.30, 0.05, 0.15)
    t = total_of(ms, g)
    assert t.low <= t.expected <= t.high and t.model_dump() == total_of(ms, g).model_dump()


def test_price_group_from_the_models_assumption_ranges():
    g = PriceGroup.from_assumptions(0.2975, 0.0724, usd(0.2692, 0.2975, 0.3258, "USD/kWh"), None)
    assert g.electricity_rel_low == pytest.approx(0.0951, abs=1e-3) and g.electricity_rel_high == pytest.approx(0.0951, abs=1e-3)
    assert g.gas_rel_low == g.gas_rel_high == 0.0 and g.gas_usd_per_kwh == 0.0724
    assert PriceGroup.from_assumptions(0.3, None, None, None) == PriceGroup(0.3)
