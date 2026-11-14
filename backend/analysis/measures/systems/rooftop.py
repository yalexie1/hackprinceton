"""HVAC_RTU: high-efficiency packaged rooftop units for an office (SPEC 6.2; physics 02
HVAC-00, HVAC-01, HVAC-07).

Evaluated only when a packaged rooftop unit is confirmed by Vexcel, interior vision or the
user (HVAC-00 rule 2); otherwise not applicable with "no packaged rooftop unit confirmed".
change: the cooling rating becomes the proposed IEER; capacity, heating and fans unchanged.
The saving is the simulation's HVAC-07 route, Q_cool x (1/IEER_old - 1/IEER_new) / 0.293071,
with an EER-only existing unit read as its IEER (the conservative baseline of HVAC-07).
"""
from __future__ import annotations

from typing import Optional

from backend.schema import BaselineResult, BuildingModel, MeasureResult, PropertyBundle

from ._common import (COP_PER_BTU_PER_WH, RTU_MIN_CAPACITY_W, SIZING_FACTOR, W_PER_TON, ac_unit_count,
                      anchor, evidence_of, flag, number_value, plain_number, point, round_half,
                      set_assumption, text_value)

MEASURE_ID = "HVAC_RTU"
FORMULA_IDS = ("HVAC-01", "HVAC-07")

# Proposed rating: the federal minimum IEER for 19 to 40 kW air-cooled air conditioners with
# electric or no heat from 1 January 2023 (10 CFR 431.97 Table 1; physics 02 HVAC-07, DEF-05).
# Destined for config / the measure library.
IEER_NEW = 14.8

NOT_CONFIRMED = "no packaged rooftop unit confirmed"


def _confirmed(model: BuildingModel) -> bool:
    """HVAC-00: confirmed when Systems or the registry says rooftop unit (the registry sets it
    only from a Vexcel count above zero, interior vision or the user)."""
    return model.systems.hvac_type == "rooftop_unit" or text_value(model, "hvac.system_type") == "rooftop_unit"


def _existing_ieer(model: BuildingModel) -> Optional[float]:
    s = model.systems
    if s.cooling_rating is not None and s.cooling_rating_metric in ("IEER", "EER"):
        return s.cooling_rating.expected        # HVAC-07: an EER-only unit is read as its IEER
    return None


def check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not _confirmed(model):
        return ("feasibility", NOT_CONFIRMED)
    cap = model.systems.cooling_capacity_w
    if cap is not None and cap < RTU_MIN_CAPACITY_W:
        return ("not_supported", "the packaged unit is under 19 kW and rated by SEER2 (physics 02 HVAC-07); "
                                 "no proposed SEER2 for a small packaged unit is sourced.")
    old = _existing_ieer(model)
    if old is not None and old >= IEER_NEW:
        return ("already_done", f"the rooftop units are already rated at IEER {old:g} or better.")
    return None


def change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    out = model.model_copy(deep=True)
    out.systems = out.systems.model_copy(update={
        "cooling_rating": point(IEER_NEW, "IEER"), "cooling_rating_metric": "IEER",
        "cooling_cop": point(round(IEER_NEW * COP_PER_BTU_PER_WH, 4), "W/W"),
        "hvac_install_year": None,
    })
    set_assumption(out, "hvac.cooling_rating", point(IEER_NEW, "IEER"),
                   f"{MEASURE_ID}: proposed units at the 2023 federal minimum IEER (10 CFR 431.97)")
    return out


def _capacity_tons(model: BuildingModel, before: Optional[BaselineResult]) -> Optional[float]:
    t = number_value(model, "hvac.rtu_capacity_tons")
    if t:
        return round_half(t)
    if model.systems.cooling_capacity_w:
        return round_half(model.systems.cooling_capacity_w / W_PER_TON)
    if before is not None and before.peak_cooling_w > 0:
        return round_half(SIZING_FACTOR * before.peak_cooling_w / W_PER_TON)
    return None


def describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
             before: BaselineResult, options: dict) -> MeasureResult:
    evidence = evidence_of(model, ("hvac.rtu_service",) if flag(model, "hvac.rtu_service")
                           else ("hvac.system_type",))
    if not _confirmed(model):                 # only when called outside the engine's check
        unknown = flag(model, "hvac.system_type")
        return MeasureResult(measure_id=MEASURE_ID, title="High-efficiency rooftop unit", applicable=False,
                             not_applicable_reason=NOT_CONFIRMED, flags=[unknown] if unknown else [],
                             evidence=evidence_of(model, ("hvac.system_type",)))
    units = ac_unit_count(bundle, model)
    tons = _capacity_tons(model, before)
    params: dict = {}
    if tons is not None:
        params["capacity_tons"] = plain_number(tons)
    if units is not None:
        params["units"] = units
    params["ieer_after"] = IEER_NEW
    warnings = ["Owner measure: the units are building plant on the roof.",
                "Replacement before the end of the units' life is valued on energy alone; "
                "no residual value of the old units is credited."]
    if model.systems.cooling_rating_metric == "EER":
        warnings.append("The existing units carry only an EER, used as their IEER: a conservative baseline "
                        "that understates the saving (physics 02 HVAC-07).")
    if tons is None:
        warnings.append("Capacity unknown: the measure cannot be priced until the size is known.")
    elif not number_value(model, "hvac.rtu_capacity_tons") and not model.systems.cooling_capacity_w:
        warnings.append("Capacity sized at 1.2 times the modelled peak cooling load (physics 02 HVAC-03).")
    plural = units is None or units > 1
    what = {None: "packaged rooftop units", 1: "packaged rooftop unit", 2: "two packaged rooftop units",
            3: "three packaged rooftop units"}.get(units, f"{units} packaged rooftop units")
    size = (f" ({tons:g} tons together)" if plural else f" ({tons:g} tons)") if tons is not None else ""
    service = flag(model, "hvac.rtu_service")
    return MeasureResult(
        measure_id=MEASURE_ID, title="High-efficiency rooftop units" if plural else "High-efficiency rooftop unit",
        applicable=True,
        description=f"Replace the {what}{size} with {'units' if plural else 'a unit'} at IEER {IEER_NEW:g} or better.",
        params=params, flags=[service] if service is not None else [],
        anchors=anchor(bundle, model, "Supply diffuser", evidence, "ceiling"),
        evidence=evidence, formula_ids=list(FORMULA_IDS), warnings=warnings)
