"""Public door of the Analysis lane (workplan 3.2). The only module other lanes import.

A0 stubs: every function returns the matching example in `specs/examples/` behind the final
signature, so the agent and server lanes can run end to end before any physics exists. A29
replaces each body with the real modules; the signatures stay. Pure, deterministic, no
network, no file writes.

Examples are found by scanning `specs/examples/` for folders with a `run_result.json` and
reading the sid out of it: no folder name and no sid is hard-coded, so repointing `office/`
or adding `office_houston/` needs no change here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from backend.schema import (Assumption, BaselineResult, BuildingModel, FinancingScenario, Flag,
                            Incentive, LayoutResult, MeasureId, MeasureResult, Plan,
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


# ---------- S4 Model ----------

def build_building_model(bundle: PropertyBundle, observed: list[Assumption] = [],
                         flags: list[Flag] = [],
                         overrides: dict[str, float | str | bool] = {}) -> BuildingModel:
    model = BuildingModel.model_validate(_load(_folder(bundle.summary.sid), "building_model.json"))
    for key, value in overrides.items():
        model = set_assumption(model, key, value)
    return model


def set_assumption(model: BuildingModel, key: str, value: float | str | bool,
                   source: Source = "user") -> BuildingModel:
    """Returns a new model; a float collapses the range to that value. The input is unchanged."""
    out = model.model_copy(deep=True)
    target = next((a for a in out.assumptions if a.key == key), None)
    if target is None:
        target = Assumption(key=key, label=key, value="", source=source, confidence=1.0)
        out.assumptions.append(target)
    if isinstance(value, (bool, str)):
        target.value = value
    else:
        unit = target.value.unit if isinstance(target.value, Ranged) else ""
        target.value = Ranged(low=float(value), expected=float(value), high=float(value), unit=unit)
    target.source, target.confidence = source, 1.0
    return out


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

def price_measure(bundle: PropertyBundle, measure: MeasureResult) -> MeasureResult:
    return _measure(bundle.summary.sid, measure.measure_id) or measure


def lookup_incentives(measure_id: MeasureId, summary: PropertySummary) -> list[Incentive]:
    found = _measure(summary.sid, measure_id)
    return list(found.finance.incentives) if found and found.finance else []


def build_plan(bundle: PropertyBundle, model: BuildingModel, request: RunRequest) -> Plan:
    name = "plan_tenant.json" if request.role == "tenant" else "plan.json"
    plan = Plan.model_validate(_load(_folder(bundle.summary.sid), name))
    return plan.model_copy(update={"budget_usd": request.budget_usd})


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
