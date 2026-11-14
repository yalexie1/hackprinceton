"""Measure LAYOUT (A23) as an A16 engine plug-in (protocol in measures/engine/engine.py).

LAYOUT changes no model field (`change` returns its input) and sets `savings` itself from the
lighting energy displaced at the recommended desks (LCT-02), with zero cost (SPEC 6.4 item 4).
The point scorer is passed in; the door closes over it when registering:

    from functools import partial
    from backend.analysis import layout
    engine.register("LAYOUT", check=layout.check, change=layout.change,
                    describe=partial(layout.describe, score_point=<A5 scorer>),
                    formula_ids=layout.FORMULA_IDS)

or `layout.measures(score_point)`, which returns the MEASURES dict with the scorer bound.
"""
from __future__ import annotations

import math
from typing import Optional

from backend.schema import (Anchor, BaselineResult, BuildingModel, EnergyUse, EvidenceRef,
                            MeasureResult, PropertyBundle, Ranged)

from .placement import (DESK_FORMULAS, DESK_HEIGHT_M, ScorePoint, candidate_grid, place_desks,
                        window_surfaces)

TITLE = "Desk placement for daylight"
FORMULA_IDS = DESK_FORMULAS + ["LCT-02", "EMI-01"]

# EMI-01: eGRID2023 rev 2, CO2e total-output and non-baseload rates, kg/kWh (same values as
# physics 04 EMI-01; kept here because measure packages never import each other).
EGRID_KG_PER_KWH = {"CAMX": (0.19504, 0.43599), "ERCT": (0.33413, 0.56586), "US": (0.3497, 0.6256)}
STATE_SUBREGION = {"CA": "CAMX", "TX": "ERCT"}

_HOME = {"single_family", "multifamily_unit"}
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
          9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
_COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


def _flow(bundle: PropertyBundle) -> str:
    return "home" if bundle.summary.use_type in _HOME else "office"


def check(bundle: PropertyBundle, model: BuildingModel) -> Optional[tuple[str, str]]:
    # Live office scans can carry room areas with no outline (physics 02 DEF-12): there is no
    # floor to put a desk on, and none is invented.
    if bundle.matterport.rooms and not any(len(r.polygon) >= 3 for r in bundle.matterport.rooms):
        return ("feasibility", "The scan has no room outlines, so there is no floor plan to "
                                 "place desks on.")
    if not window_surfaces(model):
        return ("feasibility", "No windows were found, so no position gets daylight to place a desk by.")
    if not candidate_grid(bundle.matterport):
        return ("feasibility", "No work-area room has floor space at least 0.6 m from the walls "
                               "and clear of the doors.")
    return None


def change(bundle: PropertyBundle, model: BuildingModel) -> BuildingModel:
    return model


def _r(lo: float, exp: float, hi: float, unit: str) -> Ranged:
    return Ranged(low=round(lo, 2), expected=round(exp, 2), high=round(hi, 2), unit=unit)


def _savings(bundle: PropertyBundle, kwh: Ranged) -> tuple[EnergyUse, list[str]]:
    warnings = []
    sub = STATE_SUBREGION.get((bundle.summary.state or "").upper(), "US")
    if sub == "US":
        warnings.append("State unknown: emissions use the U.S. average eGRID rate (EMI-01).")
    ef, ef_nb = EGRID_KG_PER_KWH[sub]
    price = bundle.tariff.electricity_usd_per_kwh
    k = (kwh.low, kwh.expected, kwh.high)
    zero = Ranged(low=0.0, expected=0.0, high=0.0, unit="kWh")
    return EnergyUse(electricity_kwh=_r(*k, "kWh"), gas_kwh=zero,
                     cost_usd=_r(*(v * price for v in k), "USD"),
                     co2_kg=_r(*(v * ef for v in k), "kg"),
                     co2_nonbaseload_kg=_r(*(v * ef_nb for v in k), "kg")), warnings


def _facing(bundle: PropertyBundle, model: BuildingModel, desks) -> Optional[str]:
    """Compass word of the window wall nearest the recommended desks, for the description."""
    floors = {f.id: f for f in bundle.matterport.floors}
    rooms = {r.id: r for r in bundle.matterport.rooms}
    best = None
    for s in window_surfaces(model):
        if s.azimuth_deg is None or not s.source_edge_id:
            continue
        for d in desks:
            floor = floors.get(rooms[d.room_id].floor_id)
            edge = next((e for e in floor.edges if e.id == s.source_edge_id), None) if floor else None
            if edge is None:
                continue
            vs = {v.id: (v.x, v.y) for v in floor.vertices}
            (ax, ay), (bx, by) = vs[edge.vertex_ids[0]], vs[edge.vertex_ids[1]]
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((d.x - ax) * dx + (d.y - ay) * dy) / (dx * dx + dy * dy or 1.0)))
            dist = math.hypot(d.x - ax - t * dx, d.y - ay - t * dy)
            if best is None or dist < best[0]:
                best = (dist, s.azimuth_deg)
    if best is None:
        return None
    return _COMPASS[int(((best[1] % 360) + 22.5) // 45) % 8]


def _nearest_pano(bundle: PropertyBundle, x: float, y: float) -> Optional[str]:
    panos = bundle.matterport.panos
    if not panos:
        return None
    return min(panos, key=lambda p: (p.x - x) ** 2 + (p.y - y) ** 2).id


def describe(bundle: PropertyBundle, model: BuildingModel, changed: BuildingModel,
             before: BaselineResult, options: dict, score_point: Optional[ScorePoint] = None
             ) -> MeasureResult:
    score_point = score_point or (options or {}).get("score_point")
    if score_point is None:
        return MeasureResult(measure_id="LAYOUT", title=TITLE, applicable=False,
                             not_applicable_reason="No point scorer is registered for desk placement.",
                             params={"skip_reason": "not_supported"})
    lay = place_desks(bundle, model, (options or {}).get("desks_requested"), score_point,
                      flow=_flow(bundle))
    res, rec = lay.result, lay.recommended
    if not rec:
        return MeasureResult(measure_id="LAYOUT", title=TITLE, applicable=False,
                             not_applicable_reason="No position meets the clearance and comfort rules.",
                             params={"skip_reason": "feasibility", **lay.params}, layout=res)

    savings, w_emi = _savings(bundle, res.lighting_kwh_saved)
    desks = [s.desk for s in rec]
    n = len(desks)
    where = _facing(bundle, model, desks)
    count = _WORDS.get(n, str(n))
    text = (f"Move {count} desk{'s' if n != 1 else ''} to the positions "
            + (f"along the {where} glazing " if where else "")
            + "with the best daylight, low glare risk and good comfort.")
    if res.control_type == "none":
        text += (" The lighting has no daylight control, so the saving depends on people switching "
                 "lights off and is shown as a range from zero.")
    anchors = []
    for i, d in enumerate(desks, 1):
        anchors.append(Anchor(room_id=d.room_id, pano_id=_nearest_pano(bundle, d.x, d.y),
                              x=d.x, y=d.y, z=DESK_HEIGHT_M, label=f"Recommended desk {i}"))
    evidence = []
    if res.window_source == "vision":
        for pid in dict.fromkeys(a.pano_id for a in anchors if a.pano_id):
            evidence.append(EvidenceRef(kind="pano", ref=pid, note="window geometry read from this panorama area"))
    return MeasureResult(measure_id="LAYOUT", title=TITLE, applicable=True, description=text,
                         params=dict(lay.params), savings=savings, anchors=anchors, evidence=evidence,
                         formula_ids=list(FORMULA_IDS), layout=res,
                         warnings=list(dict.fromkeys(res.warnings + w_emi)))


MEASURES = {"LAYOUT": (check, change, describe, FORMULA_IDS)}


def measures(score_point: ScorePoint) -> dict:
    """MEASURES with the point scorer bound into `describe`."""
    def bound(bundle, model, changed, before, options):
        return describe(bundle, model, changed, before, options, score_point=score_point)
    return {"LAYOUT": (check, change, bound, FORMULA_IDS)}
