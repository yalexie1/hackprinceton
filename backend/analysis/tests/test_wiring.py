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
    assert measure.finance is None and measure.solar is not None
    priced = api.price_measure(bundle, measure)
    watts = measure.solar.system_kw_dc * 1000
    assert priced.finance.installed_cost_usd.expected == pytest.approx(4.20 * watts, abs=0.01)     # COST-01, residential PV
    assert priced.finance.annual_om_change_usd == pytest.approx(35.01 * measure.solar.system_kw_dc, abs=0.01)
    assert priced.finance.discount_rate == 0.03 and priced.finance.analysis_period_years == 25
    assert priced.finance.npv_usd.low <= priced.finance.npv_usd.expected <= priced.finance.npv_usd.high
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
    selected = {i.measure.measure_id for i in plan.selected}
    financeable = {m.measure_id for m in plan.financeable}
    skipped = {s.measure_id for s in plan.skipped}
    assert not selected & skipped and financeable <= skipped              # financeable measures are skipped as over budget
    flow = api.engine.flow_of(bundle.summary)
    assert selected | skipped <= {m for m, e in api.engine.CATALOGUE.items() if flow in e.flows}
    assert plan.total_upfront_usd.expected == pytest.approx(sum(i.measure.finance.net_upfront_usd.expected for i in plan.selected), abs=0.02)
    assert plan.selected[0].remaining_budget_usd <= plan.budget_usd


def test_the_house_plan_keeps_the_examples_solar_design_on_the_real_physics():
    bundle, request = load("house")
    plan = api.build_plan(bundle, model_of(bundle, request), request)
    ids = [i.measure.measure_id for i in plan.selected]
    paid = [i for i in ids if i != "LAYOUT"]                                    # the zero-cost desk layout comes first
    assert paid[:2] == ["PV_ROOF", "LGT_LED"]                                   # the example's picks, in its order
    pv = next(i.measure for i in plan.selected if i.measure.measure_id == "PV_ROOF")
    assert pv.solar.system_kw_dc == 2.15 and pv.solar.panel_count == 5          # sized to the budget, as in the example
    assert pv.savings.cost_usd.expected == pytest.approx(942.08, rel=0.2)
    assert plan.selected[-1].cumulative_upfront_usd <= plan.budget_usd
    assert {"ENV_ATTIC", "HVAC_HP"} <= {m.measure_id for m in plan.financeable}   # the example's financeable pair


def test_a_tenant_never_gets_an_owner_only_measure():
    bundle, request = load("house")
    tenant = request.model_copy(update={"role": "tenant"})
    plan = api.build_plan(bundle, model_of(bundle, request), tenant)
    chosen = {i.measure.measure_id for i in plan.selected} | {m.measure_id for m in plan.financeable}
    assert not chosen & {"PV_ROOF", "ENV_ATTIC", "HVAC_HP", "ROOF_COOL", "DHW_HPWH"}


# ---- value uplift (A30) ----

def plan_of(flavor):
    bundle, request = load(flavor)
    return bundle, api.build_plan(bundle, model_of(bundle, request), request)


@pytest.mark.parametrize("flavor", ["office", "office_houston"])
def test_an_office_plan_carries_the_capitalised_saving(flavor):
    bundle, plan = plan_of(flavor)
    u = plan.value_uplift
    assert u is not None and u.method == "VAL-01" and u.comp_count == bundle.costar.market.comp_count
    assert u.value_usd.low == 0.0 and u.value_usd.expected <= u.value_usd.high and u.cap_rate == bundle.costar.market.cap_rate
    assert all(i.measure.value_uplift is None for i in plan.selected)
    # shown beside the totals, never inside them
    assert plan.total_annual_savings_usd.expected == pytest.approx(sum(i.measure.savings.cost_usd.expected for i in plan.selected), abs=0.02)


def test_without_market_data_the_plan_has_no_uplift():
    bundle, request = load("office")
    bare = bundle.model_copy(update={"costar": bundle.costar.model_copy(update={"market": None})})
    assert api.build_plan(bare, model_of(bare, request), request).value_uplift is None
    few = bundle.costar.market.model_copy(update={"comp_count": 3})
    few_bundle = bundle.model_copy(update={"costar": bundle.costar.model_copy(update={"market": few})})
    assert api.build_plan(few_bundle, model_of(few_bundle, request), request).value_uplift is None


def test_a_home_carries_its_uplift_on_owned_rooftop_solar_only():
    bundle, plan = plan_of("house")
    assert plan.value_uplift is None
    pv = next(i.measure for i in plan.selected if i.measure.measure_id == "PV_ROOF")
    assert pv.value_uplift.method == "VAL-03" and pv.value_uplift.value_usd.low == 0.0
    assert pv.value_uplift.value_usd.high == pytest.approx(4000 * pv.solar.system_kw_dc)
    assert all(i.measure.value_uplift is None for i in plan.selected if i.measure.measure_id != "PV_ROOF")


# ---- A29 part 3: the physics behind the door ----

def clear_caches():
    api._SIM_CACHE.clear()
    api._DESIGN_CACHE.clear()
    api._CLIMATE_CACHE.clear()


def test_the_baseline_is_the_real_chain_with_a_range():
    bundle, request = load("house")
    model = model_of(bundle, request)
    base = api.run_baseline(bundle, model)
    a = base.annual
    for r in (a.electricity_kwh, a.gas_kwh, a.cost_usd, a.co2_kg):
        assert r.low <= r.expected <= r.high
    assert a.cost_usd.low < a.cost_usd.expected < a.cost_usd.high                   # not a point
    assert len(base.monthly_electricity_kwh) == 12 and len(base.monthly_gas_kwh) == 12
    assert sum(base.end_use_kwh.values()) == pytest.approx(a.electricity_kwh.expected + a.gas_kwh.expected, rel=1e-3)
    assert base.peak_cooling_w > 0 and base.peak_heating_w > 0 and not base.calibrated_to_bills
    assert api.run_baseline(bundle, model).model_dump_json() == base.model_dump_json()


def test_load_driving_assumptions_widen_the_baseline_range():
    bundle, request = load("house")
    model = model_of(bundle, request)
    pinned = model
    for key in api._LOAD_KEYS:
        if any(a.key == key for a in pinned.assumptions):
            pinned = api.set_assumption(pinned, key, next(a.value.expected for a in pinned.assumptions if a.key == key)
                                        if not isinstance(next(a.value for a in pinned.assumptions if a.key == key), str) else 0)
    wide, narrow = api.run_baseline(bundle, model).annual.gas_kwh, api.run_baseline(bundle, pinned).annual.gas_kwh
    assert (wide.high - wide.low) > (narrow.high - narrow.low)


def test_the_sample_year_is_used_when_the_site_file_is_not_cached():
    clear_caches()
    bundle, _ = load("office_houston")
    hours, weather, notes = api._climate(bundle)
    assert len(hours.temp_c) == 8760 and notes and "example year typical_year_hourly_houston.csv" in notes[0]
    assert float(hours.temp_c.mean()) > 18                                           # Houston, not Los Angeles


def test_design_pv_stops_at_the_budget_and_reproduces_the_example_sizing():
    bundle, request = load("office")
    model = model_of(bundle, request)
    base = api.run_baseline(bundle, model)
    small = api.design_pv(bundle, model, base, 6280.0)
    assert small.panel_count == 4 and small.system_kw_dc == pytest.approx(1.72)       # the example: 4 modules, 1.72 kW
    assert api._pv_installed_cost(bundle, small.system_kw_dc * 1000) <= 6280.0
    free = api.design_pv(bundle, model, base)                                          # no budget: roof or consumption
    assert free.panel_count > small.panel_count and free.annual_kwh.low <= free.annual_kwh.expected <= free.annual_kwh.high
    assert all(p.annual_kwh > 0 for p in small.panels)


def test_pv_roof_is_evaluated_by_the_engine_and_skips_when_the_roof_has_solar():
    bundle, request = load("house")
    model = model_of(bundle, request)
    pv = api.evaluate_measure(bundle, model, "PV_ROOF", request.role)
    assert pv.applicable and pv.solar is not None and pv.savings.cost_usd.expected > 0 and pv.finance is None
    assert {"PV-06", "LAY-03"} <= set(pv.formula_ids)
    tenant = api.evaluate_measure(bundle, model, "PV_ROOF", "tenant")
    assert not tenant.applicable and tenant.params["skip_reason"] == "role"


class without_plugin:
    """Take a plug-in off the engine for a moment, as if its package had not landed."""
    def __init__(self, measure_id):
        self.measure_id = measure_id

    def __enter__(self):
        self.saved = api.engine.REGISTRY.plugins.pop(self.measure_id)

    def __exit__(self, *exc):
        api.engine.REGISTRY.plugins[self.measure_id] = self.saved


def test_a_registered_measure_runs_on_the_engine_and_the_rest_replay_the_example():
    office, request = load("office")
    model = model_of(office, request)
    with without_plugin("LAYOUT"):                                                  # as if A23 had not landed
        stubbed = api.evaluate_measure(office, model, "LAYOUT", request.role)
        assert any("not registered yet" in w for w in stubbed.warnings)
    real = api.evaluate_measure(office, model, "LAYOUT", request.role)
    assert real.applicable and not any("not registered yet" in w for w in real.warnings)
    ctrl = api.evaluate_measure(office, model, "LGT_CTRL", request.role)
    assert ctrl.applicable and ctrl.formula_ids and ctrl.savings.electricity_kwh.expected > 0
    attic = api.evaluate_measure(*load("house")[:1], model_of(*load("house")), "ENV_ATTIC", "owner_occupier")
    assert attic.applicable and not any("not registered yet" in w for w in attic.warnings)


def test_a_plugin_that_lands_replaces_the_example_by_itself():
    office, request = load("office")
    model = model_of(office, request)
    registry = api.engine.REGISTRY

    def describe(b, m, changed, before, options):
        return MeasureResult(measure_id="LAYOUT", title="Desk layout", applicable=True,
                             params={"grid_m": 0.5}, formula_ids=["LAY-01"])
    with without_plugin("LAYOUT"):
        before = api.evaluate_measure(office, model, "LAYOUT", request.role)
        assert any("not registered yet" in w for w in before.warnings)
        api.engine.register("LAYOUT", change=lambda b, m: m.model_copy(deep=True), describe=describe)
        out = api.evaluate_measure(office, model, "LAYOUT", request.role)
        assert not any("not registered yet" in w for w in out.warnings) and out.formula_ids[0] == "LAY-01"


def test_sensitivity_is_the_real_rule_once_the_core_plugins_are_registered(monkeypatch):
    bundle, request = load("house")
    model = model_of(bundle, request)
    calls = []
    monkeypatch.setattr(api, "_ask_questions", lambda m, plan_fn: calls.append(m) or [])
    assert api.sensitivity(bundle, model, request) == [] and len(calls) == 1          # envelope, lighting, heat pump: all registered
    registry = api.engine.REGISTRY
    saved = registry.plugins.pop("HVAC_HP")                                           # as if a core package were missing
    try:
        assert [q.id for q in api.sensitivity(bundle, model, request)] == ["q_service_amps"]    # the example's question
        assert len(calls) == 1
    finally:
        registry.plugins["HVAC_HP"] = saved


def test_the_real_ask_rule_runs_on_the_house_in_reasonable_time():
    import time
    bundle, request = load("house")
    started = time.time()
    questions = api.sensitivity(bundle, model_of(bundle, request), request)
    assert time.time() - started < 120
    assert all(q.choices[-1].value is None for q in questions)                        # every question ends in "I don't know"


def test_observe_interior_uses_the_vision_reader_once_a_model_client_is_given(monkeypatch):
    bundle, _ = load("house")
    seen = []
    monkeypatch.setattr(api, "_vision_interior", lambda b, ask, get, **kw: seen.append((ask, get)) or ([], []))
    try:
        api.set_vision(ask_model=lambda *a: "{}", get_bytes=lambda p: b"")
        assert api.observe_interior(bundle) == ([], []) and len(seen) == 1
    finally:
        api.set_vision(None, None)
    assert api.observe_interior(bundle)[0]                                            # back to the example's observations


@pytest.mark.parametrize("flavor", FLAVORS)
def test_the_plan_reproduces_exactly_from_a_cold_start(flavor):
    bundle, request = load(flavor)
    clear_caches()
    first = api.build_plan(bundle, model_of(bundle, request), request).model_dump_json()
    clear_caches()
    assert api.build_plan(bundle, model_of(bundle, request), request).model_dump_json() == first


def test_baseline_after_is_a_simulation_of_the_changed_building():
    bundle, request = load("office")
    model = model_of(bundle, request)
    plan = api.build_plan(bundle, model, request)
    before = api.run_baseline(bundle, model).annual
    assert plan.baseline_after.electricity_kwh.expected < before.electricity_kwh.expected


# ---- A29 part 4: desks (A23 on A5), roof masks (A12), shading (A15), flags (A8) ----

@pytest.mark.parametrize("flavor", ["office", "office_houston"])
def test_the_layout_measure_places_desks_with_the_daylight_scorer(flavor):
    bundle, request = load(flavor)
    model = model_of(bundle, request)
    m = api.evaluate_measure(bundle, model, "LAYOUT", request.role, 4)
    assert m.applicable and len(m.anchors) == 4 and not any("not registered yet" in w for w in m.warnings)
    assert {"LCT-02", "DAY-09"} <= set(m.formula_ids) or "LCT-02" in m.formula_ids
    assert m.layout.desks_requested == 4 and sum(1 for c in m.layout.candidates if c.recommended) == 4
    assert m.savings.electricity_kwh.low <= m.savings.electricity_kwh.expected <= m.savings.electricity_kwh.high
    assert m.finance is None
    again = api.evaluate_measure(bundle, model, "LAYOUT", request.role, 4)
    assert again.model_dump_json() == m.model_dump_json()


def test_a_position_the_daylight_model_refuses_is_never_recommended():
    bundle, request = load("office")
    layout = api.score_desk_positions(bundle, model_of(bundle, request), 4)
    refused = [c for c in layout.candidates if any("refused" in w for w in c.warnings)]
    recommended = [c for c in layout.candidates if c.recommended]
    assert recommended and not set(map(id, refused)) & set(map(id, recommended))
    assert all(c.daylight > 0 for c in recommended)


def test_layout_is_part_of_the_plan_for_a_home_too():
    bundle, request = load("house")
    plan = api.build_plan(bundle, model_of(bundle, request), request)
    assert "LAYOUT" in [i.measure.measure_id for i in plan.selected]


def test_tree_detections_lower_the_usable_roof_area():
    from backend.schema import VexcelDetection
    bundle, request = load("house")
    plain = model_of(bundle, request)
    plane = plain.roof_planes[0]
    tree = VexcelDetection(label="tree", confidence=0.9, image_id="ortho-1", bbox_wkt=plane.polygon_wkt,
                           mask_wkt=plane.polygon_wkt, mask_area_m2=plane.area_m2 * 0.5)
    treed = bundle.model_copy(update={"vexcel": bundle.vexcel.model_copy(update={
        "detections": [*bundle.vexcel.detections, tree]})})
    after = model_of(treed, request)
    assert sum(p.usable_area_m2 for p in after.roof_planes) < sum(p.usable_area_m2 for p in plain.roof_planes)


def test_panels_carry_a_shading_loss_and_a_parametric_roof_keeps_the_default_allowance():
    bundle, request = load("house")
    model = model_of(bundle, request)
    design = api.design_pv(bundle, model, api.run_baseline(bundle, model), 10_000.0)
    assert design.panels and all(p.shading_loss_fraction == pytest.approx(0.03) for p in design.panels)


def test_the_vision_read_is_asked_for_the_room_fallback_and_its_flags_come_through(monkeypatch):
    from backend.schema import Flag
    bundle, _ = load("house")
    seen = {}
    flag = Flag(key="electrical.service", status="likely_upgrade", message="two-prong outlets")

    def reader(b, ask, get, **kw):
        seen.update(kw)
        return [], [flag]
    monkeypatch.setattr(api, "_vision_interior", reader)
    try:
        api.set_vision(ask_model=lambda *a: "{}", get_bytes=lambda p: b"")
        assert api.observe_interior(bundle) == ([], [flag])
    finally:
        api.set_vision(None, None)
    assert seen == {"room_fallback": True}
