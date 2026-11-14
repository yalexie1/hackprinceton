"""ENV_WALL, wall insulation (SPEC 6.2; physics 02 DEF-01, ENV-03).

Cavity fill of an existing wood-frame wall: dense-pack insulation blown into the empty
cavities, the measure the cost row prices (physics 04 COST-01: "cavity fill of existing
walls", R-13 cellulose). Home flow only: SPEC 6.2 offers no wall measure for offices.

The change sets the U-value of every exterior wall whose cavity is not yet insulated to the
filled 2x4 assembly; window, door, roof and floor surfaces are untouched.
"""
from __future__ import annotations

from typing import Optional

from backend.schema import (BaselineResult, BuildingModel, EvidenceRef, MeasureResult,
                            PropertyBundle, Ranged, Surface)

from .common import (EPS, anchors_for, assumption, assumption_evidence, facing_list, is_home,
                     loss_surfaces, total_area)

MEASURE_ID = "ENV_WALL"
TITLE = "Wall insulation"
FORMULA_IDS = ("DEF-01", "ENV-03", "ZON-04", "EMI-01")

# Filled 2x4 wood-frame wall at 16 in. centres, whole-assembly U from S6 Table 4.3.1 column A
# as quoted in physics 02 DEF-01 (Btu/(h ft2 F) x 5.678263): R-15 0.095 -> 0.539 (low),
# R-13 0.102 -> 0.579 (expected; the R-13 cellulose of the COST-01 row), R-11 0.110 -> 0.625
# (high; DEF-01's "retrofitted" allowance). Measure constants, not in backend/config.py.
TARGET_U = Ranged(low=0.539, expected=0.579, high=0.625, unit="W/m2K")
TARGET_LABEL = "R-13 dense-pack cavity fill"
# A wall at or below R-11 (DEF-01: 0.625) already has cavity insulation: nothing to fill.
INSULATED_U = 0.625

# Wall materials a cavity fill cannot treat (vision reads wall material, SPEC 5.2).
NO_CAVITY_MATERIALS = ("masonry", "brick", "concrete", "stone", "block", "adobe")

COST_KEY = "area_m2"     # finance/costs: ENV_WALL is priced per m2 of wall treated


def _uninsulated(model: BuildingModel) -> list[Surface]:
    return [s for s in loss_surfaces(model, "wall") if s.u_value.expected > INSULATED_U + EPS]


def _material(model: BuildingModel) -> Optional[str]:
    a = assumption(model, "wall.material")
    return a.value.lower() if a is not None and isinstance(a.value, str) else None


def wall_check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not is_home(bundle):
        return ("not_supported", "Wall insulation is a home measure (SPEC.md section 6.2); office "
                                 "walls are curtain wall, steel frame or mass and have no cavity to fill.")
    walls = loss_surfaces(model, "wall")
    if not walls:
        return ("feasibility", "The model has no exterior wall to insulate.")
    mat = _material(model)
    if mat is not None and any(m in mat for m in NO_CAVITY_MATERIALS):
        return ("feasibility", f"The walls read as {mat}: there is no framed cavity to fill.")
    if not _uninsulated(model):
        return ("already_done", f"every exterior wall is already at U {INSULATED_U} W/m2K "
                                f"(R-11 cavity insulation) or better.")
    return None


def wall_change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    """A new model: each uninsulated exterior wall takes the filled-cavity U. No end of the
    range gets worse than before."""
    out = model.model_copy(deep=True)
    ids = {s.id for s in _uninsulated(model)}
    for s in out.surfaces:
        if s.id in ids:
            u = s.u_value
            s.u_value = Ranged(low=min(u.low, TARGET_U.low), expected=min(u.expected, TARGET_U.expected),
                               high=min(u.high, TARGET_U.high), unit=u.unit)
    return out


def wall_describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
                  before: BaselineResult, options: dict) -> MeasureResult:
    walls = _uninsulated(model)
    area = total_area(walls)
    old_u = max(s.u_value.expected for s in walls)
    params = {"target_u_w_m2k": TARGET_U.expected, COST_KEY: area,
              "wall_surface_ids": [s.id for s in walls]}
    warnings = []
    wa = assumption(model, "wall.u_value")
    if wa is None or wa.source == "vintage_default":
        warnings.append("Rests on the vintage default for the wall (physics 02 DEF-01): an empty cavity "
                        "is assumed. Confirm it with a borescope or an infrared scan before ordering.")
    warnings.append("Assumes 2x4 wood framing at 16 in. centres; the filled-wall U-value is the "
                    "published assembly value (physics 02 DEF-01), not a calculation for this wall.")
    evidence = assumption_evidence(model, ["wall.u_value", "wall.material", "building.year_built"])
    evidence.append(EvidenceRef(kind="default_table", ref="DEF-01",
                                note=f"{TARGET_LABEL}: U {TARGET_U.low} / {TARGET_U.expected} / "
                                     f"{TARGET_U.high} W/m2K (S6 Table 4.3.1, R-15 / R-13 / R-11)"))
    return MeasureResult(
        measure_id=MEASURE_ID, title=TITLE, applicable=True,
        description=(f"Blow R-13 dense-pack insulation into the {area:g} m2 of uninsulated "
                     f"{facing_list(walls)} exterior wall: U from {old_u:g} to "
                     f"{TARGET_U.expected:g} W/m2K."),
        params=params, anchors=anchors_for(bundle, walls, "wall"), evidence=evidence,
        formula_ids=list(FORMULA_IDS), warnings=warnings)
