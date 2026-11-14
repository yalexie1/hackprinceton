"""ROOF_COOL: cool roof coating or membrane (SPEC 6.2; physics 02 ENV-05, DEF-02, section 10).

Changes only `Surface.solar_absorptance` of the exterior roof surfaces over conditioned zones.
The zone model runs with both absorptances (ENV-05: the cool roof also raises the heating
need). On a home the roof is taken to sit over a vented attic, whose attenuation of the roof
gain is not sourced (physics 02 section 10, tier A): the result is an upper bound and says so.
"""
from __future__ import annotations

from typing import Optional

from backend.schema import (BaselineResult, BuildingModel, EvidenceRef, MeasureResult,
                            PropertyBundle, Ranged)

from .common import assumption, is_home, no_roof_reason, roof_surfaces

MEASURE_ID = "ROOF_COOL"
FORMULA_IDS = ("ENV-05",)
FIELDS = ("surfaces[kind=roof].solar_absorptance",)

# Cool roof after the measure: 0.25 / 0.30 / 0.40 (physics 02 DEF-02, "cool roof after ROOF_COOL";
# 0.40 is the aged end). Local constants; destined for backend/config.py if wanted there.
ABSORPTANCE_AFTER = Ranged(low=0.25, expected=0.30, high=0.40, unit="-")
# Absorptance assumed for a roof surface with none recorded; the zone model uses the same value
# (physics 02 DEF-02, "low-slope membrane, metal, or unknown commercial roof").
ABSORPTANCE_UNKNOWN = 0.65
_NO_ROOF = "a cool roof changes nothing the suite model can see"
VENTED_ATTIC_WARNING = "Vented attic: the result is an upper bound (SPEC.md section 6.2)."


def _alpha(s) -> float:
    return s.solar_absorptance.expected if s.solar_absorptance is not None else ABSORPTANCE_UNKNOWN


def _targets(model: BuildingModel):
    return [s for s in roof_surfaces(model) if _alpha(s) > ABSORPTANCE_AFTER.high]


def _vented_attic(bundle: PropertyBundle, model: BuildingModel) -> bool:
    """Homes are taken to have a vented attic unless the roof is recorded as flat."""
    if not is_home(bundle):
        return False
    shape = assumption(model, "roof.shape")
    return not (shape is not None and isinstance(shape.value, str) and shape.value.lower() == "flat")


def check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not roof_surfaces(model):
        return "not_supported", no_roof_reason(bundle, model, _NO_ROOF)[0]
    if not _targets(model):
        return ("already_done", f"the roof's solar absorptance is {ABSORPTANCE_AFTER.high:.2f} "
                                f"or lower, the range of a cool roof.")
    return None


def change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    ids = {s.id for s in _targets(model)}
    out = model.model_copy(deep=True)
    for s in out.surfaces:
        if s.id in ids:
            s.solar_absorptance = ABSORPTANCE_AFTER.model_copy()
    return out


def _evidence(model: BuildingModel, alpha_before: float) -> list[EvidenceRef]:
    ev: list[EvidenceRef] = []
    material = assumption(model, "roof.material")
    absorb = assumption(model, "roof.absorptance")
    if material is not None:
        ev.extend(material.evidence)
    if absorb is not None and absorb.source != "vintage_default":
        ev.extend(e for e in absorb.evidence if e not in ev)
    name = material.value if material is not None and isinstance(material.value, str) else "roof"
    ev.append(EvidenceRef(kind="default_table", ref="DEF-02",
                          note=f"{name} {alpha_before:.2f}, cool roof {ABSORPTANCE_AFTER.expected:.2f}"))
    return ev


def describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
             before: BaselineResult, options: dict) -> MeasureResult:
    if not roof_surfaces(model):
        text, ev = no_roof_reason(bundle, model, _NO_ROOF)
        return MeasureResult(measure_id=MEASURE_ID, title="Cool roof coating or membrane",
                             applicable=False, not_applicable_reason=text, evidence=ev)
    home = is_home(bundle)
    targets = _targets(model) or roof_surfaces(model)
    area = sum(s.area_m2 for s in targets)
    if home and model.roof_planes:
        area = sum(p.area_m2 for p in model.roof_planes)   # the coating covers the pitched roof itself
    alpha_before = max(_alpha(s) for s in targets)
    if home:
        title, desc = "Cool roof coating", "Reflective coating on the roof to cut solar heat gain."
    else:
        title = "Cool roof coating or membrane"
        desc = "Reflective coating or membrane on the low-slope roof to cut solar heat gain."
    return MeasureResult(
        measure_id=MEASURE_ID, title=title, applicable=True, description=desc,
        params={"absorptance_after": ABSORPTANCE_AFTER.expected, "roof_area_m2": round(area, 2)},
        evidence=_evidence(model, alpha_before), formula_ids=list(FORMULA_IDS),
        warnings=[VENTED_ATTIC_WARNING] if _vented_attic(bundle, model) else [])
