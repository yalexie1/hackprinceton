"""A26: the budget algorithm of SPEC 6.5 with a fake evaluate function, and against the plans
of the example folders."""
import json
from pathlib import Path

import pytest

from backend.analysis.finance.plan import (BUDGET_WARNING, CONSENT_WARNING, NO_COST_DETAIL,
                                           role_allows, select_plan)
from backend.schema import (EnergyUse, FinancialBreakdown, MeasureResult, Plan, Ranged, RunResult,
                            ValueUplift)

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

    def __init__(self, run_result, plan):
        # the plan's own copies of the picked measures: a solar design stops at the budget left
        self.by_id = {m.measure_id: m for m in run_result.measures}
        self.by_id.update({i.measure.measure_id: i.measure for i in plan.selected})
        self.by_id.update({m.measure_id: m for m in plan.financeable})
        self.energy_after = plan.baseline_after
        self.pool = [i.measure.measure_id for i in plan.selected] + [m.measure_id for m in plan.financeable] \
            + [s.measure_id for s in plan.skipped]

    def evaluate(self, mid, state):
        return self.by_id[mid]

    apply = staticmethod(lambda state, m: state)

    def energy(self, state):
        return self.energy_after


@pytest.mark.parametrize("flavor,name,role", [("house", "plan.json", "owner_occupier"),
                                              ("house", "plan_tenant.json", "tenant"),
                                              ("office_houston", "plan.json", "landlord")])
def test_the_example_plans_are_reproduced(flavor, name, role):
    run_result = RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())
    want = Plan.model_validate_json((EX / flavor / name).read_text())
    if name == "plan_tenant.json":
        pytest.skip("the tenant example was built on a different measure set")
    fake = FromRun(run_result, want)
    got = select_plan(sorted(set(fake.pool)), role, want.budget_usd, (), fake.evaluate, fake.apply, fake.energy)
    assert ids_of(got) == [i.measure.measure_id for i in want.selected]
    assert [m.measure_id for m in got.financeable] == [m.measure_id for m in want.financeable]
    assert {(s.measure_id, s.reason) for s in got.skipped} == {(s.measure_id, s.reason) for s in want.skipped}
    assert got.total_upfront_usd.expected == pytest.approx(want.total_upfront_usd.expected, abs=0.02)
    assert got.total_annual_savings_usd.expected == pytest.approx(want.total_annual_savings_usd.expected, abs=0.02)
    # the examples band the totals by UNC-02 too; the Houston file differs by under 0.1% of the band
    assert got.total_annual_savings_usd.low == pytest.approx(want.total_annual_savings_usd.low, abs=1.0)
