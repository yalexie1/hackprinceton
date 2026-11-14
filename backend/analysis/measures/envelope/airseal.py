"""ENV_AIRSEAL: air sealing (SPEC 6.2; physics 02 INF-02, INF-03, INF-05, DEF-04, section 10).

The leakage after sealing has no opened source (physics 02 section 10, tier A; SPEC 6.2): it is
a measure parameter carried with a wide range, and every result says it rests on it.

Fields changed:
- homes: `Systems.infiltration_ach50` (the INF-02/INF-03 input) and `Systems.infiltration_ach`
  (the placeholder natural rate used when ACH50 is absent), both scaled by the same factors;
- offices: `Systems.envelope_leakage_l_s_m2_75pa` (the INF-05 input).
"""
from __future__ import annotations

from typing import Optional

from backend.schema import (BaselineResult, BuildingModel, EvidenceRef, Flag, MeasureResult,
                            PropertyBundle, Ranged)

from .common import (assumption, conditioned_floor_area, conditioned_zone_ids, facade_anchor,
                     is_home, number_word, scaled)

MEASURE_ID = "ENV_AIRSEAL"
FIELDS_HOME = ("systems.infiltration_ach50", "systems.infiltration_ach")
FIELDS_OFFICE = ("systems.envelope_leakage_l_s_m2_75pa",)

# --- parameters with no opened source (physics 02 section 10, tier A). Local; destined for config.
# Offices: leakage at 75 Pa after sealing, L/(s.m2) of envelope. Expected 5.0 as in the fixtures;
# low 2.0 is the INF-05 value for buildings from 2005; high is no improvement (the value before).
OFFICE_LEAKAGE_AFTER = 5.0
OFFICE_LEAKAGE_AFTER_LOW = 2.0
# Homes: fraction of ACH50 removed, low / expected / high. Judgement, bracketed by the jobs the
# ENV_AIRSEAL cost row prices ("about 20 %, 40 % and 33 % leakage reduction", physics 04 COST-01).
HOME_REDUCTION = (0.20, 0.30, 0.40)
# Homes at or below this ACH50 are taken as already sealed: a current new house built to the
# Building America benchmark is 7 (physics 02 DEF-04, S10).
HOME_ACH50_SEALED = 7.0
_TOL = 1e-9

ASSUMPTION_WARNING = ("Rests on the leakage after sealing, a parameter with no opened source "
                      "(SPEC.md section 6.2).")
BUILDING_WALL_WARNING = ("The exterior wall belongs to the building: work on it needs the owner's "
                         "agreement and the building engineer's access.")
CONSENT_FLAG = "lease.alteration_consent"


def _exterior(model: BuildingModel) -> list:
    zones = conditioned_zone_ids(model)
    return [s for s in model.surfaces if s.boundary == "exterior" and s.zone_id in zones
            and s.kind in ("wall", "roof", "window", "door")]


def _office_before(model: BuildingModel) -> Ranged:
    r = model.systems.envelope_leakage_l_s_m2_75pa
    # INF-05: 7.5 L/(s.m2) when unrecorded (the zone model uses the same default)
    return r if r is not None else Ranged(low=2.0, expected=7.5, high=7.5, unit="L/s.m2 at 75 Pa")


def check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not _exterior(model):
        return "not_supported", "The model has no exterior envelope to seal."
    if is_home(bundle):
        a50 = model.systems.infiltration_ach50
        if a50 is not None and a50.expected <= HOME_ACH50_SEALED + _TOL:
            return ("already_done", f"the home's air leakage is {a50.expected:g} ACH50, at or below "
                                    f"{HOME_ACH50_SEALED:g}, the level of a current new house.")
        return None
    if _office_before(model).expected <= OFFICE_LEAKAGE_AFTER + _TOL:
        return ("already_done", f"the envelope leakage is {_office_before(model).expected:g} L/s.m2 at "
                                f"75 Pa, at or below the {OFFICE_LEAKAGE_AFTER:g} that sealing reaches.")
    return None


def _office_after(before: Ranged) -> Ranged:
    t = min(OFFICE_LEAKAGE_AFTER, before.expected)
    return Ranged(low=min(OFFICE_LEAKAGE_AFTER_LOW, t), expected=t, high=max(t, before.expected),
                  unit=before.unit)


def change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    out = model.model_copy(deep=True)
    sysm = out.systems
    if is_home(bundle):
        lo, ex, hi = HOME_REDUCTION
        # the largest reduction gives the lowest leakage, so it scales the low end
        f = (1.0 - hi, 1.0 - ex, 1.0 - lo)
        if sysm.infiltration_ach50 is not None:
            sysm.infiltration_ach50 = scaled(sysm.infiltration_ach50, *f)
        sysm.infiltration_ach = scaled(sysm.infiltration_ach, *f)
    else:
        sysm.envelope_leakage_l_s_m2_75pa = _office_after(_office_before(model))
    return out


def _evidence(bundle: PropertyBundle, model: BuildingModel) -> list[EvidenceRef]:
    if is_home(bundle):
        a = assumption(model, "infiltration.ach50")
        if a is not None and a.source != "vintage_default" and a.evidence:
            return list(a.evidence)
        a50 = model.systems.infiltration_ach50
        note = f"ACH50 {a50.expected:g} by vintage" if a50 is not None else "ACH50 by vintage"
        return [EvidenceRef(kind="default_table", ref="DEF-04", note=note)]
    a = assumption(model, "infiltration.leakage_75pa")
    if a is not None and a.source != "vintage_default" and a.evidence:
        return list(a.evidence)
    year = bundle.costar.year_built if bundle.costar else None
    before = _office_before(model).expected
    when = "" if year is None else (" before 2004" if year <= 2004 else " from 2005")
    return [EvidenceRef(kind="default_table", ref="INF-05", note=f"{before:g} L/s.m2 at 75 Pa{when}")]


def _facades(model: BuildingModel) -> int:
    zones = conditioned_zone_ids(model)
    return len({round(s.azimuth_deg % 360.0, 1) for s in model.surfaces
                if s.kind == "wall" and s.boundary == "exterior" and s.zone_id in zones
                and s.azimuth_deg is not None})


def describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
             before: BaselineResult, options: dict) -> MeasureResult:
    home = is_home(bundle)
    warnings = [ASSUMPTION_WARNING]
    flags: list[Flag] = [f for f in model.flags if f.key == CONSENT_FLAG]
    stories = bundle.costar.stories if bundle.costar else None
    if home:
        lo, ex, hi = HOME_REDUCTION
        after = changed.systems.infiltration_ach50
        params = {"leakage_reduction_fraction": ex, "floor_area_m2": conditioned_floor_area(model)}
        if after is not None:
            params["ach50_after"] = round(after.expected, 2)
        desc = ("Seal the attic floor, the top plates, and the gaps around windows, doors and "
                "penetrations, then check the result with a blower-door test.")
        formula_ids = ["INF-02", "INF-03"]
    else:
        params = {"leakage_after_l_s_m2_75pa": changed.systems.envelope_leakage_l_s_m2_75pa.expected,
                  "floor_area_m2": conditioned_floor_area(model)}
        n = _facades(model)
        suite = bool(stories and stories > 1)
        if suite:
            desc = ("Seal the suite's side of the exterior wall: window perimeters, spandrel joints and "
                    f"penetrations along the {number_word(n)} exterior wall{'s' if n != 1 else ''}.")
            if not flags:
                warnings.append(BUILDING_WALL_WARNING)
        else:
            desc = "Seal window perimeters, spandrel joints and penetrations on the exterior walls and roof."
        formula_ids = ["INF-05"]
    return MeasureResult(
        measure_id=MEASURE_ID, title="Air sealing", applicable=True, description=desc,
        params=params, flags=flags, anchors=facade_anchor(bundle, model),
        evidence=_evidence(bundle, model), formula_ids=formula_ids, warnings=warnings)
