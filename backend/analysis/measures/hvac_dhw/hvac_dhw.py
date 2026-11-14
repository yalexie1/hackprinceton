"""Measures HVAC_ECON, HVAC_DUCT, DHW_HPWH (A21; SPEC 6.2, physics 02).

Plain functions over contract types, following the plug-in protocol in
`backend/analysis/measures/engine/engine.py`: per measure a `check`, a `change` (returns a NEW
model, never mutates the input) and a `describe` (the card; `savings` left empty for the engine
to fill from simulate(changed) - simulate(model)). Nothing here imports the engine or a sibling.

- HVAC_ECON (office): only on a confirmed packaged rooftop unit (physics 02 HVAC-00, SPEC 6.2).
  The change switches on the fixed dry-bulb economizer rule of INF-06; the simulation reports
  the saving net of the outdoor-air latent load (INF-07).
- HVAC_DUCT (home): never evaluated. The distribution efficiency of leaky ducts is not sourced
  (physics 02 HVAC-08, section 10 tier A), so `check` returns `not_supported`.
- DHW_HPWH (home): replaces the water heater with a heat pump water heater (DHW-03, DEF-07). The
  engine handles the `dhw.space` feasibility flag (catalogue `blocked_by`).
"""
from __future__ import annotations

from typing import Optional

from backend.schema import (Anchor, BaselineResult, BuildingModel, EvidenceRef, Flag, MeasureResult,
                            PropertyBundle, Ranged)

# ---------------------------------------------------------------- local constants (workplan 2.6)

# INF-06 `theta_limit`, the fixed dry-bulb high limit. The code values (ASHRAE 90.1 6.5.1) are
# paywalled and not sourced (physics 02 section 10, tier A): a parameter, 18 C as in the
# office_houston fixture (the INF-06 worked example uses 21 C). A limit already in the model wins.
ECONOMIZER_LIMIT_C = 18.0

# DEF-07: the proposed heat pump water heater's UEF is a measure-library parameter from the
# product certificate; 2.30 (federal minimum from 6 May 2029, 10 CFR 430.32(d)(2)) is the floor
# and the expected value until a product is chosen; 3.5 is the DHW-03 worked-example product.
HPWH_UEF = Ranged(low=2.30, expected=2.30, high=3.50, unit="-")

UNITS_KEY = "roof-objects.ac-unit.count"     # Vexcel roof-object count of rooftop AC units

HVAC00 = "physics 02 HVAC-00"
DUCT_REASON = ("Distribution efficiency not sourced: the measure is not evaluated "
               "(physics 02 HVAC-08, SPEC.md section 6.2).")

ECON_FORMULAS = ("INF-06", "INF-07", "HVAC-07")
DUCT_FORMULAS = ("HVAC-08", "DEF-06")
HPWH_FORMULAS = ("DHW-01", "DHW-02", "DHW-03", "DEF-07")


# ---------------------------------------------------------------- helpers

def _flag(model: BuildingModel, key: str) -> Optional[Flag]:
    return next((f for f in model.flags if f.key == key), None)


def _assumption(model: BuildingModel, key: str):
    return next((a for a in model.assumptions if a.key == key), None)


def _words(n: int) -> str:
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
            8: "eight", 9: "nine", 10: "ten"}.get(n, str(n))


def _pano_anchors(evidence: list[EvidenceRef]) -> list[Anchor]:
    out, seen = [], set()
    for e in evidence:
        if e.kind == "pano" and e.ref not in seen:
            seen.add(e.ref)
            out.append(Anchor(pano_id=e.ref, label=e.note or e.ref))
    return out


def rooftop_units(bundle: PropertyBundle, model: BuildingModel) -> tuple[Optional[int], Optional[EvidenceRef]]:
    """Count of rooftop AC units: Vexcel primary structure, then the parcel attributes, then the
    roof planes' obstruction counts. (None, None) when nothing counted one."""
    v = bundle.vexcel
    if v is not None:
        structures = sorted(v.structures, key=lambda s: not s.primary)
        for attrs in [s.attributes for s in structures] + [v.attributes]:
            n = attrs.get(UNITS_KEY)
            if isinstance(n, (int, float)) and not isinstance(n, bool) and n >= 1:
                return int(round(n)), EvidenceRef(kind="vexcel_attr", ref=UNITS_KEY,
                                                  note=f"{int(round(n))} as returned")
    n = sum(p.obstruction_counts.get("ac-unit", 0) for p in model.roof_planes)
    if n >= 1:
        return int(n), EvidenceRef(kind="vexcel_attr", ref=UNITS_KEY, note=f"{int(n)} on the roof planes")
    return None, None


# ---------------------------------------------------------------- HVAC_ECON

def econ_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    """HVAC-00 rule 2: evaluated only when a packaged rooftop unit is confirmed (by Vexcel,
    interior vision or the user, which the model records as hvac_type rooftop_unit)."""
    s = model.systems
    if s.hvac_type != "rooftop_unit":
        f = _flag(model, "hvac.system_type")
        why = (f"flag hvac.system_type is {f.status}" if f is not None
               else f"the HVAC system type is {s.hvac_type}")
        return ("feasibility", f"No packaged rooftop unit confirmed: {why} ({HVAC00}).")
    if s.has_economizer:
        return ("already_done", "the rooftop units already have an economizer.")
    return None


def econ_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    out = model.model_copy(deep=True)
    out.systems.has_economizer = True
    if out.systems.economizer_limit_c is None:
        out.systems.economizer_limit_c = ECONOMIZER_LIMIT_C
    return out


def econ_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                  before: BaselineResult, options: dict) -> MeasureResult:
    title = "Economizer and advanced rooftop controls"
    skip = econ_check(bundle, model)
    if skip is not None:
        return MeasureResult(measure_id="HVAC_ECON", title=title, applicable=False,
                             not_applicable_reason=skip[1], params={"skip_reason": skip[0]})
    units, ev = rooftop_units(bundle, model)
    warnings: list[str] = []
    if units is None:
        units = 1
        warnings.append("No rooftop unit was counted on the roof; priced as one unit until the "
                        "count is confirmed.")
    city = bundle.summary.city
    warnings.append(f"Net of the added latent load of humid {city + ' ' if city else 'outdoor '}air "
                    "(physics 02 INF-07).")
    warnings.append("Owner measure: the controls are fitted to building plant.")
    limit = changed.systems.economizer_limit_c
    if model.systems.economizer_limit_c is None:
        warnings.append(f"High-limit temperature {limit:g} °C is a parameter: the code values were not "
                        "sourced (physics 02 INF-06, section 10).")
    each = "each of the two" if units == 2 else (f"each of the {_words(units)}" if units > 1 else "the")
    plural = "s" if units > 1 else ""
    description = (f"Add an advanced controller with a variable-speed fan and economizer control to "
                   f"{each} rooftop unit{plural}. A functional test of the damper and the sensors is "
                   "part of the work. The saving counts free cooling by outdoor air only; fan energy "
                   "is unchanged in the model (physics 02 INF-06).")
    flags = [f for f in (_flag(model, "hvac.rtu_service"),) if f is not None]
    evidence = [ev] if ev is not None else []
    return MeasureResult(measure_id="HVAC_ECON", title=title, applicable=True, description=description,
                         params={"units": units, "economizer_limit_c": limit},
                         flags=flags, evidence=evidence,   # rooftop plant: no tour anchor (fixture)
                         formula_ids=list(ECON_FORMULAS), warnings=warnings)


# ---------------------------------------------------------------- HVAC_DUCT

def duct_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    """HVAC-08: the saving is the difference of two unsourced DSE values, so never evaluated."""
    return ("not_supported", DUCT_REASON)


def duct_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    """No field can be changed on a sourced basis (HVAC-08); a copy of the input."""
    return model.model_copy(deep=True)


def duct_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                  before: BaselineResult, options: dict) -> MeasureResult:
    return MeasureResult(measure_id="HVAC_DUCT", title="Duct sealing", applicable=False,
                         not_applicable_reason=DUCT_REASON, params={"skip_reason": "not_supported"})


# ---------------------------------------------------------------- DHW_HPWH

def hpwh_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    s = model.systems
    if s.dhw_type == "heat_pump":
        return ("already_done", "the water heater is already a heat pump water heater.")
    if s.dhw_location == "conditioned":
        return ("feasibility", "The water heater is inside the conditioned space; the measure assumes "
                               "it sits outside it (physics 02 DHW-03, SPEC.md section 6.2).")
    return None


def hpwh_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    out = model.model_copy(deep=True)
    out.systems.dhw_type = "heat_pump"
    out.systems.dhw_fuel = "electricity"
    out.systems.dhw_efficiency = HPWH_UEF.model_copy()
    return out


def hpwh_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                  before: BaselineResult, options: dict) -> MeasureResult:
    title = "Heat pump water heater"
    skip = hpwh_check(bundle, model)
    if skip is not None:
        return MeasureResult(measure_id="DHW_HPWH", title=title, applicable=False,
                             not_applicable_reason=skip[1], params={"skip_reason": skip[0]})
    s = model.systems
    warnings = ["Assumes the heater sits outside the conditioned space (garage, closet with outdoor "
                "air, or outdoors); the cooling it gives a space is not modelled (physics 02 DHW-03)."]
    if s.dhw_fuel != "electricity":
        warnings.append(f"Fuel switch: the saving is the {s.dhw_fuel} the old heater used minus the "
                        "electricity of the new one (physics 02 DHW-03).")
    warnings.append(f"The new heater's UEF is the federal floor {HPWH_UEF.low:.2f} until a product is "
                    "chosen; a certified product's UEF replaces it (physics 02 DEF-07).")
    a = _assumption(model, "dhw.uef")
    evidence = list(a.evidence) if a is not None else []
    flags = [f for f in (_flag(model, "dhw.space"),) if f is not None]
    evidence += [e for f in flags for e in f.evidence if e not in evidence]
    description = (f"Replace the {s.dhw_fuel if s.dhw_fuel != 'unknown' else ''} {s.dhw_type if s.dhw_type != 'unknown' else ''}"
                   f" water heater with a heat pump water heater (UEF {HPWH_UEF.low:.2f} or better).")
    description = " ".join(description.split())
    return MeasureResult(measure_id="DHW_HPWH", title=title, applicable=True, description=description,
                         params={"units": 1, "uef_old": s.dhw_efficiency.expected,
                                 "uef_new": HPWH_UEF.expected, "fuel_old": s.dhw_fuel},
                         flags=flags, evidence=evidence, anchors=_pano_anchors(evidence),
                         formula_ids=list(HPWH_FORMULAS), warnings=warnings)
