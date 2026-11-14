"""Shared helpers for the A18 systems measures: unit constants, assumption and flag lookup,
quantities and where to pin a card. Contract types only; no engine, physics or sibling imports.

Constants destined for `backend/config.py` stay here with a comment (workplan 2.6).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from backend.schema import (Anchor, Assumption, BuildingModel, EvidenceRef, Flag, PropertyBundle,
                            Ranged, Room)

# ---- unit conversions (physics 02 HVAC-01; local, not config) ----
COP_PER_BTU_PER_WH = 0.293071      # HVAC-01: EER, SEER, HSPF in Btu/(W.h) to W/W
SEER2_PER_SEER_DUCTED = 0.95       # HVAC-01, ducted split systems (EER2 / EER too)
HSPF2_PER_HSPF_DUCTED = 0.85       # HVAC-01, ducted split systems
W_PER_TON = 3516.853               # 12 000 Btu/h per ton of refrigeration (exact by definition)
SIZING_FACTOR = 1.2                # HVAC-03: capacity = 1.2 x peak hourly cooling load if unknown (S11)
RTU_MIN_CAPACITY_W = 19000.0       # HVAC-07: packaged units of 19 kW and above are rated by IEER

AC_COUNT_KEY = "roof-objects.ac-unit.count"   # Vexcel attribute (data-integration, registry A10)

# Card evidence keeps only what was observed or stated; default tables are not evidence of the measure.
_OBSERVED_KINDS = {"pano", "ortho", "oblique", "matterport_field", "vexcel_attr", "costar_field", "user"}


def assumption(model: BuildingModel, key: str) -> Optional[Assumption]:
    return next((a for a in model.assumptions if a.key == key), None)


def text_value(model: BuildingModel, key: str) -> Optional[str]:
    a = assumption(model, key)
    return a.value.strip().lower() if a is not None and isinstance(a.value, str) else None


def number_value(model: BuildingModel, key: str) -> Optional[float]:
    a = assumption(model, key)
    return a.value.expected if a is not None and isinstance(a.value, Ranged) else None


def flag(model: BuildingModel, key: str) -> Optional[Flag]:
    return next((f for f in model.flags if f.key == key), None)


def floor_area_m2(model: BuildingModel) -> float:
    return sum(z.floor_area_m2 for z in model.zones if z.conditioned)


def point(value: float, unit: str) -> Ranged:
    return Ranged(low=value, expected=value, high=value, unit=unit)


def scaled(r: Ranged, factor: float) -> Ranged:
    return Ranged(low=r.low * factor, expected=r.expected * factor, high=r.high * factor, unit=r.unit)


def round_half(x: float) -> float:
    """Nearest half unit (equipment is sold in half-ton steps); never below 0.5."""
    return max(0.5, round(x * 2.0) / 2.0)


def tons_from_watts(w: float) -> float:
    return round_half(w / W_PER_TON)


def plain_number(x: float):
    """3.0 -> 3 so params read like the fixtures; other values unchanged."""
    return int(x) if float(x).is_integer() else x


def set_assumption(model: BuildingModel, key: str, value: Ranged, note: str) -> None:
    """Keep the registry in step with Systems in a changed model: replace the value of an
    existing assumption (never add one). `model` must already be the measure's own copy."""
    for i, a in enumerate(model.assumptions):
        if a.key == key:
            model.assumptions[i] = a.model_copy(update={
                "value": value, "source": "published_default",
                "evidence": [EvidenceRef(kind="default_table", ref=key, note=note)]})


def evidence_of(model: BuildingModel, keys: Iterable[str]) -> list[EvidenceRef]:
    """Observed or stated evidence behind the named assumptions and flags, first seen first,
    without repeats."""
    out: list[EvidenceRef] = []
    seen: set[tuple[str, str]] = set()
    for key in keys:
        items = []
        f = flag(model, key)
        if f is not None:
            items.extend(f.evidence)
        a = assumption(model, key)
        if a is not None:
            items.extend(a.evidence)
        for e in items:
            if e.kind in _OBSERVED_KINDS and (e.kind, e.ref) not in seen:
                seen.add((e.kind, e.ref))
                out.append(e)
    return out


def ac_unit_count(bundle: PropertyBundle, model: BuildingModel) -> Optional[int]:
    """Rooftop AC units counted by Vexcel: the bundle attribute, else the count the registry
    wrote into its evidence note ("2 as returned"). None when not counted or zero."""
    if bundle.vexcel is not None:
        n = bundle.vexcel.attributes.get(AC_COUNT_KEY)
        if isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0:
            return int(n)
    for e in [e for a in model.assumptions for e in a.evidence] + [e for f in model.flags for e in f.evidence]:
        if e.ref == AC_COUNT_KEY and e.note:
            m = re.match(r"\s*(\d+)", e.note)
            if m and int(m.group(1)) > 0:
                return int(m.group(1))
    return None


# ---- where to pin the card ----

def _inside(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    """Even-odd ray cast."""
    hit = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def _model_rooms(bundle: PropertyBundle, model: BuildingModel) -> list[Room]:
    ids = {r for z in model.zones if z.conditioned for r in z.room_ids}
    rooms = [r for r in bundle.matterport.rooms if r.id in ids]
    return rooms or list(bundle.matterport.rooms)


def _room_of(bundle: PropertyBundle, model: BuildingModel, x: float, y: float) -> Optional[Room]:
    rooms = _model_rooms(bundle, model)
    for r in rooms:
        if len(r.polygon) >= 3 and _inside(x, y, r.polygon):
            return r
    return None


def anchor(bundle: PropertyBundle, model: BuildingModel, label: str, evidence: list[EvidenceRef],
           height: str) -> list[Anchor]:
    """One pin. Pano: the first pano in the evidence, else the first pano inside the largest
    room of the model. Position: that pano's plan position, at the ceiling (`height="ceiling"`,
    the room height) or near the floor (`height="floor"`, 0.2 m, where supply registers sit
    in a ducted home). No pano at all: the largest room without coordinates."""
    panos = {p.id: p for p in bundle.matterport.panos}
    pano = next((panos[e.ref] for e in evidence if e.kind == "pano" and e.ref in panos), None)
    room = _room_of(bundle, model, pano.x, pano.y) if pano is not None else None
    if pano is None:
        rooms = sorted(_model_rooms(bundle, model), key=lambda r: -(r.area_m2 or 0.0))
        room = rooms[0] if rooms else None
        if room is not None and len(room.polygon) >= 3:
            pano = next((p for p in bundle.matterport.panos if _inside(p.x, p.y, room.polygon)), None)
    if pano is None:
        return [Anchor(room_id=room.id if room else None, label=label)]
    if height == "ceiling":
        h = room.height_m if room is not None and room.height_m else number_value(model, "geometry.ceiling_height_m")
        z = round(h, 2) if h else None
    else:
        z = 0.2
    return [Anchor(room_id=room.id if room else None, pano_id=pano.id, x=pano.x, y=pano.y, z=z, label=label)]
