"""A29 part 1: the door runs on the real modules (model, pricing, incentives, plan)."""
import json
import socket
from pathlib import Path

import pytest

from backend.analysis import api
from backend.schema import (BuildingModel, MeasureResult, Plan, PropertyBundle, RunRequest,
                            RunResult)

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"
FLAVORS = sorted(p.name for p in EX.iterdir() if (p / "run_result.json").is_file())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def load(flavor):
    bundle = PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())
    request = RunRequest.model_validate_json((EX / flavor / "run_request.json").read_text())
    return bundle, request


def model_of(bundle, request):
    observed, flags = api.observe_interior(bundle)
    return api.build_building_model(bundle, observed, flags, request.overrides)


# ---- the model ----

@pytest.mark.parametrize("flavor", FLAVORS)
def test_the_model_is_built_from_the_real_modules(flavor):
    bundle, request = load(flavor)
    model = model_of(bundle, request)
    BuildingModel.model_validate_json(model.model_dump_json())
    assert model.sid == bundle.summary.sid and model.zones and model.surfaces and model.roof_planes
    assert model.north_source == "georeference"
    for key, value in request.overrides.items():
        assert next(a for a in model.assumptions if a.key == key).source == "user"
    assert model_of(bundle, request).model_dump_json() == model.model_dump_json()      # deterministic


def test_vision_observations_reach_the_model():
    bundle, request = load("office")
    model = model_of(bundle, request)
    assert any(a.source == "vision" for a in model.assumptions)
    assert any(s.kind == "window" and s.source_opening_id is None for s in model.surfaces)   # no openings in an office scan


def test_set_assumption_returns_a_new_model():
    bundle, request = load("house")
    model = model_of(bundle, request)
    before = model.model_dump_json()
    out = api.set_assumption(model, "occupancy.count", 5.0)
    assert model.model_dump_json() == before
    assumption = next(a for a in out.assumptions if a.key == "occupancy.count")
    assert (assumption.value.low, assumption.value.expected, assumption.value.high) == (5.0, 5.0, 5.0)
    assert assumption.source == "user"


# ---- pricing and incentives ----

def evaluated(flavor, measure_id):
    bundle, request = load(flavor)
    model = model_of(bundle, request)
    return bundle, api.evaluate_measure(bundle, model, measure_id, request.role, request.desks_requested)


def test_price_measure_uses_costs_and_economics():
    bundle, measure = evaluated("house", "PV_ROOF")
    assert measure.finance is None
    priced = api.price_measure(bundle, measure)
    want = next(m for m in RunResult.model_validate_json((EX / "house" / "run_result.json").read_text()).measures
                if m.measure_id == "PV_ROOF").finance
    assert priced.finance.installed_cost_usd.expected == want.installed_cost_usd.expected == 9030.0
    assert priced.finance.npv_usd.expected == pytest.approx(want.npv_usd.expected, abs=0.5)
    assert priced.finance.sir == pytest.approx(want.sir, abs=2e-3)
    assert priced.finance.discount_rate == 0.03 and priced.finance.analysis_period_years == 25
    assert {"COST-01", "ECO-07", "INC-40"} <= set(priced.formula_ids) and set(measure.formula_ids) <= set(priced.formula_ids)
    assert api.price_measure(bundle, measure).model_dump_json() == priced.model_dump_json()


def test_a_measure_with_no_verified_cost_is_never_priced():
    bundle, measure = evaluated("house", "WIN_SHADE")
    priced = api.price_measure(bundle, measure)
    assert priced.finance is None and any("no verified cost" in w for w in priced.warnings)


def test_a_measure_that_is_not_applicable_comes_back_unchanged():
    bundle, measure = evaluated("house", "DHW_HPWH")
    assert not measure.applicable and api.price_measure(bundle, measure) == measure


def test_lookup_incentives_is_the_registry():
    house, _ = load("house")
    names = [i.name for i in api.lookup_incentives("ROOF_COOL", house.summary)]
    assert any("LADWP" in n and "cool roof" in n for n in names)
    pv = api.lookup_incentives("PV_ROOF", house.summary)
    assert any(i.status == "expired" and "25D" in i.name for i in pv)
    houston, _ = load("office_houston")
    assert any("CenterPoint" in i.name for i in api.lookup_incentives("CTRL_TSTAT", houston.summary))


# ---- the plan ----

@pytest.mark.parametrize("flavor", FLAVORS)
def test_build_plan_is_byte_identical_on_two_runs(flavor):
    bundle, request = load(flavor)
    model = model_of(bundle, request)
    first = api.build_plan(bundle, model, request).model_dump_json()
    assert api.build_plan(bundle, model, request).model_dump_json() == first
    Plan.model_validate_json(first)


@pytest.mark.parametrize("flavor", FLAVORS)
def test_every_measure_in_the_plan_lists_formula_ids_and_is_accounted_for(flavor):
    bundle, request = load(flavor)
    plan = api.build_plan(bundle, model_of(bundle, request), request)
    measures = [i.measure for i in plan.selected] + list(plan.financeable)
    assert measures and all(m.formula_ids for m in measures)
    accounted = {m.measure_id for m in measures} | {s.measure_id for s in plan.skipped}
    example = {m.measure_id for m in RunResult.model_validate_json((EX / flavor / "run_result.json").read_text()).measures}
    assert {m.measure_id for m in measures} <= accounted <= example       # nothing outside the example, nothing lost
    assert plan.value_uplift is None                               # no value module yet (A30)
    assert plan.total_upfront_usd.expected == pytest.approx(sum(i.measure.finance.net_upfront_usd.expected for i in plan.selected), abs=0.02)
    assert plan.selected[0].remaining_budget_usd <= plan.budget_usd


def test_the_house_plan_matches_the_example():
    bundle, request = load("house")
    plan = api.build_plan(bundle, model_of(bundle, request), request)
    want = Plan.model_validate_json((EX / "house" / "plan.json").read_text())
    assert [i.measure.measure_id for i in plan.selected] == [i.measure.measure_id for i in want.selected]
    assert [m.measure_id for m in plan.financeable] == [m.measure_id for m in want.financeable]
    # every skip of the example is reproduced; the engine adds the ones the example left out (HVAC_DUCT is n/a "for now")
    assert {(s.measure_id, s.reason) for s in want.skipped} <= {(s.measure_id, s.reason) for s in plan.skipped}
    assert plan.total_upfront_usd.expected == want.total_upfront_usd.expected
    assert plan.total_annual_savings_usd.expected == want.total_annual_savings_usd.expected


def test_a_tenant_never_gets_an_owner_only_measure():
    bundle, request = load("house")
    tenant = request.model_copy(update={"role": "tenant"})
    plan = api.build_plan(bundle, model_of(bundle, request), tenant)
    chosen = {i.measure.measure_id for i in plan.selected} | {m.measure_id for m in plan.financeable}
    assert not chosen & {"PV_ROOF", "ENV_ATTIC", "HVAC_HP", "ROOF_COOL", "DHW_HPWH"}
