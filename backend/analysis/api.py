"""Public door of the Analysis lane (workplan 3.2). The only module other lanes import.

Every function keeps its final signature. A29 replaces the A0 stubs with the real modules as
they merge; a stub replays the matching example in `specs/examples/`. REAL now: the model (A9
geometry, A10 registry, A11 roof), the baseline (A3 systems with A2 zone loads and A1 climate),
measures (the A16 engine with every plug-in that is registered: A17 to A22 and the A23 desk
layout on the A5 daylight scorer), solar (A11 roof refined by the A12 masks, A14 layout, A15
shading, A1 and A4 yield, the A19 measure), pricing and incentives (A24, A25), the budget plan (A26) and its value uplift (A30).
STILL FIXTURE-BACKED, and switching by itself when the package lands: a measure with no
registered plug-in (replays the example's evaluation, marked in its warnings), observe_interior
(A7 and A8 need a model client: `set_vision`) and cpace_scenario (no rate or term source yet).
Sensitivity (the real one, A27, takes over once the envelope, lighting and
heating-and-cooling plug-ins are all registered, so that the plan answers to the model).
Pure and deterministic; no network.

Examples are found by scanning `specs/examples/` for folders with a `run_result.json` and
reading the sid out of it: no folder name and no sid is hard-coded, so repointing `office/`
or adding `office_houston/` needs no change here.
"""
from __future__ import annotations

import contextvars
import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from backend.analysis.finance.costs import NoCostData, cost_fields, incentives_for, measure_cost
from backend.analysis.finance.economics import financial_breakdown
from backend.analysis.finance.plan import select_plan
from backend.analysis.finance.sensitivity import sensitivity as _ask_questions
from backend.analysis.finance.value import home_pv_uplift, plan_value_uplift
from backend.analysis import layout
from backend.analysis.measures import engine
from backend.analysis.measures.pv import evaluate_pv
from backend.analysis.physics.climate import ClimateHours, Weather, load_climate, plane_irradiance, read_site_weather, read_weather
from backend.analysis.physics.daylight import (lighting_power_fraction, occupied_mask_from_stamps,
                                               prepare_room, score_point, sun_arrays)
from backend.analysis.physics.pv import energy_range, pv_hourly_yield
from backend.analysis.physics.systems import (HourlyLoads, SystemsBaseline, calendar_from_stamps,
                                              egrid_subregion, internal_gains_hourly, systems_baseline)
from backend.analysis.physics.zone import zone_loads
from backend.analysis.solar.layout import Module, layout_pv
from backend.analysis.model.geometry import build_geometry
from backend.analysis.model.registry import (build_registry, merge_assumptions, scanned_floor_area_m2,
                                             set_model_assumption)
from backend.analysis.solar.roof import build_parametric_roof, refine_with_masks
from backend.analysis.solar.shading import shade_panels
from backend.analysis.vision import observe_interior as _vision_interior
from backend.schema import (Assumption, BaselineResult, BuildingModel, EnergyUse, FinancingScenario,
                            Flag, Incentive, LayoutResult, MeasureId, MeasureResult, Plan,
                            PropertyBundle, PropertySummary, Question, Ranged, Role, RunRequest,
                            SolarDesign, Source, UtilityBills)

_EXAMPLES = Path(__file__).resolve().parents[2] / "specs" / "examples"


# ---------- fixture lookup ----------

def _folders() -> list[Path]:
    return sorted(p for p in _EXAMPLES.iterdir() if (p / "run_result.json").is_file())


def _load(folder: Path, name: str):
    return json.loads((folder / name).read_text())


def _folder(sid: str) -> Path:
    for folder in _folders():
        if _load(folder, "run_result.json")["property"]["sid"] == sid:
            return folder
    raise LookupError(f"no example for sid {sid}")


def _measures(sid: str) -> list[MeasureResult]:
    return [MeasureResult.model_validate(m) for m in _load(_folder(sid), "measures.json")]


def _measure(sid: str, measure_id: str) -> Optional[MeasureResult]:
    return next((m for m in _measures(sid) if m.measure_id == measure_id), None)


def _not_in_fixture(measure_id: str) -> MeasureResult:
    return MeasureResult(measure_id=measure_id, title=measure_id, applicable=False,
                         not_applicable_reason="A0 stub: this example has no data for the measure")


# ---------- S3 See ----------

_VISION: dict = {"ask_model": None, "get_bytes": None}


def set_vision(ask_model: Optional[Callable] = None, get_bytes: Optional[Callable] = None) -> None:
    """Give the door a model client and an image reader so observe_interior runs A7 (panoramas
    to glazing, HVAC, water heater and lighting). Sending sponsor imagery to an external model
    waits for the answer to SPEC 16, so the default is none, and the example observations are
    used instead."""
    _VISION["ask_model"], _VISION["get_bytes"] = ask_model, get_bytes


def observe_interior(bundle: PropertyBundle) -> tuple[list[Assumption], list[Flag]]:
    """REAL (A7) when `set_vision` has been called; otherwise the example's observations."""
    if _VISION["ask_model"] is not None and _VISION["get_bytes"] is not None:
        return _vision_interior(bundle, _VISION["ask_model"], _VISION["get_bytes"], room_fallback=True)
    m = BuildingModel.model_validate(_load(_folder(bundle.summary.sid), "building_model.json"))
    return list(m.assumptions), list(m.flags)


# ---------- S4 Model ----------   REAL: A10 registry, A9 geometry, A11 roof

def build_building_model(bundle: PropertyBundle, observed: list[Assumption] = [],
                         flags: list[Flag] = [],
                         overrides: dict[str, float | str | bool] = {}) -> BuildingModel:
    registry = build_registry(bundle, observed, flags, overrides)
    office = registry.building_type != "home"
    costar = bundle.costar
    geometry = build_geometry(bundle.matterport, bundle.vexcel, registry.assumptions,
                              use="office" if office else "living", part_of_larger_building=office,
                              building_stories=costar.stories if costar else None)
    roof = (build_parametric_roof(bundle.vexcel, geometry.north_offset_deg.expected,
                                  state=bundle.summary.state) if bundle.vexcel else None)
    if roof is not None:        # A12: tree overhang from the SAM 3 detections lowers the usable area
        roof.planes = refine_with_masks(roof.planes, bundle.vexcel).planes
    assumptions = merge_assumptions(registry.assumptions, geometry.assumptions,
                                    roof.assumptions if roof else [])
    return BuildingModel(
        sid=bundle.summary.sid, bedrooms=registry.bedrooms, north_offset_deg=geometry.north_offset_deg,
        north_source=geometry.north_source, zones=geometry.zones, surfaces=geometry.surfaces,
        systems=registry.systems, roof_planes=list(roof.planes) if roof else [],
        assumptions=assumptions, flags=registry.flags)


def set_assumption(model: BuildingModel, key: str, value: float | str | bool,
                   source: Source = "user") -> BuildingModel:
    """Returns a new model; a float collapses the range to that value. The input is unchanged."""
    return set_model_assumption(model, key, value, source)


# ---------- climate and the simulate function ----------

_WEATHER_SAMPLES = _EXAMPLES / "weather"
_SAMPLE_FILE = {"CA": "typical_year_hourly.csv", "TX": "typical_year_hourly_houston.csv"}
_CLIMATE_CACHE: dict[tuple, tuple[ClimateHours, Weather, tuple[str, ...]]] = {}
_SIM_CACHE: dict[str, SystemsBaseline] = {}
_SIM_CACHE_MAX = 512
_DESIGN_CACHE: dict[str, SolarDesign] = {}

# Assumptions that move the zone loads, run at low and at high so the baseline range reflects
# them (A2 and A3 handoff note): envelope, glazing, infiltration, setpoints and internal gains.
_A3_OWN_KEYS = ("lighting.lpd", "plug.ppd", "occupancy.count")
_LOAD_KEYS = ("wall.u_value", "roof.u_value", "roof.absorptance", "window.u_value", "window.shgc",
              "infiltration.ach50", "infiltration.leakage_75pa", "setpoint.heating", "setpoint.cooling",
              "lighting.lpd", "plug.ppd", "occupancy.count")


def _climate(bundle: PropertyBundle) -> tuple[ClimateHours, Weather, tuple[str, ...]]:
    """The site's weather year with the sun for every hour (A1). When the cached file of the
    site is not on disk, the example year of the same state is used and the notes say so."""
    key = (bundle.summary.sid, bundle.climate.weather_path)
    if key not in _CLIMATE_CACHE:
        site, notes = bundle.climate, ()
        try:
            weather = read_site_weather(site)
        except FileNotFoundError:
            sample = _WEATHER_SAMPLES / _SAMPLE_FILE[bundle.summary.state]
            weather = read_weather(sample, site.timezone, site.weather_time_convention,
                                   source=f"example year {sample.name}")
            notes = (f"weather: the site file is not cached, so the example year {sample.name} was used",)
        _CLIMATE_CACHE[key] = (load_climate(site, weather=weather), weather, notes)
    return _CLIMATE_CACHE[key]


def _floor_area(model: BuildingModel) -> float:
    conditioned = [z.floor_area_m2 for z in model.zones if z.conditioned]
    return float(sum(conditioned) or sum(z.floor_area_m2 for z in model.zones))


def _zone_run(bundle: PropertyBundle, model: BuildingModel, hours: ClimateHours, weather: Weather,
              cal) -> tuple[HourlyLoads, dict]:
    """A3 internal gains -> A2 zone model -> hourly loads for A3."""
    area = _floor_area(model)
    gains = internal_gains_hourly(model.systems, area, cal, model.bedrooms, len(hours.temp_c))
    cache: dict = {}

    def irradiance(tilt, azimuth):
        k = (round(tilt or 0.0, 3), round(180.0 if azimuth is None else azimuth, 3))
        if k not in cache:
            cache[k] = plane_irradiance(hours, k[0], k[1])["poa_global"]
        return cache[k]

    loads = zone_loads(model, hours.temp_c, irradiance, gains["sensible_w"], wind_m_s=weather.wind_m_s,
                       stamps=hours.stamps, latent_gains_w=gains["latent_w"])
    need = np.asarray(loads.phi_hc_w, dtype=float)
    return HourlyLoads(heating_need_w=np.maximum(need, 0.0), cooling_need_w=np.maximum(-need, 0.0),
                       outdoor_temp_c=np.asarray(hours.temp_c, dtype=float)), {"zone": loads}


def _variant_model(bundle: PropertyBundle, model: BuildingModel, key: str, value: float) -> BuildingModel:
    """The model rebuilt with one assumption collapsed to `value` (geometry and systems follow)."""
    keep = {a.key: a.value.expected if isinstance(a.value, Ranged) else a.value
            for a in model.assumptions if a.source == "user"}
    observed = [a for a in model.assumptions if a.source == "vision"]
    return build_building_model(bundle, observed, model.flags, {**keep, key: value})


def _simulate(bundle: PropertyBundle, model: BuildingModel) -> SystemsBaseline:
    """S5 for one state of the building, memoised on its content (the plan asks for the same
    state many times). The range comes from re-running the zone model with each load-driving
    assumption at its low and high; in fast mode (exploring a plan, the ask rule) that is skipped
    and the range is the price range alone."""
    fast = _FAST.get()
    stamp = hashlib.sha256(((b"fast" if fast else b"full") + (bundle.summary.sid + bundle.climate.weather_path
                                                              + model.model_dump_json()).encode())).hexdigest()
    if stamp in _SIM_CACHE:
        return _SIM_CACHE[stamp]
    hours, weather, _ = _climate(bundle)
    cal = calendar_from_stamps(hours.stamps, bundle.climate.weather_time_convention)
    loads, _ = _zone_run(bundle, model, hours, weather, cal)
    variants = {}
    for a in ([] if fast else model.assumptions):
        if a.key in _LOAD_KEYS and a.user_editable and isinstance(a.value, Ranged) and a.value.low < a.value.high:
            runs = []
            for value in (a.value.low, a.value.high):
                runs.append(_zone_run(bundle, _variant_model(bundle, model, a.key, value), hours, weather, cal)[0])
            # A3 already varies lighting, plug and occupant energy under these keys; the same inputs
            # also change the heat gains the zone model sees, which is a separate effect.
            name = f"zone.{a.key}" if a.key in _A3_OWN_KEYS else a.key
            variants[name] = (runs[0], runs[1])
    result = systems_baseline(model.systems, bundle.tariff, loads, floor_area_m2=_floor_area(model),
                              subregion=egrid_subregion(bundle.summary.state), bedrooms=model.bedrooms,
                              calendar=cal, assumptions=model.assumptions, load_variants=variants)
    if len(_SIM_CACHE) >= _SIM_CACHE_MAX:
        _SIM_CACHE.pop(next(iter(_SIM_CACHE)))
    _SIM_CACHE[stamp] = result
    return result


def _simulate_baseline(bundle: PropertyBundle, model: BuildingModel) -> BaselineResult:
    return _simulate(bundle, model).baseline


# ---------- S5 Baseline ----------   REAL: A3 -> A2 -> A3, A1 climate

def run_baseline(bundle: PropertyBundle, model: BuildingModel,
                 bills: UtilityBills | None = None) -> BaselineResult:
    return _simulate_baseline(bundle, model)          # bill calibration is A6 (P2)


# ---------- S6 Measures ----------

def _register_plugins() -> None:
    """Register every measure package that exists, in the shape the A16 engine documents:
    a MEASURES dict of MeasureId -> (check, change, describe, formula_ids). A package that has
    not landed yet is simply absent, and its measures keep replaying the example."""
    for name in ("envelope", "systems", "walls_windows", "hvac_dhw", "controls"):
        try:
            module = importlib.import_module(f"backend.analysis.measures.{name}")
        except ImportError:
            continue
        for measure_id, (check, change, describe, formula_ids) in getattr(module, "MEASURES", {}).items():
            engine.register(measure_id, change=change, describe=describe, check=check, formula_ids=formula_ids)
    engine.register("LAYOUT", check=layout.check, change=layout.change, describe=_describe_layout,
                    formula_ids=layout.FORMULA_IDS)
    engine.register("PV_ROOF", change=lambda bundle, model: model.model_copy(deep=True),
                    describe=_describe_pv, formula_ids=("PV-01", "PV-02", "PV-03", "PV-04", "PV-05",
                                                        "PV-06", "PV-09", "LAY-03", "ROOF-04"))


def evaluate_measure(bundle: PropertyBundle, model: BuildingModel, measure_id: MeasureId,
                     role: Role, desks_requested: int | None = None) -> MeasureResult:
    """REAL (A16 engine) for every registered measure. One with no plug-in yet replays the
    example's evaluation and says so; with no example either it is not applicable."""
    result = engine.evaluate(bundle, model, measure_id, role, _simulate_baseline,
                             desks_requested=desks_requested, simulate_formula_ids=_SIM_FORMULAS)
    if engine.skip_reason(result) != "not_supported":
        return result
    stub = _measure(bundle.summary.sid, measure_id)
    if stub is None:
        return result
    return stub.model_copy(update={"finance": None, "warnings": [
        *stub.warnings, "A0 stub: this measure's package is not registered yet; the example's evaluation is shown"]})


_SIM_FORMULAS = ("ZON-01", "ZON-04", "ENV-03", "INF-01", "HVAC-01", "LGT-03", "TAR-01", "EMI-01", "UNC-02")


# ---- solar: A11 roof planes -> A14 layout, with the A1 climate and A4 chain behind the yield ----

_FAST: contextvars.ContextVar[bool] = contextvars.ContextVar("fast_simulation", default=False)
_PV_BUDGET: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar("pv_budget", default=None)
_NO_WIND_M_S = 1.0     # the weather file has no wind column: a light breeze is assumed for the cell temperature


def _plane_hourly(bundle: PropertyBundle, tilt: float, azimuth: float) -> np.ndarray:
    """Hourly AC kWh per kW DC on one plane (A1 transposition, then the A4 chain)."""
    hours, weather, _ = _climate(bundle)
    poa = plane_irradiance(hours, tilt, azimuth)
    wind = weather.wind_m_s if weather.wind_m_s is not None else np.full(len(hours.temp_c), _NO_WIND_M_S)
    return pv_hourly_yield(poa["poa_beam"], poa["poa_sky_diffuse"], poa["poa_ground"], poa["incidence_deg"],
                           hours.temp_c, wind).ac_kwh_per_kw


def _plane_yield(bundle: PropertyBundle, plane) -> Ranged:
    """Annual kWh per kW DC of a plane with the PV-09 range: the tilt range as extra runs, then the
    weather spread from PVGIS."""
    tilt, az = plane.tilt_deg, plane.azimuth_deg
    expected = float(_plane_hourly(bundle, tilt.expected, az).sum())
    others = [float(_plane_hourly(bundle, t, az).sum()) for t in (tilt.low, tilt.high)]
    ranged, _ = energy_range(expected, others, bundle.climate.pvgis_sd_fraction, unit="kWh/kW")
    return ranged


def _feasibility(model: BuildingModel) -> tuple[Flag, Flag]:
    def flag(key: str, message: str) -> Flag:
        return next((f for f in model.flags if f.key == key),
                    Flag(key=key, status="unknown", message=message))
    return (flag("electrical.service", "Main panel not seen; a service upgrade may be needed."),
            flag("roof.structure", "Roof structure not assessed."))


def _design(bundle: PropertyBundle, model: BuildingModel, baseline: BaselineResult,
            budget_usd: Optional[float]) -> SolarDesign:
    electrical, structural = _feasibility(model)
    consumption = baseline.annual.electricity_kwh.expected
    key = hashlib.sha256(json.dumps([bundle.summary.sid, bundle.climate.weather_path,
                                     [p.model_dump(mode="json") for p in model.roof_planes],
                                     electrical.model_dump(mode="json"), structural.model_dump(mode="json"),
                                     budget_usd, round(consumption, 3)], sort_keys=True).encode()).hexdigest()
    if key in _DESIGN_CACHE:                      # packing a large flat roof takes seconds
        return _DESIGN_CACHE[key]
    cache: dict[str, Ranged] = {}

    def yield_fn(plane, polygon_wkt):
        if plane.id not in cache:
            cache[plane.id] = _plane_yield(bundle, plane)
        return cache[plane.id]

    module_w = Module().watts

    def installed_cost(count: int) -> float:
        return _pv_installed_cost(bundle, count * module_w)
    design = layout_pv(list(model.roof_planes), electrical, structural, yield_fn, budget_usd,
                       consumption if consumption > 0 else None, installed_cost_usd=installed_cost)
    design = _with_shading(bundle, model, design)
    if len(_DESIGN_CACHE) >= 128:
        _DESIGN_CACHE.pop(next(iter(_DESIGN_CACHE)))
    _DESIGN_CACHE[key] = design
    return design


def _pv_installed_cost(bundle: PropertyBundle, watts_dc: float) -> float:
    """A24's installed cost of PV for a system of this size, the number A14 compares with the budget."""
    return measure_cost("PV_ROOF", watts_dc, bundle.summary.segment)[0].expected


def _with_shading(bundle: PropertyBundle, model: BuildingModel, design: SolarDesign) -> SolarDesign:
    """A15: ray-cast shading per panel where there is geometry to cast against (a splat roof or
    obstructions with a height). On a parametric roof there is nothing to cast, so each panel keeps
    A4's default allowance and A15 only reports that."""
    if not design.panels:
        return design
    hours, _, _ = _climate(bundle)
    comps = {p.id: {k: v for k, v in plane_irradiance(hours, p.tilt_deg.expected, p.azimuth_deg).items()
                    if k in ("poa_beam", "poa_sky_diffuse", "poa_ground", "poa_sky_circumsolar")}
             for p in model.roof_planes}
    shaded = shade_panels(list(model.roof_planes), design.panels, hours.apparent_zenith_deg,
                          hours.sun_azimuth_deg, poa_components=comps)
    return design.model_copy(update={"panels": shaded.placements(design.panels)})


def design_pv(bundle: PropertyBundle, model: BuildingModel, baseline: BaselineResult,
              budget_usd: float | None = None) -> SolarDesign:
    """REAL: A14 fills the A11 roof planes in order of yield and stops at the roof, the budget or
    the site's annual consumption; the yield of each plane is the A1 climate through the A4 chain."""
    return _design(bundle, model, baseline, budget_usd)


def _describe_pv(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                 before: BaselineResult, options: dict) -> MeasureResult:
    """The PV_ROOF card for the A16 engine: the design (A14) and its value (A19). The budget is what
    the plan has left; evaluated alone there is none, and the roof or the consumption stops the fill."""
    design = _design(bundle, model, before, _PV_BUDGET.get())
    existing = (build_parametric_roof(bundle.vexcel, model.north_offset_deg.expected,
                                      state=bundle.summary.state).existing_solar if bundle.vexcel else False)
    hourly = None
    if design.panels:
        planes = {p.id: p for p in model.roof_planes}
        kw: dict[str, float] = {}
        for panel in design.panels:
            kw[panel.plane_id] = kw.get(panel.plane_id, 0.0) + (design.module_w or Module().watts) / 1000.0
        parts = [_plane_hourly(bundle, planes[pid].tilt_deg.expected, planes[pid].azimuth_deg) * k
                 for pid, k in kw.items() if pid in planes]
        hourly = sum(parts) if parts else None
    return evaluate_pv(design, before, bundle.tariff, hourly_pv_kwh=hourly, existing_solar=bool(existing),
                       state=bundle.summary.state)


_LIGHT_CONTROLS = ("continuous", "continuous_off", "stepped", "auto_on_off")


def _desk_scorer(bundle: PropertyBundle, model: BuildingModel):
    """The point scorer A23 wants, built on A5: daylight, glare and comfort at (x, y) of a room.
    The sun is A1's year, the zone air temperature is A2's, and each room's windows and room-wide
    reflected component are prepared once (a point takes about 6 ms). Besides A5's fields it
    returns the mean saved lighting fraction at the setpoint for each control type (LCT-01)."""
    hours, weather, _ = _climate(bundle)
    cal = calendar_from_stamps(hours.stamps, bundle.climate.weather_time_convention)
    _, runs = _zone_run(bundle, model, hours, weather, cal)
    zone = next((z for z in runs["zone"].zones if z.conditioned), runs["zone"].zones[0])
    zone_temps = {"theta_air_c": zone.hourly["theta_air_c"]}
    occupied = occupied_mask_from_stamps(hours.stamps)
    sun = sun_arrays(hours, occupied)
    floors = {f.id: f for f in bundle.matterport.floors}
    contexts: dict = {}
    north = model.north_offset_deg.expected

    def scorer(*, bundle, model, room, x, y, setpoint_lux):
        floor = floors[room.floor_id]
        if room.id not in contexts:
            contexts[room.id] = prepare_room(room, model.surfaces, floor=floor, north_offset_deg=north,
                                             assumptions=model.assumptions)
        try:
            raw = score_point(room, model.surfaces, x, y, sun, zone_temps, floor=floor, north_offset_deg=north,
                              assumptions=model.assumptions, context=contexts[room.id], return_hourly=True)
        except ValueError as err:       # A5 refuses a point it finds outside the room: never recommend it
            return {"daylight": 0.0, "glare_risk": 1.0, "comfort_ppd": 100.0, "max_dt_pr_k": None,
                    "warnings": [f"A5 refused this position: {err}"],
                    "lighting_saved_fraction": {ct: 0.0 for ct in _LIGHT_CONTROLS}}
        e_in = raw["hourly"]["e_in_lux"]
        raw = {k: v for k, v in raw.items() if k != "hourly"}
        raw["lighting_saved_fraction"] = {
            ct: float(np.mean(1.0 - lighting_power_fraction(e_in, setpoint_lux, ct)[occupied]))
            for ct in _LIGHT_CONTROLS}
        return raw
    return scorer


_LAYOUT_CACHE: dict[str, MeasureResult] = {}


def _describe_layout(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                     before: BaselineResult, options: dict) -> MeasureResult:
    """The LAYOUT card for the A16 engine: A23 placing desks with the A5 scorer. Scoring a few
    thousand positions takes seconds, so the card is memoised on the building and the request."""
    key = hashlib.sha256(json.dumps([bundle.summary.sid, bundle.climate.weather_path, model.model_dump_json(),
                                     (options or {}).get("desks_requested")]).encode()).hexdigest()
    if key not in _LAYOUT_CACHE:
        if len(_LAYOUT_CACHE) >= 64:
            _LAYOUT_CACHE.pop(next(iter(_LAYOUT_CACHE)))
        _LAYOUT_CACHE[key] = layout.describe(bundle, model, changed, before, options,
                                             score_point=_desk_scorer(bundle, model))
    return _LAYOUT_CACHE[key]


def score_desk_positions(bundle: PropertyBundle, model: BuildingModel,
                         desks_requested: int | None = None) -> LayoutResult:
    """REAL (A23 with the A5 scorer): the scored candidate positions and the recommended desks."""
    return layout.place_desks(bundle, model, desks_requested, _desk_scorer(bundle, model),
                              flow=engine.flow_of(bundle.summary)).result


_FORMULAS = ["COST-01", "COST-02", "ECO-05", "ECO-06", "ECO-07", "ECO-09", "ECO-10", "ECO-11", "ECO-13",
             "INC-40"]


def price_measure(bundle: PropertyBundle, measure: MeasureResult) -> MeasureResult:
    """REAL (A24 costs, A25 economics) once the measure says how much of it there is (its
    `params` or `solar`). Where the quantity is not in the measure yet, the stub engine's own
    finance is kept and the measure says so; with no quantity and none to keep, `finance`
    stays empty. A measure with no verified cost source gets `finance=None` and a warning."""
    if not measure.applicable or measure.savings is None:
        return measure
    summary = bundle.summary
    try:
        # `Tariff.utility` is resolved by the data lane from the Census
        # incorporated-place layer (D14), so the LADWP and CenterPoint registry
        # entries no longer key on the CoStar city field - a *mailing* city, right
        # 14/14 for Los Angeles but only 9 of 16 for Houston. An unnamed utility is
        # unconfirmed and gets no utility-specific incentive, per the lead.
        costs = cost_fields(measure, summary, utility=bundle.tariff.utility)
    except NoCostData as err:
        if err.code == "no_quantity":
            stub = _measure(summary.sid, measure.measure_id)
            if stub is not None and stub.finance is not None:
                return measure.model_copy(update={"finance": stub.finance, "warnings": [
                    *measure.warnings, "A0 stub: finance kept from the example; the quantity to price is not in the measure yet"]})
        return measure.model_copy(update={"finance": None, "warnings": [
            *measure.warnings, f"{err}" if err.code == "no_quantity" else "no verified cost source; get a quote"]})
    breakdown = financial_breakdown(
        installed_cost_usd=costs.installed_cost_usd, cost_source=costs.cost_source,
        net_upfront_usd=costs.net_upfront_usd, incentives=costs.incentives,
        useful_life_years=costs.useful_life_years, annual_om_change_usd=costs.annual_om_change_usd,
        savings=measure.savings, tariff=bundle.tariff, state=summary.state, segment=summary.segment,
        degradation_rate=(measure.solar.degradation_rate if measure.solar else 0.0) or 0.0)
    formulas = list(measure.formula_ids) + [f for f in _FORMULAS if f not in measure.formula_ids]
    return measure.model_copy(update={"finance": breakdown, "formula_ids": formulas,
                                      "warnings": [*measure.warnings, *costs.notes]})


def lookup_incentives(measure_id: MeasureId, summary: PropertySummary) -> list[Incentive]:
    """REAL (A24). The measure's parameters come from the stub engine's result until A16."""
    found = _measure(summary.sid, measure_id) or MeasureResult(measure_id=measure_id, title=measure_id,
                                                               applicable=True)
    # No bundle here, so no resolved utility: this door function takes a summary by
    # workplan 3.2. `incentives_for` falls back to the city field and warns. The
    # load-bearing path is `price_measure`, which has the bundle and passes
    # `Tariff.utility` through - see the note on `utility_of`.
    return incentives_for(found, summary)


@dataclass(frozen=True)
class _PlanState:
    """The building as the plan has changed it so far."""
    model: BuildingModel
    stub_savings: tuple = ()        # savings of measures replayed from the example (they cannot change the model)
    spent: float = 0.0              # net upfront cash of the measures chosen
    applied: int = 0                # how many measures have been chosen


def _select(bundle: PropertyBundle, model: BuildingModel, request: RunRequest,
            wanted: Optional[frozenset] = None) -> Plan:
    """One run of the SPEC 6.5 algorithm. Every measure is evaluated in fast mode (the expected
    values decide the order) except the (measure, round) pairs in `wanted`, which get the full
    ranges."""
    summary = bundle.summary
    ids = [m for m, entry in engine.CATALOGUE.items()
           if engine.flow_of(summary) in entry.flows
           and (m in engine.REGISTRY.plugins or _measure(summary.sid, m) is not None)]

    def evaluate(measure_id, state):
        full = wanted is not None and (measure_id, state.applied) in wanted
        tokens = (_PV_BUDGET.set(max(0.0, request.budget_usd - state.spent)), _FAST.set(not full))
        try:
            found = evaluate_measure(bundle, state.model, measure_id, request.role, request.desks_requested)
        finally:
            _FAST.reset(tokens[1])
            _PV_BUDGET.reset(tokens[0])
        return price_measure(bundle, found)

    def apply(state, measure):
        spent = state.spent + (measure.finance.net_upfront_usd.expected if measure.finance else 0.0)
        if measure.measure_id in engine.REGISTRY.plugins:
            return _PlanState(engine.apply_measure(bundle, state.model, measure.measure_id),
                              state.stub_savings, spent, state.applied + 1)
        return _PlanState(state.model, state.stub_savings + (measure.savings,), spent, state.applied + 1)

    def energy(state):
        token = _FAST.set(wanted is None)
        try:
            return _after(_simulate_baseline(bundle, state.model).annual, list(state.stub_savings))
        finally:
            _FAST.reset(token)

    return select_plan(ids, request.role, request.budget_usd, _PlanState(model), evaluate, apply, energy)


def build_plan(bundle: PropertyBundle, model: BuildingModel, request: RunRequest) -> Plan:
    """REAL (A26, SPEC 6.5). Every round each measure is evaluated against the building as the plan
    has changed it (A16 engine, A2 and A3 simulation), priced (A24, A25), and the solar design is
    sized to the budget still left. A measure with no plug-in yet replays the example's evaluation
    and cannot change the model; its savings are taken off the final baseline.

    Two passes: the first explores in fast mode, which is all the order needs (it depends on the
    expected values only); the second repeats the run and gives the measures that made the plan, and
    the financeable ones, the full low and high ranges."""
    return _with_value_uplift(bundle, _plan_with_ranges(bundle, model, request))


def _plan_fast(bundle: PropertyBundle, model: BuildingModel, request: RunRequest) -> Plan:
    """The plan for exploring (the ask rule re-runs it many times): expected values exact, ranges narrow."""
    return _select(bundle, model, request)


def _plan_with_ranges(bundle: PropertyBundle, model: BuildingModel, request: RunRequest) -> Plan:
    first = _select(bundle, model, request)
    wanted = frozenset({(item.measure.measure_id, k) for k, item in enumerate(first.selected)}
                       | {(m.measure_id, len(first.selected)) for m in first.financeable})
    return _select(bundle, model, request, wanted)


def _with_value_uplift(bundle: PropertyBundle, plan: Plan) -> Plan:
    """REAL (A30). A commercial or multifamily plan carries VAL-01 when the bundle has CoStar
    market data (and the module has at least 10 comparables); a home carries VAL-03 on its owned
    rooftop solar and nowhere else. Never added to a total and never used in the order."""
    summary = bundle.summary
    if summary.segment == "residential":
        def with_pv(m: MeasureResult) -> MeasureResult:
            if m.measure_id != "PV_ROOF" or m.solar is None or m.finance is None:
                return m
            return m.model_copy(update={"value_uplift": home_pv_uplift(
                m.solar.system_kw_dc, m.finance.net_upfront_usd.expected)})
        return plan.model_copy(update={
            "selected": [i.model_copy(update={"measure": with_pv(i.measure)}) for i in plan.selected],
            "financeable": [with_pv(m) for m in plan.financeable]})
    if not plan.selected or bundle.costar is None:
        return plan
    om = sum(i.measure.finance.annual_om_change_usd for i in plan.selected if i.measure.finance)
    saving = plan.total_annual_savings_usd
    net = Ranged(low=round(saving.low - om, 2), expected=round(saving.expected - om, 2),
                 high=round(saving.high - om, 2), unit="USD")
    uplift = plan_value_uplift(bundle.costar.market, net, floor_area_m2=scanned_floor_area_m2(bundle))
    return plan.model_copy(update={"value_uplift": uplift})


def _after(base: EnergyUse, savings: list[EnergyUse]) -> EnergyUse:
    """Annual use less the chosen measures' expected savings (an interim stand-in for simulating
    the changed model, A3)."""
    def minus(r: Ranged, parts: list[Ranged]) -> Ranged:
        cut = sum(p.expected for p in parts)
        low, expected, high = (max(0.0, round(x - cut, 2)) for x in (r.low, r.expected, r.high))
        return Ranged(low=low, expected=expected, high=high, unit=r.unit)
    return EnergyUse(
        electricity_kwh=minus(base.electricity_kwh, [s.electricity_kwh for s in savings]),
        gas_kwh=minus(base.gas_kwh, [s.gas_kwh for s in savings]),
        cost_usd=minus(base.cost_usd, [s.cost_usd for s in savings]),
        co2_kg=minus(base.co2_kg, [s.co2_kg for s in savings]))


def cpace_scenario(bundle: PropertyBundle, measure: MeasureResult) -> FinancingScenario:
    """REAL (A28) for the eligibility rules; the **payment** still needs a market quote,
    because `config.CPACE_RATE` and `CPACE_TERM_YEARS` are deliberately `None`.

    `in_pace_region` comes from the data lane's Census incorporated-place lookup (D14),
    not from the CoStar city field: Texas PACE lists the City of Houston, and of 16
    CoStar-"Houston" properties only 9 are in it - 6 are unincorporated Harris County
    and 1 is Nassau Bay. `None` from that lookup means "could not check", which A28
    treats as not eligible, and the note says which it was.
    """
    from backend.analysis.finance.cpace import cpace_scenario as a28
    from backend.data_layer import api as data

    summary = bundle.summary
    try:
        in_region = data.in_pace_region(summary.sid)
    except Exception:
        in_region = None          # the lookup is a courtesy service, never fatal
    return a28(measure, summary, in_pace_region=in_region)


def sensitivity(bundle: PropertyBundle, model: BuildingModel, request: RunRequest) -> list[Question]:
    """REAL (A27) once the envelope, lighting and heating-and-cooling plug-ins are registered, so
    that the plan answers to the model; until then the example's questions, which keeps the ask
    rule demonstrable."""
    core = ("ENV_ATTIC", "LGT_LED", "HVAC_HP" if engine.flow_of(bundle.summary) == "home" else "HVAC_RTU")
    if all(m in engine.REGISTRY.plugins for m in core):
        return _ask_questions(model, lambda m: _plan_fast(bundle, m, request))
    return [Question.model_validate(q)
            for q in _load(_folder(bundle.summary.sid), "run_result.json")["questions"]]


_register_plugins()
