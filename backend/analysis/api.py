"""Public door of the Analysis lane (workplan 3.2). The only module other lanes import.

Every function keeps its final signature. A29 replaces the A0 stubs (which return the matching
example in `specs/examples/`) with the real modules as they merge. Wired so far, marked REAL
below: the model (A9 geometry, A10 registry, A11 roof), pricing and incentives (A24, A25) and
the budget plan (A26). Still replaying fixtures, marked STUB, until their packages land:
observe_interior (A7), run_baseline (A2, A3), evaluate_measure (A16 to A22), design_pv (A14),
score_desk_positions (A23), cpace_scenario (A28) and sensitivity (the real one, A27, is ready
but the stub measures do not respond to the model, so it would never ask). Pure, deterministic,
no network, no file writes.

Examples are found by scanning `specs/examples/` for folders with a `run_result.json` and
reading the sid out of it: no folder name and no sid is hard-coded, so repointing `office/`
or adding `office_houston/` needs no change here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend.analysis.finance.costs import NoCostData, cost_fields, incentives_for
from backend.analysis.finance.economics import financial_breakdown
from backend.analysis.finance.plan import select_plan
from backend.analysis.finance.value import home_pv_uplift, plan_value_uplift
from backend.analysis.model.geometry import build_geometry
from backend.analysis.model.registry import (build_registry, merge_assumptions, scanned_floor_area_m2,
                                             set_model_assumption)
from backend.analysis.solar.roof import build_parametric_roof
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

def observe_interior(bundle: PropertyBundle) -> tuple[list[Assumption], list[Flag]]:
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


# ---------- S5 Baseline ----------

def run_baseline(bundle: PropertyBundle, model: BuildingModel,
                 bills: UtilityBills | None = None) -> BaselineResult:
    return BaselineResult.model_validate(_load(_folder(bundle.summary.sid), "baseline_result.json"))


# ---------- S6 Measures ----------

def evaluate_measure(bundle: PropertyBundle, model: BuildingModel, measure_id: MeasureId,
                     role: Role, desks_requested: int | None = None) -> MeasureResult:
    found = _measure(bundle.summary.sid, measure_id)
    return found.model_copy(update={"finance": None}) if found else _not_in_fixture(measure_id)


def design_pv(bundle: PropertyBundle, model: BuildingModel, baseline: BaselineResult,
              budget_usd: float | None = None) -> SolarDesign:
    pv = _measure(bundle.summary.sid, "PV_ROOF")
    if pv is None or pv.solar is None:
        raise LookupError("A0 stub: this example has no solar design")
    return pv.solar


def score_desk_positions(bundle: PropertyBundle, model: BuildingModel,
                         desks_requested: int | None = None) -> LayoutResult:
    layout = _measure(bundle.summary.sid, "LAYOUT")
    if layout is None or layout.layout is None:
        raise LookupError("A0 stub: this example has no desk layout")
    return layout.layout


# ---------- S7 Plan ----------

# Home and office columns of the SPEC 6.2 measure library.
_HOME = ("ENV_ATTIC", "ENV_WALL", "ENV_AIRSEAL", "WIN_REPLACE", "WIN_FILM", "WIN_SHADE", "ROOF_COOL",
         "HVAC_HP", "HVAC_DUCT", "DHW_HPWH", "LGT_LED", "CTRL_TSTAT", "PV_ROOF", "LAYOUT")
_OFFICE = ("ENV_ATTIC", "ENV_AIRSEAL", "WIN_REPLACE", "WIN_FILM", "WIN_SHADE", "ROOF_COOL", "HVAC_RTU",
           "HVAC_ECON", "LGT_LED", "LGT_CTRL", "PLUG_MGMT", "CTRL_TSTAT", "PV_ROOF", "LAYOUT")
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
        costs = cost_fields(measure, summary)
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
    return incentives_for(found, summary)


def build_plan(bundle: PropertyBundle, model: BuildingModel, request: RunRequest) -> Plan:
    """REAL algorithm (A26, SPEC 6.5) over the stub engine's measures priced by A24 and A25, with
    the value uplift of A30.
    The state is the model plus the measures chosen so far; the stub engine does not yet change
    its savings with the state, and `baseline_after` is the baseline less the chosen savings."""
    columns = _HOME if model.systems.occupancy_schedule == "home" else _OFFICE
    ids = [m for m in columns if _measure(bundle.summary.sid, m) is not None]    # the stub engine's measures
    baseline = run_baseline(bundle, model, request.bills)

    def evaluate(measure_id, state):
        found = evaluate_measure(bundle, state[0], measure_id, request.role, request.desks_requested)
        return price_measure(bundle, found)

    def apply(state, measure):
        return (state[0], state[1] + (measure,))

    def energy(state):
        return _after(baseline.annual, [m.savings for m in state[1]])

    plan = select_plan(ids, request.role, request.budget_usd, (model, ()), evaluate, apply, energy)
    return _with_value_uplift(bundle, plan)


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
    found = _measure(bundle.summary.sid, measure.measure_id)
    for scenario in (found.finance.financing if found and found.finance else []):
        if scenario.kind == "cpace":
            return scenario
    return FinancingScenario(kind="cpace", eligible=False,
                             net_cashflow_year1_usd=Ranged(low=0, expected=0, high=0, unit="USD"),
                             notes=["A0 stub: this example has no C-PACE scenario"])


def sensitivity(bundle: PropertyBundle, model: BuildingModel,
                request: RunRequest) -> list[Question]:
    return [Question.model_validate(q)
            for q in _load(_folder(bundle.summary.sid), "run_result.json")["questions"]]
