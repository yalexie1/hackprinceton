"""A0: every door function of workplan 3.2 returns fixture data that validates, offline."""
import json
import socket
from pathlib import Path

import pytest

from backend import config
from backend.analysis import api
from backend.schema import (Assumption, BaselineResult, BuildingModel, FinancingScenario, Flag,
                            Incentive, LayoutResult, MeasureResult, Plan, PropertyBundle,
                            Question, RunRequest, SolarDesign)

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"
FLAVORS = sorted(p.name for p in EX.iterdir() if (p / "run_result.json").is_file())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def load(flavor):
    bundle = PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())
    request = RunRequest.model_validate_json((EX / flavor / "run_request.json").read_text())
    return bundle, request


def roundtrip(obj):
    """A returned model must survive its own JSON, i.e. it validates."""
    return type(obj).model_validate_json(obj.model_dump_json())


def test_every_example_folder_is_found():
    assert {"house", "office", "office_houston"} <= set(FLAVORS)


@pytest.mark.parametrize("flavor", FLAVORS)
def test_the_door_runs_end_to_end_on_the_fixture(flavor, monkeypatch):
    monkeypatch.setattr(api, "_ask_questions", lambda m, plan_fn: [])      # the real rule is tested in test_wiring
    bundle, request = load(flavor)
    assumptions, flags = api.observe_interior(bundle)
    assert assumptions and all(isinstance(a, Assumption) for a in assumptions)
    assert all(isinstance(f, Flag) for f in flags)

    model = api.build_building_model(bundle, assumptions, flags, request.overrides)
    assert roundtrip(model) == model and model.sid == bundle.summary.sid
    for key, value in request.overrides.items():
        assert next(a for a in model.assumptions if a.key == key).source == "user"

    baseline = api.run_baseline(bundle, model, request.bills)
    assert roundtrip(baseline) == baseline

    measures = []
    for measure_id in ("LGT_LED", "PV_ROOF", "HVAC_HP", "HVAC_RTU", "LAYOUT"):
        measure = api.evaluate_measure(bundle, model, measure_id, request.role, request.desks_requested)
        assert roundtrip(measure) == measure and measure.measure_id == measure_id
        assert measure.finance is None                       # savings only: SPEC 3.2
        priced = api.price_measure(bundle, measure)
        assert roundtrip(priced) == priced
        measures.append(priced)
        assert all(isinstance(i, Incentive) for i in api.lookup_incentives(measure_id, bundle.summary))
        assert isinstance(api.cpace_scenario(bundle, priced), FinancingScenario)

    plan = api.build_plan(bundle, model, request)
    assert roundtrip(plan) == plan and plan.budget_usd == request.budget_usd
    questions = api.sensitivity(bundle, model, request)
    assert all(isinstance(q, Question) for q in questions)


@pytest.mark.parametrize("flavor", FLAVORS)
def test_solar_and_layout_come_from_the_physics(flavor):
    bundle, request = load(flavor)
    model = api.build_building_model(bundle)
    baseline = api.run_baseline(bundle, model)
    design = api.design_pv(bundle, model, baseline, 10_000.0)
    assert roundtrip(design) == design and design.panel_count == len(design.panels)
    layout = api.score_desk_positions(bundle, model, 4)
    assert isinstance(layout, LayoutResult) and layout.desks_requested == 4
    assert sum(1 for c in layout.candidates if c.recommended) == 4


def test_tenant_plan_and_budget():
    bundle, request = load("house")
    model = api.build_building_model(bundle)
    tenant = request.model_copy(update={"role": "tenant", "budget_usd": 321.0})
    plan = api.build_plan(bundle, model, tenant)
    assert plan.budget_usd == 321.0
    assert {s.measure_id for s in plan.skipped if s.reason == "role"} >= {"PV_ROOF", "ENV_ATTIC", "HVAC_HP"}
    assert all(i.cumulative_upfront_usd <= 321.0 for i in plan.selected)


def test_set_assumption_collapses_a_range_and_leaves_the_input_alone():
    bundle, _ = load("house")
    model = api.build_building_model(bundle)
    before = model.model_dump_json()
    key = next(a.key for a in model.assumptions if hasattr(a.value, "low") and a.value.low < a.value.high)
    out = api.set_assumption(model, key, 7.0)
    assert model.model_dump_json() == before
    changed = next(a for a in out.assumptions if a.key == key)
    assert (changed.value.low, changed.value.expected, changed.value.high) == (7.0, 7.0, 7.0)
    assert changed.source == "user" and changed.confidence == 1.0
    assert api.set_assumption(model, "new.key", "x", source="vision").assumptions[-1].source == "vision"


def test_measure_missing_from_the_example_is_not_applicable_not_a_crash():
    bundle, request = load("house")
    model = api.build_building_model(bundle)
    out = api.evaluate_measure(bundle, model, "HVAC_ECON", request.role)
    assert out.applicable is False and out.not_applicable_reason


def test_a_property_with_no_example_gets_no_observations_and_no_error():
    """A real property has no example folder: the fallbacks that replay an example return nothing and
    the physics carries on (checkpoint 3 ran a property with none)."""
    bundle, _ = load("house")
    bad = bundle.model_copy(update={"summary": bundle.summary.model_copy(update={"sid": "nope"})})
    assert api.observe_interior(bad) == ([], [])


def test_results_are_deterministic():
    bundle, request = load("office_houston")
    model = api.build_building_model(bundle)
    a = api.build_plan(bundle, model, request).model_dump_json()
    assert a == api.build_plan(bundle, model, request).model_dump_json()


def test_config_constants():
    assert config.ASK_WIDTH == 0.40 and config.ASK_MAX == 3
    assert config.DISCOUNT_RATE_REAL == 0.030 and config.ANALYSIS_PERIOD_CAP_YEARS == 40
    assert config.SENSITIVITY_DISCOUNT_RATE == 0.07
    assert (config.ORCHESTRATOR_MODEL, config.SUBAGENT_MODEL, config.VISION_MODEL) == (
        "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
    assert config.CPACE_RATE is None and config.CPACE_TERM_YEARS is None      # placeholders
    assert config.CACHE_DIR.name == "cache"
