"""Wall-graph helpers: edge lengths, which rooms own an edge, outward normals, openings.

Everything here is in the model frame, metres. No contract object is changed.
"""
from __future__ import annotations

import math
from typing import Optional

from backend.schema import Floor, Opening, Room, WallEdge

# Constants destined for backend/config.py (SPEC 12); kept local until the lane owner moves them.
EDGE_ON_POLYGON_TOL_M = 0.05   # an edge lies on a room outline when within this distance
NORMAL_PROBE_M = 0.05          # step off an edge's midpoint to tell inside from outside

XY = tuple[float, float]


def vertex_xy(floor: Floor) -> dict[str, XY]:
    return {v.id: (v.x, v.y) for v in floor.vertices}


def edge_points(edge: WallEdge, xy: dict[str, XY]) -> Optional[tuple[XY, XY]]:
    a, b = edge.vertex_ids
    if a not in xy or b not in xy:
        return None
    return xy[a], xy[b]


def edge_length(edge: WallEdge, xy: dict[str, XY]) -> float:
    pts = edge_points(edge, xy)
    return 0.0 if pts is None else math.dist(*pts)


def room_polygon(room: Room):
    """shapely Polygon of Room.polygon, or None when it has fewer than three points."""
    from shapely.geometry import Polygon
    if len(room.polygon) < 3:
        return None
    poly = Polygon(room.polygon)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return None if poly.is_empty else poly


def room_area(room: Room) -> float:
    """Room.area_m2 as measured (Matterport areaFloor); the polygon area only when it is absent."""
    if room.area_m2 is not None:
        return float(room.area_m2)
    poly = room_polygon(room)
    return 0.0 if poly is None else float(poly.area)


def edge_owners(floor: Floor, rooms: list[Room]) -> dict[str, list[str]]:
    """edge id -> ids of the rooms it bounds.

    ``Room.boundary_edge_ids`` is authoritative. A room without it is matched geometrically:
    the edge lies on the room outline.
    """
    owners: dict[str, list[str]] = {e.id: [] for e in floor.edges}
    xy = vertex_xy(floor)
    for room in rooms:
        if room.boundary_edge_ids:
            for eid in room.boundary_edge_ids:
                if eid in owners and room.id not in owners[eid]:
                    owners[eid].append(room.id)
            continue
        poly = room_polygon(room)
        if poly is None:
            continue
        ring = poly.exterior
        for e in floor.edges:
            pts = edge_points(e, xy)
            if pts is None or pts[0] == pts[1]:
                continue
            if max(ring.distance(_pt(p)) for p in (*pts, _mid(*pts))) <= EDGE_ON_POLYGON_TOL_M:
                owners[e.id].append(room.id)
    return owners


def _pt(p: XY):
    from shapely.geometry import Point
    return Point(p)


def _mid(a: XY, b: XY) -> XY:
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def outward_normal(p0: XY, p1: XY, room: Optional[Room], fallback_centre: Optional[XY]) -> XY:
    """Unit normal of the edge p0 -> p1 pointing away from the room.

    The room polygon decides when it exists; otherwise the normal points away from
    ``fallback_centre`` (for example the centroid of the room's edge vertices).
    """
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return (0.0, 0.0)
    n = (dy / length, -dx / length)   # right-hand side of p0 -> p1
    m = _mid(p0, p1)
    poly = room_polygon(room) if room is not None else None
    if poly is not None:
        ahead = _pt((m[0] + NORMAL_PROBE_M * n[0], m[1] + NORMAL_PROBE_M * n[1]))
        behind = _pt((m[0] - NORMAL_PROBE_M * n[0], m[1] - NORMAL_PROBE_M * n[1]))
        if poly.contains(ahead) and not poly.contains(behind):
            return (-n[0], -n[1])
        if poly.contains(behind) and not poly.contains(ahead):
            return n
    if fallback_centre is not None:
        to_c = (fallback_centre[0] - m[0], fallback_centre[1] - m[1])
        if to_c[0] * n[0] + to_c[1] * n[1] > 0:
            return (-n[0], -n[1])
    return n


def azimuth_in_model(normal: XY) -> float:
    """Azimuth of a horizontal normal, clockwise from model +y, in [0, 360)."""
    return math.degrees(math.atan2(normal[0], normal[1])) % 360.0


def opening_center(p0: XY, p1: XY, opening: Opening) -> Optional[tuple[XY, XY]]:
    """Centre of an opening in the model frame under both readings of ``relative_center``.

    Returns (from the first vertex of ``vertex_ids``, from the second vertex). The first is
    the working reading (examples README section 3, item 2); which end Matterport measures from
    is an open item (physics.md section 8), so a consumer that needs the position (daylight,
    glare) should carry the second as the other end of its range. Surfaces built here need only
    width, height and the edge azimuth, which do not depend on it.
    """
    if opening.relative_center is None:
        return None
    t = float(opening.relative_center)
    a = (p0[0] + t * (p1[0] - p0[0]), p0[1] + t * (p1[1] - p0[1]))
    b = (p1[0] + t * (p0[0] - p1[0]), p1[1] + t * (p0[1] - p1[1]))
    return a, b


def opening_fits(length: float, opening: Opening, tol: float = 0.02) -> bool:
    """Width within the edge and, when the centre is known, both ends on the edge.

    Symmetric in the two readings of ``relative_center``, so it holds or fails for both.
    """
    w = opening.width_m or 0.0
    if w > length + tol:
        return False
    if opening.relative_center is None:
        return True
    c = opening.relative_center * length
    return c - w / 2.0 >= -tol and c + w / 2.0 <= length + tol
