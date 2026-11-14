"""A9: rooms and wall graph -> zones and surfaces, with true north (workplan 4.2, SPEC 6.3 step 2).

Rules, in the order they apply:

- One ``Zone`` per Matterport floor holding all of its rooms (floor area = sum of the rooms'
  measured areas; volume = sum of area x room height).
- A wall edge bounded by two rooms of the same zone is interior and gets no surface. An edge
  bounded by one room is part of the envelope: ``exterior``, or ``adjacent_conditioned`` for a
  demising wall of a unit or suite inside a larger building (thinner than the unit's exterior
  walls; see ``classify_envelope``). Invisible edges get no surface.
- Each ``window`` opening on an envelope edge becomes one window surface (area = width x
  height), each ``doorway`` one door surface; ``opening`` and ``divider`` are not envelope
  elements (physics 02 section 0). The wall surface carries the net area.
- Vision windows (``Assumption`` with ``source="vision"``) are used only where the model has
  no window openings (SPEC 5.1): ``window.area_m2`` spread over the exterior walls of a model
  with none, in proportion to wall area; ``window.<room_id>.area_m2`` on the exterior wall of a
  room with none that an evidence ``ref`` names by edge id, else on its longest exterior wall.
  With neither measured nor vision windows, the DEF-03 window-to-wall ratio applies.
- A floor with rooms but no usable wall graph (no edges, or no room owns an edge; live office
  scans) takes its walls from the Vexcel footprint perimeter scaled by the scanned share of the
  plate, or, with no footprint either, from a square of the scanned area (physics 02 DEF-12,
  SPEC 5.1). Such a model is never left without exterior walls silently.
- A roof surface on the top storey, a ground floor with its exposed perimeter on storey 1.
  A suite (``part_of_larger_building``) scanned on one floor with a generic label ("Floor 1",
  "1" or none), in a building of more than one storey (CoStar) that the scan covers less than
  ``MID_BUILDING_MAX_SHARE`` of the footprint of, is on an unknown storey and is modelled
  mid-building: no ground floor and no roof (physics 02 DEF-13).
- ``north_offset_deg`` and ``north_source`` from ``north.resolve_north``.

Envelope properties (U-values, SHGC, ...) are not this package's job: they arrive as
``Assumption`` values from the registry (A10) through the door. Missing keys fall back to wide
placeholders, and the result says so in ``warnings``.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

from backend.schema import (Assumption, EvidenceRef, Floor, MatterportData, Ranged, Room,
                            Surface, VexcelData, WallEdge, Zone)

from .north import NorthSource, footprint_local_xy, footprint_wkt, resolve_north
from .walls import (azimuth_in_model, edge_length, edge_owners, edge_points, opening_fits,
                    outward_normal, room_area, vertex_xy)

# Constants destined for backend/config.py (SPEC 12); kept local until the lane owner moves them.
DEFAULT_CEILING_HEIGHT_M = 2.7       # only when no room on the model has a height
DEMISING_THICKNESS_GAP_M = 0.04      # thinner than the unit's exterior walls by this -> demising
MAX_WINDOW_TO_WALL = 0.9             # cap on vision or default glazing per wall
MEASURED_WINDOW_REL = 0.05           # physics 02 DEF-03: measured openings +/- 5 %
DEFAULT_EMITTANCE = 0.9              # physics 02 ENV-05 default
# physics 02 DEF-03 window-to-wall ratios (low, expected, high), NOT sourced (section 10, tier A)
DEFAULT_WWR = {"home": (0.15, 0.18, 0.25), "office": (0.20, 0.30, 0.40)}
# physics 02 DEF-13: below this scanned share of the footprint, a generically labelled suite
# floor in a multi-storey building is taken as mid-building. Not sourced (section 10, tier A).
MID_BUILDING_MAX_SHARE = 0.95
_GENERIC_FLOOR_LABEL = re.compile(r"^\s*(?:(?:floor|level|storey|story)\s*)?0*1?\s*$", re.IGNORECASE)

# Placeholders when the registry has not passed a value. Wide on purpose; replaced through the
# door by the registry's assumptions (physics 02 DEF tables). Keys follow physics 02 section 12.
PLACEHOLDER_PROPERTIES: dict[str, tuple[float, float, float, str]] = {
    "wall.u_value": (0.3, 1.0, 2.5, "W/m2K"),
    "partition.u_value": (1.5, 2.0, 2.5, "W/m2K"),
    "window.u_value": (2.0, 4.5, 6.9, "W/m2K"),
    "window.shgc": (0.25, 0.5, 0.8, "-"),
    "glazing.visible_transmittance": (0.4, 0.68, 0.8, "-"),   # physics 03 section 0.4
    "door.u_value": (2.0, 2.8, 3.5, "W/m2K"),
    "roof.u_value": (0.15, 0.5, 1.7, "W/m2K"),
    "floor.u_value": (0.15, 0.6, 1.0, "W/m2K"),
    "wall.absorptance": (0.3, 0.6, 0.8, "-"),
    "roof.absorptance": (0.6, 0.75, 0.92, "-"),
}

# SPEC 5.1, strongest first
SOURCE_STRENGTH = ["user", "measured", "costar", "vexcel", "vision", "published_default",
                   "vintage_default"]

_ROOM_WINDOW_KEY = re.compile(r"^window\.(?P<room>.+)\.area_m2$")

Boundary = Literal["exterior", "ground", "adjacent_conditioned", "adjacent_unconditioned"]


@dataclass(frozen=True)
class GeometryResult:
    zones: list[Zone]
    surfaces: list[Surface]
    north_offset_deg: Ranged
    north_source: NorthSource
    assumptions: list[Assumption]               # written by this package; merge in the registry
    window_source: Optional[Literal["measured", "vision", "default"]] = None
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- inputs

def _pick(assumptions: Iterable[Assumption], key: str,
          source: Optional[str] = None) -> Optional[Assumption]:
    found = [a for a in assumptions if a.key == key and (source is None or a.source == source)]
    if not found:
        return None
    return min(found, key=lambda a: SOURCE_STRENGTH.index(a.source)
               if a.source in SOURCE_STRENGTH else len(SOURCE_STRENGTH))


class _Props:
    """Ranged envelope properties from the assumptions, placeholders otherwise."""

    def __init__(self, assumptions: list[Assumption]):
        self._assumptions = assumptions
        self.placeholders: set[str] = set()

    def get(self, key: str) -> Ranged:
        a = _pick(self._assumptions, key)
        if a is not None and isinstance(a.value, Ranged):
            return a.value
        self.placeholders.add(key)
        lo, ex, hi, unit = PLACEHOLDER_PROPERTIES[key]
        return Ranged(low=lo, expected=ex, high=hi, unit=unit)


def _generic_label(label: Optional[str]) -> bool:
    """True for a floor label that says nothing about the storey: "Floor 1", "1", or none.
    Matterport names the first floor of every model "Floor 1", whatever storey it is on."""
    return bool(_GENERIC_FLOOR_LABEL.match(label or ""))


def _floor_level(floor: Floor, index: int, floor_levels: Optional[dict[str, int]]) -> int:
    if floor_levels and floor.id in floor_levels:
        return int(floor_levels[floor.id])
    m = re.search(r"-?\d+", floor.label or "")
    return int(m.group()) if m else index + 1


# ---------------------------------------------------------------- envelope classification

def classify_envelope(edges: list[tuple[WallEdge, float]],
                      part_of_larger_building: bool) -> dict[str, Boundary]:
    """``exterior`` or ``adjacent_conditioned`` for each envelope edge (one owning room).

    A detached building has only exterior envelope edges. For a unit or suite inside a larger
    building the scan does not say which outline walls face outdoors (no translation to place
    the outline on the footprint), so the thickest outline walls are taken as exterior and walls
    thinner by more than ``DEMISING_THICKNESS_GAP_M`` as demising walls to conditioned
    neighbours. An edge without a thickness is exterior. This is a heuristic; the result
    records it as an assumption so the user can correct it.
    """
    if not part_of_larger_building:
        return {e.id: "exterior" for e, _ in edges}
    known = [e.thickness_m for e, _ in edges if e.thickness_m is not None]
    t_ext = max(known) if known else None
    out: dict[str, Boundary] = {}
    for e, _ in edges:
        thin = (t_ext is not None and e.thickness_m is not None
                and e.thickness_m < t_ext - DEMISING_THICKNESS_GAP_M)
        out[e.id] = "adjacent_conditioned" if thin else "exterior"
    return out


# ---------------------------------------------------------------- builder

@dataclass
class _Wall:
    edge: WallEdge
    floor_id: str
    zone_id: str
    room: Optional[Room]                  # None for a wall built from the footprint (DEF-12)
    length: float
    height: float
    azimuth: float
    boundary: Boundary
    surface_id: str
    children: list[Surface] = field(default_factory=list)
    synthetic: bool = False               # not a Matterport edge: no source_edge_id

    @property
    def gross(self) -> float:
        return self.length * self.height

    @property
    def source_edge_id(self) -> Optional[str]:
        return None if self.synthetic else self.edge.id


def build_geometry(matterport: MatterportData, vexcel: Optional[VexcelData] = None,
                   assumptions: Iterable[Assumption] = (), *, use: str = "living",
                   part_of_larger_building: bool = False,
                   building_stories: Optional[int] = None,
                   floor_levels: Optional[dict[str, int]] = None) -> GeometryResult:
    """Zones, surfaces and true north for one scanned model.

    ``assumptions``: everything known so far (vision observations from A7, registry values from
    A10). Vision window sizes are read from it; envelope properties too.
    ``use``: zone use and the default table row, ``"living"`` for homes or ``"office"``.
    ``part_of_larger_building``: an apartment unit or office suite (demising walls possible).
    ``building_stories``: storeys above grade (``CostarData.stories``); the top storey gets the
    roof. ``floor_levels``: storey number of each Matterport floor id, when the floor label does
    not carry it (for a suite, the scan's "Floor 1" is not the building's first storey).
    """
    assumptions = list(assumptions)
    warnings: list[str] = []
    props = _Props(assumptions)
    north = resolve_north(matterport, vexcel)
    warnings += north.warnings
    psi = north.offset.expected

    edge_ids = [e.id for fl in matterport.floors for e in fl.edges]
    clash = len(edge_ids) != len(set(edge_ids))
    rooms_by_floor: dict[str, list[Room]] = defaultdict(list)
    for r in matterport.rooms:
        rooms_by_floor[r.floor_id].append(r)
    orphan_rooms = [r.id for r in matterport.rooms
                    if r.floor_id not in {f.id for f in matterport.floors}]
    if orphan_rooms:
        warnings.append(f"rooms on no known floor are left out: {orphan_rooms}")

    # room heights, with the mean of the measured rooms where the scan has none
    measured_h = [r.height_m for r in matterport.rooms if r.height_m]
    height: dict[str, float] = {}
    filled: list[str] = []
    for fl in matterport.floors:
        on_floor = [r.height_m for r in rooms_by_floor[fl.id] if r.height_m]
        fallback = (sum(on_floor) / len(on_floor) if on_floor else
                    sum(measured_h) / len(measured_h) if measured_h else DEFAULT_CEILING_HEIGHT_M)
        for r in rooms_by_floor[fl.id]:
            if r.height_m:
                height[r.id] = float(r.height_m)
            else:
                height[r.id] = round(fallback, 2)
                filled.append(r.id)
    if not measured_h and matterport.rooms:
        warnings.append(f"no room height in the scan; {DEFAULT_CEILING_HEIGHT_M} m assumed")

    levels = {fl.id: _floor_level(fl, i, floor_levels) for i, fl in enumerate(matterport.floors)}
    top = building_stories if building_stories else (max(levels.values()) if levels else 1)
    single = len([f for f in matterport.floors if rooms_by_floor[f.id]]) == 1
    use_key = "office" if use == "office" else "home"

    ring_cache: list = []                         # the footprint ring, read at most once

    def footprint() -> Optional[list[tuple[float, float]]]:
        if not ring_cache:
            ring_cache.append(_footprint_ring(vexcel, warnings))
        return ring_cache[0]

    # physics 02 DEF-13: a generically labelled suite floor in a multi-storey building
    mid_floors, storey_assumption = _unknown_storey(
        matterport, rooms_by_floor, footprint, part_of_larger_building=part_of_larger_building,
        single=single, building_stories=building_stories, floor_levels=floor_levels,
        warnings=warnings)

    zones: list[Zone] = []
    walls: list[_Wall] = []
    zone_of_floor: dict[str, str] = {}
    no_graph: list[tuple[Floor, Zone]] = []      # floors for the DEF-12 fallback
    for fl in matterport.floors:
        rooms = rooms_by_floor[fl.id]
        if not rooms:
            continue
        zid = (("zone_suite" if part_of_larger_building else "zone_main") if single
               else f"zone_{fl.id}")
        zone_of_floor[fl.id] = zid
        area = sum(room_area(r) for r in rooms)
        volume = sum(room_area(r) * height[r.id] for r in rooms)
        zones.append(Zone(id=zid, room_ids=[r.id for r in rooms], use=use,
                          floor_area_m2=round(area, 4), volume_m3=round(volume, 4)))

        xy = vertex_xy(fl)
        owners = edge_owners(fl, rooms)
        if not any(owners.values()):               # no edges, or no room owns one (DEF-12)
            no_graph.append((fl, zones[-1]))
            continue
        room_by_id = {r.id: r for r in rooms}
        envelope: list[tuple[WallEdge, Room]] = []
        for e in fl.edges:
            if e.type == "invisible":
                continue
            own = owners.get(e.id, [])
            pts = edge_points(e, xy)
            if pts is None:
                warnings.append(f"edge {e.id}: unknown vertex id")
                continue
            if len(own) == 1:
                envelope.append((e, room_by_id[own[0]]))
            elif not own and e.openings:
                warnings.append(f"edge {e.id} bounds no room; its openings are left out")
        boundary = classify_envelope([(e, edge_length(e, xy)) for e, _ in envelope],
                                     part_of_larger_building)
        for e, room in envelope:
            p0, p1 = edge_points(e, xy)
            centre = _room_centre(room, fl, xy)
            n = outward_normal(p0, p1, room, centre)
            walls.append(_Wall(
                edge=e, floor_id=fl.id, zone_id=zid, room=room, length=edge_length(e, xy),
                height=height[room.id], azimuth=_az(azimuth_in_model(n) + psi),
                boundary=boundary[e.id],
                surface_id=f"surf_wall_{fl.id}_{e.id}" if clash else f"surf_wall_{e.id}"))

    new_assumptions: list[Assumption] = [north.assumption]
    if storey_assumption is not None:
        new_assumptions.append(storey_assumption)
    if no_graph:
        fp_walls, fp_assumption = _footprint_envelope(no_graph, footprint(), psi, single, warnings)
        walls += fp_walls
        new_assumptions.append(fp_assumption)

    # measured openings on envelope edges
    measured_windows = 0
    measured_area = 0.0
    rooms_with_windows: set[str] = set()
    model_has_windows = any(o.type == "window" for fl in matterport.floors for e in fl.edges
                            for o in e.openings)
    for w in walls:
        for i, o in enumerate(w.edge.openings, start=1):
            if o.type not in ("window", "doorway"):
                continue
            if not o.width_m or not o.height_m:
                warnings.append(f"opening {o.id}: no width or height; left out")
                continue
            if not opening_fits(w.length, o):
                warnings.append(f"opening {o.id} does not fit edge {w.edge.id}")
            stem = w.surface_id.replace("surf_wall_", "")
            area = o.width_m * o.height_m
            if o.type == "window":
                measured_windows += 1
                measured_area += area
                rooms_with_windows.add(w.room.id)
                w.children.append(_window(f"surf_win_{stem}_{i}", w, area, props, o.id))
            else:
                w.children.append(Surface(
                    id=f"surf_door_{stem}_{i}", zone_id=w.zone_id, kind="door",
                    boundary=w.boundary, area_m2=area, azimuth_deg=w.azimuth, tilt_deg=90.0,
                    u_value=props.get("door.u_value"), parent_surface_id=w.surface_id,
                    source_edge_id=w.edge.id, source_opening_id=o.id))
    # rooms with a window opening on an interior edge still count as having windows
    for fl in matterport.floors:
        owners = edge_owners(fl, rooms_by_floor[fl.id])
        for e in fl.edges:
            if any(o.type == "window" for o in e.openings):
                rooms_with_windows.update(owners.get(e.id, []))

    window_source: Optional[str] = "measured" if measured_windows else None
    exterior = [w for w in walls if w.boundary == "exterior"]

    # vision windows, only where the model (or the room) has no window openings
    vision_used: list[str] = []
    for a in assumptions:
        if a.source != "vision" or not isinstance(a.value, Ranged):
            continue
        m = _ROOM_WINDOW_KEY.match(a.key)
        if not m or a.key == "window.area_m2":
            continue
        rid = m.group("room")
        if rid in rooms_with_windows:
            warnings.append(f"{a.key}: room {rid} has measured window openings; the vision "
                            f"reading is a cross-check only and builds no surface")
            continue
        candidates = [w for w in exterior if w.room is not None and w.room.id == rid]
        if not candidates:
            warnings.append(f"{a.key}: room {rid} has no exterior wall; no window built")
            continue
        named = {ev.ref for ev in a.evidence}
        on_named = [c for c in candidates if c.edge.id in named]
        w = (on_named or [max(candidates, key=lambda c: (c.gross, c.edge.id))])[0]
        area = min(a.value.expected, MAX_WINDOW_TO_WALL * w.gross - _child_area(w))
        if area < a.value.expected:
            warnings.append(f"{a.key}: capped at {MAX_WINDOW_TO_WALL:.0%} of wall {w.edge.id}")
        if area > 0:
            w.children.append(_window(f"surf_win_{rid}_vision", w, area, props, None))
            vision_used.append(a.key)
    global_vision = _pick(assumptions, "window.area_m2", source="vision")
    if global_vision is not None and isinstance(global_vision.value, Ranged):
        if model_has_windows:
            warnings.append("window.area_m2 from vision: the model has window openings, so the "
                            "vision reading is a cross-check only and builds no surface")
        elif vision_used:
            warnings.append("window.area_m2 from vision ignored: room-level vision windows "
                            "were applied")
        elif exterior:
            _spread(exterior, global_vision.value.expected, props, warnings, "window.area_m2")
            vision_used.append("window.area_m2")
    if vision_used and not window_source:
        window_source = "vision"

    if not model_has_windows and not vision_used and exterior:
        lo, ex, hi = DEFAULT_WWR[use_key]
        gross = sum(w.gross for w in exterior)
        _spread(exterior, ex * gross, props, warnings, "window-to-wall default")
        window_source = "default"
        warnings.append(f"no window openings and no vision reading: DEF-03 window-to-wall "
                        f"ratio {ex} ({lo} to {hi}), not sourced")
        new_assumptions.append(Assumption(
            key="window.area_m2", label="Window area from the default window-to-wall ratio",
            value=Ranged(low=round(lo * gross, 2), expected=round(ex * gross, 2),
                         high=round(hi * gross, 2), unit="m2"),
            source="vintage_default", confidence=0.2,
            evidence=[EvidenceRef(kind="default_table", ref="DEF-03",
                                  note=f"{use_key} window-to-wall ratio {lo} / {ex} / {hi} of "
                                       f"{gross:.1f} m2 exterior wall; not sourced")]))
    elif measured_windows:
        new_assumptions.append(Assumption(
            key="window.area_m2", label="Window area from measured openings",
            value=Ranged(low=round(measured_area * (1 - MEASURED_WINDOW_REL), 4),
                         expected=round(measured_area, 4),
                         high=round(measured_area * (1 + MEASURED_WINDOW_REL), 4), unit="m2"),
            source="measured", confidence=0.9, user_editable=False,
            evidence=[EvidenceRef(kind="matterport_field", ref="floors.edges.openings",
                                  note=f"{measured_windows} openings of type window; plus or "
                                       f"minus {MEASURED_WINDOW_REL:.0%} (physics 02 DEF-03)")]))

    # wall surfaces with their net area, followed by their windows and doors
    surfaces: list[Surface] = []
    for w in walls:
        net = w.gross - _child_area(w)
        if net < 0:
            warnings.append(f"edge {w.edge.id}: openings exceed the wall area; net wall set to 0")
            net = 0.0
        ext = w.boundary == "exterior"
        surfaces.append(Surface(
            id=w.surface_id, zone_id=w.zone_id, kind="wall", boundary=w.boundary,
            area_m2=round(net, 4), azimuth_deg=w.azimuth, tilt_deg=90.0,
            u_value=props.get("wall.u_value" if ext else "partition.u_value"),
            source_edge_id=w.source_edge_id,
            solar_absorptance=props.get("wall.absorptance") if ext else None,
            emittance=DEFAULT_EMITTANCE if ext else None))
        surfaces.extend(w.children)

    # roof on the top storey, ground floor on storey 1; neither on a DEF-13 mid-building floor,
    # whose floor and ceiling face conditioned neighbours (b = 0, ENV-03: no surface is built)
    for fl in matterport.floors:
        zid = zone_of_floor.get(fl.id)
        if zid is None or fl.id in mid_floors:
            continue
        zone = next(z for z in zones if z.id == zid)
        suffix = "" if single else f"_{fl.id}"
        if levels[fl.id] >= top:
            surfaces.append(Surface(
                id=f"surf_roof{suffix}", zone_id=zid, kind="roof", boundary="exterior",
                area_m2=zone.floor_area_m2, azimuth_deg=None, tilt_deg=0.0,
                u_value=props.get("roof.u_value"), solar_absorptance=props.get("roof.absorptance"),
                emittance=DEFAULT_EMITTANCE))
        if levels[fl.id] <= 1:
            perimeter = sum(w.length for w in walls
                            if w.floor_id == fl.id and w.boundary == "exterior")
            surfaces.append(Surface(
                id=f"surf_floor{suffix}", zone_id=zid, kind="floor", boundary="ground",
                area_m2=zone.floor_area_m2, azimuth_deg=None, tilt_deg=180.0,
                u_value=props.get("floor.u_value"), exposed_perimeter_m=round(perimeter, 4)))

    # recorded geometry assumptions
    used_h = [height[r.id] for r in matterport.rooms if r.id in height]
    if used_h:
        note = None
        if filled:
            note = (f"{', '.join(filled)} {'has' if len(filled) == 1 else 'have'} no height in "
                    f"the scan; the mean of the measured rooms is used")
        new_assumptions.append(Assumption(
            key="geometry.ceiling_height_m", label="Ceiling height",
            value=Ranged(low=min(used_h), expected=round(sum(used_h) / len(used_h), 4),
                         high=max(used_h), unit="m"),
            source="measured", confidence=0.95 if measured_h else 0.3, user_editable=False,
            evidence=[EvidenceRef(kind="matterport_field", ref="rooms.dimensions.height",
                                  note=note)]))
    demising = [w.edge.id for w in walls if w.boundary == "adjacent_conditioned"]
    if demising:
        new_assumptions.append(Assumption(
            key="geometry.demising_edges",
            label="Outline walls taken as walls to conditioned neighbours",
            value=" ".join(demising), source="measured", confidence=0.6,
            evidence=[EvidenceRef(kind="matterport_field", ref="floors.edges.thickness",
                                  note="thinner than the unit's exterior walls; the scan does "
                                       "not say which walls face outdoors")]))
    for z in zones:
        if z.conditioned and not any(s.zone_id == z.id and s.kind == "wall"
                                     and s.boundary == "exterior" for s in surfaces):
            warnings.append(f"zone {z.id} has no exterior wall: its baseline leaves out the "
                            f"facade, and window measures cannot apply")
    if props.placeholders:
        warnings.append("placeholder envelope properties (no registry value passed): "
                        + ", ".join(sorted(props.placeholders)))

    return GeometryResult(zones=zones, surfaces=surfaces, north_offset_deg=north.offset,
                          north_source=north.source, assumptions=new_assumptions,
                          window_source=window_source, warnings=warnings)


# ---------------------------------------------------------------- helpers

def _footprint_ring(vexcel: Optional[VexcelData], warnings: list[str]
                    ) -> Optional[list[tuple[float, float]]]:
    """The chosen structure's footprint (the ``primary`` one, as A11 and ``north.py`` read it)
    in metres east and north, counter-clockwise and closed; None when there is none."""
    wkt = footprint_wkt(vexcel)
    if not wkt:
        return None
    ring = footprint_local_xy(wkt)
    if ring is None:
        warnings.append("Vexcel footprint WKT could not be read; no footprint envelope")
        return None
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient
    poly = Polygon(ring)
    if not poly.is_valid or poly.area <= 0:
        warnings.append("Vexcel footprint is not a valid polygon; no footprint envelope")
        return None
    return [(float(x), float(y)) for x, y in orient(poly, sign=1.0).exterior.coords]


def _unknown_storey(matterport: MatterportData, rooms_by_floor: dict[str, list[Room]], footprint,
                    *, part_of_larger_building: bool, single: bool,
                    building_stories: Optional[int], floor_levels: Optional[dict[str, int]],
                    warnings: list[str]) -> tuple[set[str], Optional[Assumption]]:
    """Floors taken as mid-building, and the ``geometry.storey`` assumption (physics 02 DEF-13).

    Applies to a suite scanned on one floor whose label is generic ("Floor 1", "1" or none),
    with no storey passed in ``floor_levels``, in a building of more than one storey (CoStar),
    when the scan covers less than ``MID_BUILDING_MAX_SHARE`` of the Vexcel footprint (the
    DEF-12 share). Such a suite is more likely on a middle storey than on the ground or top one.
    Without a footprint the share is unknown and the label is read as before.
    """
    if not (part_of_larger_building and single and building_stories and building_stories > 1):
        return set(), None
    fl = next(f for f in matterport.floors if rooms_by_floor[f.id])
    if (floor_levels and fl.id in floor_levels) or not _generic_label(fl.label):
        return set(), None
    ring = footprint()
    if ring is None:
        return set(), None
    from shapely.geometry import Polygon
    fp_area = float(Polygon(ring).area)
    scanned = sum(room_area(r) for r in rooms_by_floor[fl.id])
    share = min(1.0, scanned / fp_area)
    if share >= MID_BUILDING_MAX_SHARE:
        return set(), None
    label = f"'{fl.label}'" if fl.label else "no label"
    warnings.append(
        f"floor {fl.id} has {label}, which does not say which storey the suite is on; the "
        f"building has {building_stories} storeys and the scan covers {share:.0%} of its footprint, "
        f"so the suite is assumed to be on a middle storey: no ground floor and no roof, its floor "
        f"and ceiling against conditioned space (physics 02 DEF-13). Set the storey if the suite is "
        f"on the ground or top floor")
    return {fl.id}, Assumption(
        key="geometry.storey", label="Storey of the scanned suite: unknown, assumed mid-building",
        value="unknown_mid_building", source="vintage_default", confidence=0.3,
        evidence=[
            EvidenceRef(kind="matterport_field", ref="floors.label",
                        note=f"floor {fl.id}: {label}, the scan's own floor name, not a storey"),
            EvidenceRef(kind="costar_field", ref="stories", note=f"{building_stories} storeys"),
            EvidenceRef(kind="vexcel_attr", ref="footprint.wkt",
                        note=f"scanned share {share:.3f} ({scanned:.1f} of {fp_area:.1f} m2), below "
                             f"{MID_BUILDING_MAX_SHARE}"),
            EvidenceRef(kind="default_table", ref="DEF-13", note="physics 02 DEF-13, not sourced")])


def _footprint_envelope(no_graph: list[tuple[Floor, Zone]],
                        ring: Optional[list[tuple[float, float]]],
                        psi: float, single: bool, warnings: list[str]
                        ) -> tuple[list[_Wall], Assumption]:
    """Exterior walls of floors without a usable wall graph (physics 02 DEF-12, SPEC 5.1).

    Each edge of the Vexcel footprint becomes one exterior wall of length edge x share, with
    share = min(1, scanned floor area / footprint area): a suite's exterior is taken as
    proportional to its area. Azimuths are the outward normals in the footprint's own
    east-north frame, so they are true azimuths without the north offset. With no footprint, a
    square of the scanned area aligned with the model axes is the last resort (azimuths rotated
    by the north offset). Height is the zone's mean room height (volume / area).
    """
    fp_area = None
    if ring is not None:
        from shapely.geometry import Polygon
        fp_area = float(Polygon(ring).area)
    walls: list[_Wall] = []
    notes: list[str] = []
    for fl, zone in no_graph:
        area = zone.floor_area_m2
        height = zone.volume_m3 / area if area > 0 else DEFAULT_CEILING_HEIGHT_M
        prefix = "footprint" if single else f"{fl.id}_footprint"
        if any(o.type == "window" for e in fl.edges for o in e.openings):
            warnings.append(f"floor {fl.id}: window openings on edges that bound no room are "
                            f"left out")
        if ring is not None:
            share = min(1.0, area / fp_area)
            sides = []
            for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
                length = math.hypot(x1 - x0, y1 - y0)
                if length > 1e-6:      # counter-clockwise ring: outward normal on the right
                    sides.append((length * share, _az(math.degrees(math.atan2(y1 - y0,
                                                                              -(x1 - x0))))))
            warnings.append(
                f"floor {fl.id}: the scan has no wall graph, so walls and windows come from the "
                f"building footprint: the Vexcel footprint perimeter ({fp_area:.0f} m2) scaled "
                f"by the scanned share {share:.2f} ({area:.0f} m2 scanned), assuming the "
                f"suite's exterior is proportional to its area (physics 02 DEF-12)")
            notes.append(f"floor {fl.id}: {len(sides)} footprint edges x share {share:.3f} "
                         f"({area:.1f} of {fp_area:.1f} m2), height {height:.2f} m")
        else:
            side = math.sqrt(area)
            sides = [(side, _az(a + psi)) for a in (0.0, 90.0, 180.0, 270.0)]
            warnings.append(
                f"floor {fl.id}: the scan has no wall graph and there is no Vexcel footprint, so "
                f"the walls are a square of the scanned area ({area:.0f} m2, {side:.1f} m a "
                f"side), every side exterior. Orientation, exterior share and window area are "
                f"all guesses (physics 02 DEF-12); treat the envelope figures as rough")
            notes.append(f"floor {fl.id}: no footprint; square of the scanned {area:.1f} m2, "
                         f"height {height:.2f} m")
        for i, (length, az) in enumerate(sides, start=1):
            eid = f"{prefix}_{i}"
            walls.append(_Wall(
                edge=WallEdge(id=eid, type="wall", vertex_ids=(f"{eid}_a", f"{eid}_b")),
                floor_id=fl.id, zone_id=zone.id, room=None, length=length, height=height,
                azimuth=az, boundary="exterior", surface_id=f"surf_wall_{eid}", synthetic=True))
    if ring is not None:
        value, conf = "vexcel_footprint_perimeter_x_scanned_share", 0.2
        evidence = [EvidenceRef(kind="vexcel_attr", ref="footprint.wkt",
                                note="perimeter and edge azimuths of the chosen structure's "
                                     "footprint; " + "; ".join(notes)),
                    EvidenceRef(kind="matterport_field", ref="rooms.area_m2",
                                note="scanned floor area; the scan has no wall edges or room "
                                     "outlines")]
    else:
        value, conf = "square_of_scanned_area", 0.05
        evidence = [EvidenceRef(kind="matterport_field", ref="rooms.area_m2",
                                note="no wall graph and no Vexcel footprint; " + "; ".join(notes))]
    evidence.append(EvidenceRef(kind="default_table", ref="DEF-12",
                                note="physics 02 DEF-12, not sourced"))
    return walls, Assumption(
        key="geometry.envelope_source",
        label="Exterior walls from the building footprint (the scan has no wall graph)",
        value=value, source="vintage_default", confidence=conf, evidence=evidence)


def _az(a: float) -> float:
    r = round(a % 360.0, 4)
    return 0.0 if r >= 360.0 else r


def _room_centre(room: Room, floor: Floor, xy) -> Optional[tuple[float, float]]:
    if room.polygon:
        return (sum(p[0] for p in room.polygon) / len(room.polygon),
                sum(p[1] for p in room.polygon) / len(room.polygon))
    pts = [xy[v] for e in floor.edges if e.id in room.boundary_edge_ids
           for v in e.vertex_ids if v in xy]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _child_area(w: _Wall) -> float:
    return sum(c.area_m2 for c in w.children)


def _window(sid: str, w: _Wall, area: float, props: _Props,
            opening_id: Optional[str]) -> Surface:
    return Surface(
        id=sid, zone_id=w.zone_id, kind="window", boundary=w.boundary, area_m2=round(area, 4),
        azimuth_deg=w.azimuth, tilt_deg=90.0, u_value=props.get("window.u_value"),
        shgc=props.get("window.shgc"),
        visible_transmittance=props.get("glazing.visible_transmittance"),
        parent_surface_id=w.surface_id, source_edge_id=w.source_edge_id,
        source_opening_id=opening_id)


def _spread(walls: list[_Wall], total: float, props: _Props, warnings: list[str],
            what: str) -> None:
    """One window per exterior wall, area in proportion to the wall's gross area."""
    gross = sum(w.gross for w in walls)
    if gross <= 0 or total <= 0:
        return
    if total > MAX_WINDOW_TO_WALL * gross:
        warnings.append(f"{what}: {total:.1f} m2 capped at {MAX_WINDOW_TO_WALL:.0%} of the "
                        f"exterior wall area")
        total = MAX_WINDOW_TO_WALL * gross
    for w in walls:
        area = total * w.gross / gross
        if area > 0:
            stem = w.surface_id.replace("surf_wall_", "")
            w.children.append(_window(f"surf_win_{stem}_vision" if what == "window.area_m2"
                                      else f"surf_win_{stem}_default", w, area, props, None))
