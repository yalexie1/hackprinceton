"""Window rectangles in the model frame and the wall frame of physics 03 section 0.2.

A window is a vertical rectangle on a wall edge: centre on the edge, outward unit normal `e_n`,
tangent `e_t` 90 degrees clockwise from `e_n` seen from above, width, sill `z1` and head `z2`.
A point `(x, y, z)` maps to wall coordinates `(u, d, z)`: `u` along `e_t` from the window centre,
`d` the perpendicular distance from the glass into the room (positive inside).

Sources of windows (section 0.2): a `WallEdge.openings` entry of type `"window"` (measured), or a
window `Surface` with `source_opening_id = None` (vision), placed centred on its wall edge with
sill 0.9 m.

`Opening.relative_center`: which end of the edge it is measured from is [P] Data lane
(physics.md section 8). The default `relative_center_from="first"` measures from the first of
`WallEdge.vertex_ids` (section 0.2); `"second"` gives the other reading, which mirrors every
off-centre window along its wall.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from backend.schema import Floor, Opening, Room, Surface, WallEdge

from . import constants as C

XY = tuple[float, float]
EDGE_ON_POLYGON_TOL_M = 0.05   # design choice: an edge lies on the room outline within this distance
NORMAL_PROBE_M = 0.05          # design choice: step off an edge midpoint to tell inside from outside


# ---------------------------------------------------------------- azimuth (section 0.2)

def azimuth_in_model(nx: float, ny: float) -> float:
    """Azimuth of a horizontal model-frame vector, clockwise from model +y, in [0, 360)."""
    return math.degrees(math.atan2(nx, ny)) % 360.0


def azimuth_true(nx: float, ny: float, north_offset_deg: float) -> float:
    """Section 0.2 / ROOF-02: azimuth_true = azimuth_in_model + north_offset_deg (mod 360)."""
    return (azimuth_in_model(nx, ny) + north_offset_deg) % 360.0


def wrap180(a):
    """Angle difference wrapped into [-180, 180)."""
    return (a + 180.0) % 360.0 - 180.0


# ---------------------------------------------------------------- opening placement

def opening_centre(a: XY, b: XY, relative_center: float, from_vertex: str = "first") -> XY:
    """Centre of an opening on edge a -> b (T-GEO-2). `relative_center` is a fraction in [0, 1].

    from_vertex="first": a + rc (b - a) (section 0.2 working reading); "second": b + rc (a - b).
    """
    rc = float(relative_center)
    if not 0.0 <= rc <= 1.0 or math.isnan(rc):
        raise ValueError(f"relative_center must be a fraction in [0, 1], got {relative_center}")
    if from_vertex == "first":
        p, q = a, b
    elif from_vertex == "second":
        p, q = b, a
    else:
        raise ValueError("from_vertex must be 'first' or 'second'")
    return (p[0] + rc * (q[0] - p[0]), p[1] + rc * (q[1] - p[1]))


# ---------------------------------------------------------------- window rectangle

@dataclass(frozen=True)
class WindowRect:
    """One glazed aperture. Lengths in m, model frame."""
    id: str
    centre: XY
    normal: XY                     # outward unit normal e_n
    width_m: float
    z1: float                      # sill above the floor
    z2: float                      # head above the floor
    edge_id: Optional[str] = None
    edge_length_m: Optional[float] = None
    source: str = "measured"       # "measured" or "vision"
    surface_id: Optional[str] = None
    tau: Optional[tuple[float, float, float]] = None   # Surface.visible_transmittance, if given
    u_value: float = C.DEFAULT_WINDOW_U
    shgc: float = C.DEFAULT_WINDOW_SHGC
    azimuth_deg: float = 0.0       # true azimuth of e_n (A_w)

    @property
    def tangent(self) -> XY:
        """e_t: 90 degrees clockwise from e_n seen from above."""
        return (self.normal[1], -self.normal[0])

    @property
    def u1(self) -> float:
        return -self.width_m / 2.0

    @property
    def u2(self) -> float:
        return self.width_m / 2.0

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return (self.u1, self.u2, self.z1, self.z2)

    @property
    def height_m(self) -> float:
        return self.z2 - self.z1

    @property
    def area_m2(self) -> float:
        return self.width_m * self.height_m

    def to_wall(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        """Model-frame point to wall-frame (u, d, z)."""
        dx, dy = x - self.centre[0], y - self.centre[1]
        t = self.tangent
        u = dx * t[0] + dy * t[1]
        d = -(dx * self.normal[0] + dy * self.normal[1])
        return (u, d, z)

    def vector_to_wall(self, vx: float, vy: float) -> tuple[float, float]:
        """Horizontal model-frame vector to (component along e_t, component along e_n)."""
        t = self.tangent
        return (vx * t[0] + vy * t[1], vx * self.normal[0] + vy * self.normal[1])

    def horizontal_distance(self, x: float, y: float) -> float:
        """Distance in plan from (x, y) to the window's horizontal segment."""
        u, d, _ = self.to_wall(x, y, 0.0)
        du = max(0.0, abs(u) - self.width_m / 2.0)
        return math.hypot(du, d)


# ---------------------------------------------------------------- polygon helpers

def point_in_polygon(x: float, y: float, poly: Sequence[XY]) -> bool:
    """Even-odd ray cast. Points on the boundary may go either way."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xc = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < xc:
                inside = not inside
        j = i
    return inside


def polygon_area_perimeter(poly: Sequence[XY]) -> tuple[float, float]:
    a = 0.0
    p = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
        p += math.hypot(x1 - x0, y1 - y0)
    return abs(a) / 2.0, p


def _dist_point_segment(p: XY, a: XY, b: XY) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def _on_polygon(p: XY, poly: Sequence[XY]) -> bool:
    n = len(poly)
    return any(_dist_point_segment(p, poly[i], poly[(i + 1) % n]) <= EDGE_ON_POLYGON_TOL_M
               for i in range(n))


def outward_normal(a: XY, b: XY, room: Room, fallback_centre: Optional[XY] = None) -> XY:
    """Unit normal of edge a -> b pointing away from the room (polygon test, else centroid)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L == 0:
        raise ValueError("zero-length edge")
    n = (dy / L, -dx / L)          # right-hand side of a -> b
    m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    if len(room.polygon) >= 3:
        ahead = point_in_polygon(m[0] + NORMAL_PROBE_M * n[0], m[1] + NORMAL_PROBE_M * n[1],
                                 room.polygon)
        behind = point_in_polygon(m[0] - NORMAL_PROBE_M * n[0], m[1] - NORMAL_PROBE_M * n[1],
                                  room.polygon)
        if ahead and not behind:
            return (-n[0], -n[1])
        if behind and not ahead:
            return n
    if fallback_centre is not None:
        if (fallback_centre[0] - m[0]) * n[0] + (fallback_centre[1] - m[1]) * n[1] > 0:
            return (-n[0], -n[1])
    return n


# ---------------------------------------------------------------- room geometry

@dataclass
class RoomGeometry:
    floor_area_m2: float
    perimeter_m: float
    height_m: float
    warnings: list[str] = field(default_factory=list)


def room_geometry(room: Room) -> RoomGeometry:
    warnings: list[str] = []
    h = room.height_m
    if not h:
        h = C.DEFAULT_CEILING_HEIGHT_M
        warnings.append(f"room {room.id}: no ceiling height in the scan; {h} m assumed")
    if len(room.polygon) >= 3:
        area, perim = polygon_area_perimeter(room.polygon)
    elif room.width_m and room.depth_m:
        area, perim = room.width_m * room.depth_m, 2.0 * (room.width_m + room.depth_m)
        warnings.append(f"room {room.id}: no polygon; width x depth rectangle used")
    else:
        raise ValueError(f"room {room.id} has neither a polygon nor width and depth")
    if room.area_m2:
        area = float(room.area_m2)
    return RoomGeometry(area, perim, float(h), warnings)


def room_edges(room: Room, floor: Floor) -> list[tuple[WallEdge, XY, XY]]:
    """Edges bounding the room with their end points. `Room.boundary_edge_ids` is authoritative;
    without it, edges whose ends and midpoint lie on `Room.polygon`."""
    xy = {v.id: (v.x, v.y) for v in floor.vertices}
    out = []
    ids = set(room.boundary_edge_ids)
    for e in floor.edges:
        a_id, b_id = e.vertex_ids
        if a_id not in xy or b_id not in xy:
            continue
        a, b = xy[a_id], xy[b_id]
        if ids:
            if e.id in ids:
                out.append((e, a, b))
        elif len(room.polygon) >= 3:
            mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            if all(_on_polygon(p, room.polygon) for p in (a, b, mid)):
                out.append((e, a, b))
    return out


def _centroid(points: Iterable[XY]) -> Optional[XY]:
    pts = list(points)
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _ranged3(r) -> Optional[tuple[float, float, float]]:
    return None if r is None else (float(r.low), float(r.expected), float(r.high))


def infer_north_offset(windows_and_surfaces: list[tuple[XY, Surface]]) -> Optional[float]:
    """north_offset_deg = Surface.azimuth_deg - azimuth_in_model(normal), from the first window
    surface that carries an azimuth. A9 builds Surface.azimuth_deg with the same convention."""
    for n, s in windows_and_surfaces:
        if s.azimuth_deg is not None:
            return (float(s.azimuth_deg) - azimuth_in_model(*n)) % 360.0
    return None


def room_windows(room: Room, floor: Floor, surfaces: Sequence[Surface], *,
                 north_offset_deg: Optional[float] = None,
                 relative_center_from: str = "first") -> tuple[list[WindowRect], Optional[str],
                                                               float, list[str]]:
    """Windows of `room` as rectangles. Returns (windows, window_source, north_offset_deg, warnings).

    Measured windows come from the room's wall edges (`Opening.type == "window"`); their glazing
    properties from the window `Surface` with the same `source_opening_id`, when there is one.
    Vision windows are window surfaces without `source_opening_id` on one of the room's edges,
    centred on the edge, sill 0.9 m, height 1.5 m (widened to the edge, then heightened up to the
    ceiling, when the area needs it). `window_source` is "measured" if any measured window was
    used, "vision" if only vision windows, None if the room has no window.
    """
    warnings: list[str] = []
    geo = room_geometry(room)
    edges = room_edges(room, floor)
    edge_by_id = {e.id: (e, a, b) for e, a, b in edges}
    xy_all = [p for _, a, b in edges for p in (a, b)]
    centre = _centroid(room.polygon) if room.polygon else _centroid(xy_all)
    win_surfaces = [s for s in surfaces if s.kind == "window"]
    by_opening = {s.source_opening_id: s for s in win_surfaces if s.source_opening_id}

    pending: list[dict] = []        # rectangles before the azimuth is known
    for e, a, b in edges:
        L = math.dist(a, b)
        if L == 0:
            continue
        for o in e.openings:
            if o.type != "window":
                continue
            if not o.width_m or not o.height_m:
                warnings.append(f"opening {o.id}: no width or height; left out")
                continue
            rc = o.relative_center
            if rc is None:
                rc = 0.5
                warnings.append(f"opening {o.id}: no relative_center; centred on the edge")
            sill = o.lower_elevation_m
            if sill is None:
                sill = C.VISION_SILL_M
                warnings.append(f"opening {o.id}: no sill height; {sill} m assumed")
            width = float(o.width_m)
            if width > L + 0.02:
                warnings.append(f"opening {o.id}: wider than edge {e.id}; clipped to the edge")
                width = L
            s = by_opening.get(o.id)
            pending.append(dict(
                id=o.id, centre=opening_centre(a, b, rc, relative_center_from),
                normal=outward_normal(a, b, room, centre), width_m=width, z1=float(sill),
                z2=float(sill) + float(o.height_m), edge_id=e.id, edge_length_m=L,
                source="measured", surface=s))

    for s in win_surfaces:
        if s.source_opening_id or s.source_edge_id not in edge_by_id:
            continue
        e, a, b = edge_by_id[s.source_edge_id]
        L = math.dist(a, b)
        if L == 0 or s.area_m2 <= 0:
            continue
        sill = C.VISION_SILL_M
        h_max = max(0.1, geo.height_m - sill)
        h = min(C.VISION_WINDOW_HEIGHT_M, h_max)
        w = s.area_m2 / h
        if w > L:
            w = L
            h = s.area_m2 / L
            if h > h_max:
                warnings.append(f"window {s.id}: {s.area_m2:.1f} m2 does not fit edge {e.id} "
                                f"above a {sill} m sill; clipped to {L * h_max:.1f} m2")
                h = h_max
        pending.append(dict(
            id=s.id, centre=((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0),
            normal=outward_normal(a, b, room, centre), width_m=w, z1=sill, z2=sill + h,
            edge_id=e.id, edge_length_m=L, source="vision", surface=s))

    if north_offset_deg is None:
        north_offset_deg = infer_north_offset([(p["normal"], p["surface"]) for p in pending
                                               if p["surface"] is not None])
        if north_offset_deg is None:
            north_offset_deg = 0.0
            if pending:
                warnings.append("north offset unknown (no window surface azimuth); 0 assumed")

    zone_u = [s.u_value.expected for s in win_surfaces]
    zone_g = [s.shgc.expected for s in win_surfaces if s.shgc is not None]
    u_default = sum(zone_u) / len(zone_u) if zone_u else C.DEFAULT_WINDOW_U
    g_default = sum(zone_g) / len(zone_g) if zone_g else C.DEFAULT_WINDOW_SHGC

    windows = []
    for p in pending:
        s: Optional[Surface] = p.pop("surface")
        n = p["normal"]
        windows.append(WindowRect(
            **p, surface_id=s.id if s else None,
            tau=_ranged3(s.visible_transmittance) if s else None,
            u_value=float(s.u_value.expected) if s else u_default,
            shgc=float(s.shgc.expected) if (s and s.shgc) else g_default,
            azimuth_deg=azimuth_true(n[0], n[1], north_offset_deg)))
        if s is None:
            warnings.append(f"opening {p['id']}: no window surface; zone glazing properties used")

    sources = {w.source for w in windows}
    window_source = "measured" if "measured" in sources else ("vision" if sources else None)
    return windows, window_source, float(north_offset_deg), geo.warnings + warnings
