"""Helpers shared by the three envelope measures (A17): flow, roof surfaces, anchors, evidence.

Contract types only; imports neither the engine nor a sibling package (workplan 2.6).
"""
from __future__ import annotations

import math
import re
from typing import Iterable, Optional

from backend.schema import (Anchor, Assumption, BuildingModel, EvidenceRef, PropertyBundle,
                            Ranged, Room, Surface)

_HOME_USES = {"single_family", "multifamily_unit"}

# Anchor placement (judgement, local; not physics): how far inside the wall the pin sits.
ANCHOR_INSET_M = 0.2
_EPS = 1e-6

_NUMBERS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
_COMPASS = ("North", "North-east", "East", "South-east", "South", "South-west", "West", "North-west")


def is_home(bundle: PropertyBundle) -> bool:
    """Home flow for single-family and multifamily units, office flow for offices, else by
    segment. Same rule as the engine's catalogue (SPEC 6.2), restated here so this package
    does not import the engine."""
    s = bundle.summary
    if s.use_type in _HOME_USES:
        return True
    if s.use_type == "office":
        return False
    return s.segment == "residential"


def assumption(model: BuildingModel, key: str) -> Optional[Assumption]:
    return next((a for a in model.assumptions if a.key == key), None)


def conditioned_zone_ids(model: BuildingModel) -> set[str]:
    return {z.id for z in model.zones if z.conditioned}


def roof_surfaces(model: BuildingModel, boundaries: Iterable[str] = ("exterior",)) -> list[Surface]:
    """Roof surfaces of conditioned zones with one of the given boundaries."""
    zones = conditioned_zone_ids(model)
    bset = set(boundaries)
    return [s for s in model.surfaces if s.kind == "roof" and s.boundary in bset and s.zone_id in zones]


def conditioned_floor_area(model: BuildingModel) -> float:
    return round(sum(z.floor_area_m2 for z in model.zones if z.conditioned), 2)


def scaled(r: Ranged, f_low: float, f_exp: float, f_high: float) -> Ranged:
    """r with each percentile multiplied by its own factor, re-ordered so low <= expected <= high."""
    vals = sorted((r.low * f_low, r.expected * f_exp, r.high * f_high))
    exp = r.expected * f_exp
    return Ranged(low=round(min(vals[0], exp), 4), expected=round(exp, 4),
                  high=round(max(vals[2], exp), 4), unit=r.unit)


# ---------------------------------------------------------------- where the suite sits

def _floor_number(bundle: PropertyBundle, model: BuildingModel) -> Optional[int]:
    room_ids = {r for z in model.zones for r in z.room_ids}
    floor_ids = {r.floor_id for r in bundle.matterport.rooms if r.id in room_ids}
    for f in bundle.matterport.floors:
        if f.id in floor_ids:
            m = re.search(r"(\d+)", f.label or "") or re.search(r"(\d+)", f.id)
            if m:
                return int(m.group(1))
    return None


def no_roof_reason(bundle: PropertyBundle, model: BuildingModel, consequence: str) -> tuple[str, list[EvidenceRef]]:
    """The sentence and evidence for a model with no roof over a conditioned zone."""
    stories = bundle.costar.stories if bundle.costar else None
    floor = _floor_number(bundle, model)
    if stories and floor and stories > 1:
        text = (f"The suite is on floor {floor} of {stories}: the roof is not part of its envelope, "
                f"so {consequence}.")
        return text, [EvidenceRef(kind="costar_field", ref="CostarData.stories", note=str(stories))]
    return (f"The model has no roof over a conditioned zone, so {consequence}.", [])


# ---------------------------------------------------------------- anchors

def compass(azimuth_deg: float) -> str:
    return _COMPASS[int(((azimuth_deg % 360.0) + 22.5) // 45.0) % 8]


def number_word(n: int) -> str:
    return _NUMBERS.get(n, str(n))


def _poly_area(poly) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]))) / 2.0


def _inside(x: float, y: float, poly) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xc:
                inside = not inside
    return inside


def _rooms_of(bundle: PropertyBundle, room_ids: set[str]) -> list[Room]:
    return [r for r in bundle.matterport.rooms if r.id in room_ids]


def _room_at(bundle: PropertyBundle, x: float, y: float, room_ids: set[str]) -> Optional[Room]:
    for r in _rooms_of(bundle, room_ids):
        if len(r.polygon) >= 3 and _inside(x, y, [tuple(p) for p in r.polygon]):
            return r
    return None


def _zone_room_ids(model: BuildingModel, zone_ids: set[str]) -> set[str]:
    return {r for z in model.zones if z.id in zone_ids for r in z.room_ids}


def ceiling_anchor(bundle: PropertyBundle, model: BuildingModel, surfaces: list[Surface],
                   what: str) -> list[Anchor]:
    """One pin at the ceiling of the largest room under the given roof surfaces, at the pano in
    that room nearest its centre. Label "<what> above the <room label>"."""
    zone_ids = {s.zone_id for s in surfaces}
    rooms = [r for r in _rooms_of(bundle, _zone_room_ids(model, zone_ids)) if len(r.polygon) >= 3 or r.area_m2]
    if not rooms:
        return []
    room = max(rooms, key=lambda r: (r.area_m2 or _poly_area([tuple(p) for p in r.polygon]), r.id))
    poly = [tuple(p) for p in room.polygon]
    panos = [p for p in bundle.matterport.panos if len(poly) >= 3 and _inside(p.x, p.y, poly)]
    zone = next(z for z in model.zones if z.id in zone_ids and room.id in z.room_ids)
    z = room.height_m or (zone.volume_m3 / zone.floor_area_m2 if zone.floor_area_m2 else None)
    where = f"the {room.label.lower()}" if room.label else "the suite"
    label = f"{what} above {where}"
    if panos:
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        pano = min(panos, key=lambda p: (round(math.hypot(p.x - cx, p.y - cy), 6), p.id))
        return [Anchor(room_id=room.id, pano_id=pano.id, x=pano.x, y=pano.y,
                       z=round(z, 2) if z else None, label=label)]
    return [Anchor(room_id=room.id, label=label)]


def _edge_segments(bundle: PropertyBundle) -> dict[str, tuple[tuple[float, float], tuple[float, float]]]:
    out = {}
    for f in bundle.matterport.floors:
        verts = {v.id: (v.x, v.y) for v in f.vertices}
        for e in f.edges:
            a, b = e.vertex_ids
            if a in verts and b in verts:
                out[e.id] = (verts[a], verts[b])
    return out


def _project(px, py, a, b):
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    qx, qy = ax + t * dx, ay + t * dy
    return qx, qy, math.hypot(px - qx, py - qy)


def facade_anchor(bundle: PropertyBundle, model: BuildingModel) -> list[Anchor]:
    """One pin on the sunniest facade: the exterior walls whose azimuth is nearest south (ties:
    the most glazing). The pano nearest that facade (ties: nearest a facade corner, where
    joints and window perimeters meet; then the later pano) is projected onto the wall and set
    ANCHOR_INSET_M inside it, at pano height. Label "<compass> glazing" or "<compass> wall"."""
    zones = conditioned_zone_ids(model)
    segs = _edge_segments(bundle)
    walls = [s for s in model.surfaces if s.kind == "wall" and s.boundary == "exterior"
             and s.zone_id in zones and s.azimuth_deg is not None and s.source_edge_id in segs]
    if not walls:
        return []
    glazing: dict[str, float] = {}
    for s in model.surfaces:
        if s.kind == "window" and s.parent_surface_id:
            glazing[s.parent_surface_id] = glazing.get(s.parent_surface_id, 0.0) + s.area_m2

    def off_south(az: float) -> float:
        return round(abs(((az - 180.0) + 180.0) % 360.0 - 180.0), 1)

    groups: dict[float, list[Surface]] = {}
    for w in walls:
        groups.setdefault(round(w.azimuth_deg % 360.0, 1), []).append(w)
    az = min(groups, key=lambda a: (off_south(a), -sum(glazing.get(w.id, 0.0) for w in groups[a]), a))
    facade = groups[az]

    ends: dict[tuple[float, float], int] = {}
    for w in facade:
        for p in segs[w.source_edge_id]:
            key = (round(p[0], 3), round(p[1], 3))
            ends[key] = ends.get(key, 0) + 1
    corners = [p for p, n in ends.items() if n == 1] or list(ends)

    room_ids = _zone_room_ids(model, zones)
    panos = [p for p in bundle.matterport.panos if _room_at(bundle, p.x, p.y, room_ids) is not None]
    if not panos:
        return []
    best = None
    for i, p in enumerate(panos):
        q = min((_project(p.x, p.y, *segs[w.source_edge_id]) + (w,) for w in facade), key=lambda t: t[2])
        d_corner = min(math.hypot(p.x - cx, p.y - cy) for cx, cy in corners)
        key = (round(q[2], 6), round(d_corner, 6), -i)
        if best is None or key < best[0]:
            best = (key, p, q)
    _, pano, (qx, qy, dist, wall) = best
    if dist > _EPS:
        qx += ANCHOR_INSET_M * (pano.x - qx) / dist
        qy += ANCHOR_INSET_M * (pano.y - qy) / dist
    room = _room_at(bundle, pano.x, pano.y, room_ids)
    what = "glazing" if glazing.get(wall.id) else "wall"
    return [Anchor(room_id=room.id if room else None, pano_id=pano.id, x=round(qx, 2), y=round(qy, 2),
                   z=round(pano.z, 2), label=f"{compass(az)} {what}")]
