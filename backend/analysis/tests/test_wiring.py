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
    bundle, request = load("office_houston")
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
    api._ZONE_CACHE.clear()
    api._EVAL_CACHE.clear()
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


@pytest.fixture
def isolated_climate_cache():
    """The climate cache belongs to the test: it starts empty and leaves nothing behind."""
    clear_caches()
    yield
    clear_caches()


def test_the_sample_year_is_used_when_the_site_file_is_not_cached(isolated_climate_cache, monkeypatch):
    """Whatever is in data/cache on this machine (a live run writes the site file there), the site
    file is treated as absent, so the test means the same on a clean checkout and after a live run."""
    def absent(site, root=None):
        raise FileNotFoundError(site.weather_path)
    monkeypatch.setattr(api, "read_site_weather", absent)
    bundle, _ = load("office_houston")
    hours, weather, notes = api._climate(bundle)
    assert len(hours.temp_c) == 8760 and notes and "example year typical_year_hourly_houston.csv" in notes[0]
    assert float(hours.temp_c.mean()) > 18                                           # Houston, not Los Angeles


def test_the_site_file_is_used_without_a_note_when_it_is_cached(isolated_climate_cache, monkeypatch):
    from backend.analysis.physics.climate import read_weather
    sample = api._WEATHER_SAMPLES / api._SAMPLE_FILE["TX"]
    bundle, _ = load("office_houston")
    site = bundle.climate
    monkeypatch.setattr(api, "read_site_weather",
                        lambda s, root=None: read_weather(sample, s.timezone, s.weather_time_convention, source="site file"))
    hours, weather, notes = api._climate(bundle)
    assert notes == () and weather.source == "site file" and len(hours.temp_c) == 8760


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
    monkeypatch.setattr(api, "_ask_questions", lambda m, plan_fn, **kw: calls.append(m) or [])
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
    assert plan.baseline_after.electricity_kwh.expected <= round(before.electricity_kwh.expected, 2)   # plan figures are rounded to 2 dp; LAYOUT + PV change no load (#308)


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


# ---- a missing state never crashes pricing ----

def without_state(bundle, address=None):
    summary = bundle.summary.model_copy(update={"state": None, **({"address": address} if address else {})})
    return bundle.model_copy(update={"summary": summary})


def test_the_state_is_read_from_the_address_then_the_timezone():
    assert api._state_from("5836 La Mirada Ave, Los Angeles, CA 90038") == "CA"
    assert api._state_from("2100 West Loop S Fwy, Houston, TX 77027") == "TX"
    assert api._state_from("12 Main St, Austin, Texas") == "TX"
    assert api._state_from("1 Nowhere Rd", "America/Chicago") == "TX"
    assert api._state_from("1 Nowhere Rd", "America/Los_Angeles") == "CA"
    assert api._state_from("1 Nowhere Rd", None) is None
    assert api._state_from("Cascade Ct, Santa Fe, NM", "America/Denver") is None


@pytest.mark.parametrize("flavor", ["house", "office_houston"])
def test_a_property_with_no_state_is_priced_like_the_same_property_with_one(flavor):
    bundle, request = load(flavor)
    blank = without_state(bundle)
    assert blank.summary.state is None and api._state_from(blank.summary.address, blank.climate.timezone) == bundle.summary.state
    model = model_of(bundle, request)
    known = api.build_plan(bundle, model, request)
    unknown = api.build_plan(blank, model, request)
    assert unknown.model_dump_json() == known.model_dump_json()          # the address says the state


def test_with_no_state_to_be_found_pricing_still_runs_without_escalation():
    bundle, request = load("house")
    nowhere = without_state(bundle, address="1 Nowhere Rd")
    nowhere = nowhere.model_copy(update={"climate": nowhere.climate.model_copy(update={"timezone": "America/Denver"})})
    model = model_of(bundle, request)
    measure = api.evaluate_measure(nowhere, model, "LGT_LED", request.role)
    priced = api.price_measure(nowhere, measure)
    assert priced.finance is not None and priced.finance.electricity_escalation == 0.0 == priced.finance.gas_escalation
    assert any("State unknown" in n for n in priced.finance.financing[0].notes)
    plan = api.build_plan(nowhere, model, request)                      # the whole plan, no exception
    assert plan.selected
    assert api.lookup_incentives("LGT_LED", nowhere.summary) is not None
    assert api.cpace_scenario(nowhere, priced).eligible is False        # no state, no C-PACE rules to apply


# ---- the ask rule on the real physics (checkpoint 3) ----

ASK = EX / "ask"


def ask_model(name):
    return BuildingModel.model_validate_json((ASK / f"building_model_{name}.json").read_text())


def test_the_ask_rule_fires_on_the_wide_fixture_and_not_on_the_narrow_one():
    from backend.analysis.finance.sensitivity import sensitivity as ask
    bundle, request = load("house")
    wide, narrow = ask_model("wide"), ask_model("narrow")
    questions = ask(wide, api._responsive_plan(bundle, wide, request))
    assert questions and questions[0].choices[-1].value is None             # an "I don't know" with no value
    assert ask(narrow, api._responsive_plan(bundle, narrow, request)) == []


def test_a_moved_assumption_really_moves_the_plan():
    """A27 collapses the value in the assumption list only; the door rebuilds the model so the walls,
    the systems and the zones follow. Without that every variant plan was the same plan."""
    bundle, request = load("house")
    base = model_of(bundle, request)
    plan_of_model = api._responsive_plan(bundle, base, request)
    from backend.analysis.finance.sensitivity import with_value
    key = "infiltration.ach50"
    leaky = plan_of_model(with_value(base, key, 30.0))
    tight = plan_of_model(with_value(base, key, 6.0))
    assert leaky.total_annual_savings_usd.expected != tight.total_annual_savings_usd.expected
    assert plan_of_model(base).model_dump_json() == plan_of_model(base).model_dump_json()


# ---- the caches return what a fresh run would ----

@pytest.mark.parametrize("flavor", ["house", "office"])
def test_a_measure_that_leaves_the_zone_inputs_alone_shares_the_loads_of_its_parent(flavor):
    import numpy as np
    bundle, request = load(flavor)
    base = model_of(bundle, request)
    hours, weather, _ = api._climate(bundle)
    from backend.analysis.physics.systems import calendar_from_stamps
    cal = calendar_from_stamps(hours.stamps, bundle.climate.weather_time_convention)
    same, different = 0, 0
    for mid in api.engine.REGISTRY.registered():
        skip, _ = api.engine.applicability(bundle, base, mid, request.role)
        if skip is not None:
            continue
        changed = api.engine.apply_measure(bundle, base, mid)
        if api._zone_key(bundle, changed) == api._zone_key(bundle, base):
            same += 1
            cached = api._hourly_loads(bundle, changed, hours, weather, cal)
            fresh = api._zone_run(bundle, changed, hours, weather, cal)[0]
            assert np.array_equal(cached.heating_need_w, fresh.heating_need_w), mid
            assert np.array_equal(cached.cooling_need_w, fresh.cooling_need_w), mid
        else:
            different += 1
    assert same and different                                              # neither branch is vacuous


def test_the_layout_card_is_the_same_whether_or_not_it_comes_from_the_cache():
    bundle, request = load("office")
    base = model_of(bundle, request)
    before = api.run_baseline(bundle, base)
    fresh = api.layout.describe(bundle, base, base, before, {"desks_requested": 4},
                                score_point=api._desk_scorer(bundle, base))
    api._LAYOUT_CACHE.clear()
    cached = api._describe_layout(bundle, base, base, before, {"desks_requested": 4})
    assert cached.model_dump_json() == fresh.model_dump_json()
    # what cannot move a desk: the solar array, the flags, the roof, the water heater
    shuffled = base.model_copy(update={"flags": list(reversed(base.flags)),
                                       "roof_planes": list(reversed(base.roof_planes))})
    pv = api.engine.apply_measure(bundle, base, "PV_ROOF")
    for other in (shuffled, pv):
        assert api._layout_key(bundle, other, 4) == api._layout_key(bundle, base, 4)
        assert api._describe_layout(bundle, base, other, before, {"desks_requested": 4}).model_dump_json() \
            == fresh.model_dump_json()
    # what can: plug-load gains change the zone temperatures the comfort model reads
    skip, _ = api.engine.applicability(bundle, base, "PLUG_MGMT", request.role)
    if skip is None:
        changed = api.engine.apply_measure(bundle, base, "PLUG_MGMT")
        assert api._layout_key(bundle, changed, 4) != api._layout_key(bundle, base, 4)


def test_the_simulation_cache_ignores_only_what_the_simulation_does_not_read():
    bundle, request = load("house")
    base = model_of(bundle, request)
    first = api.run_baseline(bundle, base)
    shuffled = base.model_copy(update={"flags": list(reversed(base.flags)), "roof_planes": list(reversed(base.roof_planes))})
    assert api._simulate(bundle, shuffled) is api._simulate(bundle, base)                 # not read by S5
    warmer = api.set_assumption(base, "setpoint.heating", 24.0)
    assert api.run_baseline(bundle, warmer).model_dump_json() != first.model_dump_json()  # read: a new run


def test_the_data_lanes_extent_record_reaches_the_pv_measure(monkeypatch):
    from backend.schema import FetchRecord
    bundle, request = load("house")
    model = model_of(bundle, request)
    seen = {}
    original = api.evaluate_pv
    monkeypatch.setattr(api, "evaluate_pv", lambda *a, **k: seen.update(k) or original(*a, **k))
    record = FetchRecord(layer="vexcel", what="property/extract:extent", status="fallback",
                         detail="a larger roof outline exists at the property")
    marked = bundle.model_copy(update={"provenance": [*bundle.provenance, record]})
    api.evaluate_measure(marked, model, "PV_ROOF", request.role)
    assert record in seen["provenance"]


# ---- a number written as text ----

def test_a_number_written_as_text_is_a_number():
    bundle, request = load("house")
    base = model_of(bundle, request)
    as_float = api.set_assumption(base, "hvac.heating_rating", 0.64)
    as_text = api.set_assumption(base, "hvac.heating_rating", "0.64")
    assert as_text.model_dump_json() == as_float.model_dump_json()
    assert api.build_plan(bundle, as_text, request).model_dump_json() == api.build_plan(bundle, as_float, request).model_dump_json()
    rebuilt = api.build_building_model(bundle, [], [], {"roof.u_value": "0.182", "setpoint.heating": " 20.7 "})
    same = api.build_building_model(bundle, [], [], {"roof.u_value": 0.182, "setpoint.heating": 20.7})
    assert rebuilt.model_dump_json() == same.model_dump_json()
    assert api.set_assumption(base, "window.type", "single_clear_non_metal").model_dump_json() == \
        api.set_assumption(base, "window.type", "single_clear_non_metal").model_dump_json()      # categorical text stays text


# ---- a property with no example folder ----

def test_the_whole_door_works_for_a_property_that_has_no_example():
    bundle, request = load("office_houston")
    real = bundle.model_copy(update={"summary": bundle.summary.model_copy(update={"sid": "NO_EXAMPLE_SID"})})
    assert not api._has_example("NO_EXAMPLE_SID") and api._measures("NO_EXAMPLE_SID") == []
    observed, flags = api.observe_interior(real)
    assert observed == [] and flags == []
    model = api.build_building_model(real, observed, flags, request.overrides)
    assert api.run_baseline(real, model).annual.electricity_kwh.expected > 0
    tiny = request.model_copy(update={"budget_usd": 2_000.0})                   # a small plan keeps the test quick
    plan = api.build_plan(real, model, tiny)
    assert plan.selected and all(i.measure.finance is not None for i in plan.selected)
    assert api.lookup_incentives("LGT_LED", real.summary) is not None
    priced = api.price_measure(real, api.evaluate_measure(real, model, "LGT_LED", request.role))
    assert priced.finance is not None and api.cpace_scenario(real, priced) is not None


def test_a_missing_example_does_not_change_a_property_that_has_one():
    bundle, request = load("house")
    assert api._has_example(bundle.summary.sid) and api._measures(bundle.summary.sid)


# ---- sensitivity runs the plans side by side (A27) without changing a result ----

def _fake_plan(model):
    from backend.schema import Plan
    from types import SimpleNamespace
    total = sum(a.value.expected * (i + 1) for i, a in enumerate(model.assumptions) if hasattr(a.value, "expected"))
    return SimpleNamespace(total_annual_savings_usd=SimpleNamespace(expected=total),
                           selected=[SimpleNamespace(measure=SimpleNamespace(measure_id=f"M{int(total) % 3}"))])


def test_the_parallel_runner_gives_the_loop_s_results_in_the_loop_s_order():
    from backend.analysis.finance.sensitivity import with_value
    bundle, request = load("house")
    model = model_of(bundle, request)
    models = [model] + [with_value(model, a.key, a.value.low)
                        for a in model.assumptions if hasattr(a.value, "low") and a.value.low < a.value.high][:6]
    serial = [_fake_plan(m) for m in models]
    parallel = api._run_all(_fake_plan, models)
    assert [(p.total_annual_savings_usd.expected, p.selected[0].measure.measure_id) for p in parallel] == \
           [(p.total_annual_savings_usd.expected, p.selected[0].measure.measure_id) for p in serial]


def test_the_runner_falls_back_to_the_loop_when_the_pool_cannot_start(monkeypatch):
    import concurrent.futures as cf
    def broken(*a, **k):
        raise OSError("no processes")
    monkeypatch.setattr(cf, "ProcessPoolExecutor", broken)
    assert api._run_all(lambda m: m * 2, [1, 2, 3, 4, 5]) == [2, 4, 6, 8, 10]
    assert api._FORK == {}


def test_one_worker_means_no_pool(monkeypatch):
    monkeypatch.setenv("ANALYSIS_WORKERS", "1")
    assert api._run_all(lambda m: m + 1, list(range(8))) == list(range(1, 9))


def test_sensitivity_asks_the_same_questions_whether_or_not_it_runs_in_parallel(monkeypatch):
    from backend.analysis.finance import sensitivity as S
    bundle, request = load("house")
    model = model_of(bundle, request)
    plan = api._responsive_plan(bundle, model, request)
    keep = {"window.u_value", "tariff.electricity_usd_per_kwh", "infiltration.ach50", "lighting.lpd"}
    asked = [a.key for a in model.assumptions if a.key not in keep]       # a small set keeps the test quick
    loop = S.rank_assumptions(model, plan, asked)
    side_by_side = S.rank_assumptions(model, plan, asked, run_all=api._run_all)
    assert loop[0] == side_by_side[0]
    assert [(r.key, r.y_low_run, r.y_high_run, r.changes) for r in loop[1]] == \
           [(r.key, r.y_low_run, r.y_high_run, r.changes) for r in side_by_side[1]]
    assert [q.model_dump() for q in S.sensitivity(model, plan, asked=asked)] == \
           [q.model_dump() for q in S.sensitivity(model, plan, asked=asked, run_all=api._run_all)]


# ---- A6: the door calibrates to bills and the result says so ----

def _bills_from(bundle, model, **truth):
    import numpy as np
    from backend.schema import UtilityBills
    for k, v in truth.items():
        model = api.set_assumption(model, k, v, "user")
    token = api._FAST.set(True)
    try:
        r = api._simulate_baseline(bundle, model)
    finally:
        api._FAST.reset(token)
    return UtilityBills(electricity_kwh=[float(x) for x in np.asarray(r.monthly_electricity_kwh)],
                        gas_kwh=[float(x) for x in r.monthly_gas_kwh])


def test_without_calibration_the_baseline_says_so():
    bundle, request = load("house")
    base = api.run_baseline(bundle, model_of(bundle, request))
    assert base.calibrated_to_bills is False and base.calibration is None


def test_calibrate_model_returns_the_model_every_later_step_uses_and_the_baseline_reports_it():
    bundle, request = load("house")
    model = api.build_building_model(bundle, *api.observe_interior(bundle), {"occupancy.count": 3})
    bills = _bills_from(bundle, model, **{"infiltration.ach50": 6.0})
    calibrated = api.calibrate_model(bundle, model, bills)
    assert calibrated.calibration is not None and calibrated.calibration.fits
    base = api.run_baseline(bundle, calibrated, bills)
    assert base.calibration == calibrated.calibration
    assert base.calibrated_to_bills is calibrated.calibration.calibrated
    assert model.calibration is None                                   # the input model is unchanged


def test_sensitivity_keeps_what_the_bills_calibrated(monkeypatch):
    """A variant model is rebuilt from overrides; an assumption with `bills.` evidence stays fixed in it."""
    from backend.schema import EvidenceRef
    bundle, request = load("house")
    model = model_of(bundle, request)
    key = "infiltration.ach50"
    marked = model.model_copy(update={"assumptions": [
        a.model_copy(update={"source": "heuristic" if a.source == "user" else a.source,
                             "evidence": [*a.evidence, EvidenceRef(kind="user", ref="bills.gas_kwh")]})
        if a.key == key else a for a in model.assumptions]})
    seen = {}
    monkeypatch.setattr(api, "build_building_model",
                        lambda b, vision, flags, overrides: seen.update(overrides=dict(overrides)) or model)
    monkeypatch.setattr(api, "_plan_fast", lambda b, m, r: None)
    api._responsive_plan(bundle, marked, request)(marked)
    assert key in seen["overrides"]
