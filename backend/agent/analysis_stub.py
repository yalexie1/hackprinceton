"""Fixture-backed stand-in for `backend.analysis.api` (workplan 3.2), used by the live run
door until the Analysis lane's real door imports. Same signatures; every function replays the
example folder that matches the property's sid. Pure and offline."""
from __future__ import annotations

from typing import Optional

from backend.agent.fixtures import flavor_for_sid, load
from backend.schema import (Assumption, BaselineResult, BuildingModel, FinancingScenario,
                            Flag, Incentive, LayoutResult, MeasureResult, Plan,
                            PropertyBundle, PropertySummary, Question, Ranged, RunRequest,
                            SolarDesign)


def _flavor(sid: str) -> str:
    return flavor_for_sid(sid)


def _measures(sid: str) -> list[MeasureResult]:
    return [MeasureResult.model_validate(m) for m in load(_flavor(sid), "measures.json")]


def _measure(sid: str, measure_id: str) -> MeasureResult:
    for m in _measures(sid):
        if m.measure_id == measure_id:
            return m
    raise LookupError(f"measure {measure_id} is not in the fixture")


def observe_interior(bundle: PropertyBundle) -> tuple[list[Assumption], list[Flag]]:
    m = BuildingModel.model_validate(load(_flavor(bundle.summary.sid), "building_model.json"))
    return list(m.assumptions), list(m.flags)


def set_assumption(model: BuildingModel, key: str, value, source: str = "user") -> BuildingModel:
    out = model.model_copy(deep=True)
    for a in out.assumptions:
        if a.key == key:
            break
    else:
        a = Assumption(key=key, label=key, value="", source=source, confidence=1.0)
        out.assumptions.append(a)
    if isinstance(value, (bool, str)):
        a.value = value
    else:
        unit = a.value.unit if isinstance(a.value, Ranged) else ""
        a.value = Ranged(low=float(value), expected=float(value), high=float(value), unit=unit)
    a.source, a.confidence = source, 1.0
    return out


def build_building_model(bundle: PropertyBundle, observed=(), flags=(), overrides=None) -> BuildingModel:
    m = BuildingModel.model_validate(load(_flavor(bundle.summary.sid), "building_model.json"))
    for key, value in (overrides or {}).items():
        m = set_assumption(m, key, value)
    return m


def run_baseline(bundle: PropertyBundle, model: BuildingModel, bills=None) -> BaselineResult:
    return BaselineResult.model_validate(load(_flavor(bundle.summary.sid), "baseline_result.json"))


def climate_notes(bundle: PropertyBundle) -> list[str]:
    """Nothing: this door reads no weather, so it substitutes none. The run is already warned
    that the whole analysis is a replay (`Doors.degraded`), which covers more than the weather."""
    return []


def evaluate_measure(bundle: PropertyBundle, model: BuildingModel, measure_id: str, role: str,
                     desks_requested: Optional[int] = None) -> MeasureResult:
    return _measure(bundle.summary.sid, measure_id).model_copy(update={"finance": None})


def design_pv(bundle: PropertyBundle, model: BuildingModel, baseline: BaselineResult,
              budget_usd: Optional[float] = None) -> SolarDesign:
    solar = _measure(bundle.summary.sid, "PV_ROOF").solar
    if solar is None:
        raise LookupError("the fixture has no solar design")
    return solar


def score_desk_positions(bundle: PropertyBundle, model: BuildingModel,
                         desks_requested: Optional[int] = None) -> LayoutResult:
    layout = _measure(bundle.summary.sid, "LAYOUT").layout
    if layout is None:
        raise LookupError("the fixture has no desk layout")
    return layout


def price_measure(bundle: PropertyBundle, measure: MeasureResult) -> MeasureResult:
    return _measure(bundle.summary.sid, measure.measure_id)


def lookup_incentives(measure_id: str, summary: PropertySummary) -> list[Incentive]:
    m = _measure(summary.sid, measure_id)
    return list(m.finance.incentives) if m.finance else []


def build_plan(bundle: PropertyBundle, model: BuildingModel, request: RunRequest) -> Plan:
    name = "plan_tenant.json" if request.role == "tenant" else "plan.json"
    plan = Plan.model_validate(load(_flavor(bundle.summary.sid), name))
    return plan.model_copy(update={"budget_usd": request.budget_usd})


def cpace_scenario(bundle: PropertyBundle, measure: MeasureResult) -> FinancingScenario:
    finance = _measure(bundle.summary.sid, measure.measure_id).finance
    for f in (finance.financing if finance else []):
        if f.kind == "cpace":
            return f
    raise LookupError(f"no C-PACE scenario for {measure.measure_id} in the fixture")


def sensitivity(bundle: PropertyBundle, model: BuildingModel, request: RunRequest) -> list[Question]:
    run = load(_flavor(bundle.summary.sid), "run_result.json")
    return [Question.model_validate(q) for q in run["questions"]]
