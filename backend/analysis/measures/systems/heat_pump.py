"""HVAC_HP: a heat pump replacing the air conditioner and furnace of a home (SPEC 6.2;
physics 02 HVAC-01, HVAC-04, HVAC-05, and the `HVAC_HP` evaluation under HVAC-06).

change: Systems becomes a heat pump with the proposed product's SEER2, HSPF2 and COP at
47 F; electricity for heating. The compressor is marked two-stage so the simulation takes
the seasonal cooling route (HVAC-04), as the HVAC_HP evaluation prescribes.
"""
from __future__ import annotations

from typing import Optional

from backend.schema import BaselineResult, BuildingModel, MeasureResult, PropertyBundle

from ._common import (COP_PER_BTU_PER_WH, HSPF2_PER_HSPF_DUCTED, SEER2_PER_SEER_DUCTED, SIZING_FACTOR,
                      anchor, evidence_of, flag, plain_number, point,
                      set_assumption, tons_from_watts)

MEASURE_ID = "HVAC_HP"
FORMULA_IDS = ("HVAC-01", "HVAC-04", "HVAC-05")

# Proposed product (SPEC 6.2: HVAC_HP needs the product's SEER2, HSPF2 and certified COP at
# 47 F). A representative ducted heat pump, as in the house fixture; not a sourced product.
# Destined for config / the measure library.
HP_SEER2 = 16.5
HP_HSPF2 = 8.2
HP_COP_47F = 3.6

_EVIDENCE_KEYS = ("hvac.system_type", "hvac.thermostat_type", "hvac.duct_location", "hvac.cooling_rating")
_REPLACES = {"central_ac_furnace": "central air conditioner and {fuel} furnace",
             "room_ac": "room air conditioners and {fuel} heating",
             "unknown": "existing air conditioner and {fuel} heating"}


def _ducted(model: BuildingModel) -> bool:
    return model.systems.duct_location != "none"


def check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    s = model.systems
    if s.hvac_type == "heat_pump":
        return ("already_done", "the home is already heated and cooled by a heat pump.")
    if s.hvac_type == "central_plant":
        return ("not_supported", "the home is served by a central plant, which this model does not replace "
                                 "(physics 02 HVAC-00 rule 3).")
    if s.hvac_type == "none":
        return ("not_supported", "no heating or cooling equipment to replace.")
    elec = flag(model, "electrical.service")
    if elec is not None and elec.status == "blocked":
        return ("feasibility", f"Blocked by feasibility flag electrical.service: {elec.message}")
    return None


def _capacity_w(model: BuildingModel, before: Optional[BaselineResult]) -> Optional[float]:
    if model.systems.cooling_capacity_w:
        return model.systems.cooling_capacity_w
    if before is not None and before.peak_cooling_w > 0:
        return SIZING_FACTOR * before.peak_cooling_w          # HVAC-03 sizing rule
    return None


def change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    out = model.model_copy(deep=True)
    ducted = _ducted(out)
    seer = HP_SEER2 / (SEER2_PER_SEER_DUCTED if ducted else 1.0)      # HVAC-01
    hspf = HP_HSPF2 / (HSPF2_PER_HSPF_DUCTED if ducted else 1.0)      # HVAC-01 (ductless: HSPF2 taken as HSPF)
    out.systems = out.systems.model_copy(update={
        "hvac_type": "heat_pump",
        "heating_fuel": "electricity",
        "cooling_rating": point(HP_SEER2, "SEER2"), "cooling_rating_metric": "SEER2",
        "cooling_cop": point(round(seer * COP_PER_BTU_PER_WH, 4), "W/W"),
        "heating_rating": point(HP_HSPF2, "HSPF2"), "heating_rating_metric": "HSPF2",
        "heating_efficiency": point(round(hspf * COP_PER_BTU_PER_WH, 4), "W/W"),
        "heating_cop_47f": HP_COP_47F,
        "compressor_type": "two_stage",
        "hvac_install_year": None,
    })
    note = f"{MEASURE_ID}: proposed heat pump"
    set_assumption(out, "hvac.cooling_rating", point(HP_SEER2, "SEER2"), note)
    set_assumption(out, "hvac.heating_rating", point(HP_HSPF2, "HSPF2"), note)
    return out


def describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
             before: BaselineResult, options: dict) -> MeasureResult:
    s = model.systems
    fuel = {"gas": "gas", "electricity": "electric"}.get(s.heating_fuel, "existing")
    replaces = _REPLACES.get(s.hvac_type, "existing system").format(fuel=fuel)
    kind = "ducted heat pump" if _ducted(model) else "ductless heat pump"
    params: dict = {"seer2": HP_SEER2, "hspf2": HP_HSPF2, "cop_47f": HP_COP_47F}
    warnings = [f"The proposed heat pump (SEER2 {HP_SEER2:g}, HSPF2 {HP_HSPF2:g}, COP {HP_COP_47F:g} at 47 F) "
                f"is a representative product, not a quote; use the chosen unit's certified ratings "
                f"(SPEC.md section 6.2)."]
    cap = _capacity_w(model, before)
    if cap is not None:
        params = {"capacity_tons": plain_number(tons_from_watts(cap)), **params}
        if not s.cooling_capacity_w:
            warnings.append("Capacity sized at 1.2 times the modelled peak cooling load (physics 02 HVAC-03); "
                            "the existing unit's capacity is not known.")
    else:
        warnings.append("Capacity unknown: the measure cannot be priced until the size is known.")
    flags = []
    elec = flag(model, "electrical.service")
    if elec is not None and elec.status in ("unknown", "likely_upgrade"):
        flags.append(elec)
        warnings.append("The electrical service may need an upgrade for a heat pump "
                        f"(electrical.service is {elec.status}).")
    if s.heating_fuel == "gas":
        warnings.append("Gas saved and electricity added are reported separately (physics 02 HVAC-06).")
    evidence = evidence_of(model, _EVIDENCE_KEYS)
    return MeasureResult(
        measure_id=MEASURE_ID, title="Heat pump replacing AC and furnace", applicable=True,
        description=f"Replace the {replaces} with a {kind}.",
        params=params, flags=flags,
        anchors=anchor(bundle, model, "Supply register", evidence, "floor"),
        evidence=evidence, formula_ids=list(FORMULA_IDS), warnings=warnings)
