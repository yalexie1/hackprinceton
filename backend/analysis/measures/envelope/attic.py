"""ENV_ATTIC: attic or roof insulation (SPEC 6.2; physics 02 ENV-01, ENV-03, DEF-01).

Changes only `Surface.u_value` of the roof surfaces over conditioned zones whose U is above the
target. The saving comes from the engine simulating before and after (ZON-04 and the HVAC
entries are the simulate's formula ids, not this card's).
"""
from __future__ import annotations

from typing import Optional

from backend.schema import (BaselineResult, BuildingModel, EvidenceRef, MeasureResult,
                            PropertyBundle, Ranged)

from .common import ceiling_anchor, is_home, no_roof_reason, roof_surfaces

MEASURE_ID = "ENV_ATTIC"
FORMULA_IDS = ("ENV-01", "ENV-03")
FIELDS = ("surfaces[kind=roof].u_value",)

# Target: R-38 over the attic floor, assembly U 0.148 W/m2K (physics 02 DEF-01: "ENV_ATTIC raises
# the attic to R-38 or R-49 (U 0.148 or 0.114)"; S6 Table 4.2.1). Local constant; destined for
# backend/config.py if the owner wants it there.
TARGET_U_W_M2K = 0.148
TARGET_LABEL = "R-38"
_TOL = 1e-9
# Roof boundaries the measure insulates: the roof itself, or a ceiling under an unconditioned attic.
_BOUNDARIES = ("exterior", "adjacent_unconditioned")
_NO_ROOF = "roof insulation changes nothing the suite model can see"


def _targets(model: BuildingModel):
    return [s for s in roof_surfaces(model, _BOUNDARIES) if s.u_value.expected > TARGET_U_W_M2K + _TOL]


def check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    if not roof_surfaces(model, _BOUNDARIES):
        return "not_supported", no_roof_reason(bundle, model, _NO_ROOF)[0]
    if not _targets(model):
        return ("already_done", f"the attic or roof is insulated to {TARGET_LABEL} or better "
                                f"(U {TARGET_U_W_M2K} W/m2K or lower).")
    return None


def change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    """A new model with every roof above the target set to U = target. The low end keeps an
    existing better value; the range otherwise collapses to the installed R-value."""
    ids = {s.id for s in _targets(model)}
    out = model.model_copy(deep=True)
    for s in out.surfaces:
        if s.id in ids:
            u = s.u_value
            s.u_value = Ranged(low=min(u.low, TARGET_U_W_M2K), expected=TARGET_U_W_M2K,
                               high=TARGET_U_W_M2K, unit=u.unit)
    return out


def _evidence(bundle: PropertyBundle, model: BuildingModel) -> list[EvidenceRef]:
    a = next((x for x in model.assumptions if x.key == "roof.u_value"), None)
    if a is not None and a.source != "vintage_default" and a.evidence:
        return list(a.evidence)
    if is_home(bundle):
        return [EvidenceRef(kind="default_table", ref="DEF-01", note="attic ceiling U-value by vintage")]
    return [EvidenceRef(kind="default_table", ref="DEF-11", note="office roof U-value by vintage")]


def describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
             before: BaselineResult, options: dict) -> MeasureResult:
    home = is_home(bundle)
    if not roof_surfaces(model, _BOUNDARIES):
        text, ev = no_roof_reason(bundle, model, _NO_ROOF)
        return MeasureResult(measure_id=MEASURE_ID, title="Attic or roof insulation", applicable=False,
                             not_applicable_reason=text, evidence=ev)
    targets = _targets(model)
    area = round(sum(s.area_m2 for s in targets), 2)
    if home:
        title = f"Attic insulation to {TARGET_LABEL}"
        desc = f"Blow insulation over the attic floor to {TARGET_LABEL} (U {TARGET_U_W_M2K} W/m2K)."
        what = "Attic"
    else:
        title = f"Roof insulation to {TARGET_LABEL}"
        desc = f"Add insulation to the roof over the suite to {TARGET_LABEL} (U {TARGET_U_W_M2K} W/m2K)."
        what = "Roof"
    return MeasureResult(
        measure_id=MEASURE_ID, title=title, applicable=True, description=desc,
        params={"target_u_w_m2k": TARGET_U_W_M2K, "area_m2": area},
        anchors=ceiling_anchor(bundle, model, targets or roof_surfaces(model, _BOUNDARIES), what),
        evidence=_evidence(bundle, model), formula_ids=list(FORMULA_IDS))
