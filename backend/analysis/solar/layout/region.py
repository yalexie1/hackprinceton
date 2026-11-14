"""Plane coordinates and the usable region of one roof plane (physics 01 ROOF-04, ROOF-06).

Polygon method where the plane has a map polygon: transform it to plane coordinates
(u along the eave, v up the slope, metres in the roof plane), remove the fire-code
setbacks, then remove located obstructions buffered by their clearance and tree masks.
Area method where it has none: a rectangle eave length by slope length, the same
setbacks, no drawn positions.

The ROOF-06 numbers are copied here (not imported from ``solar/roof``, workplan 2.6).
They are design defaults, not a legal determination; the California residential text
(R329.6) and Houston's local adoption are unverified (physics 01 section 8).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import shapely
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from backend.schema import RoofPlane

# --- constants destined for backend/config.py (kept local until A0 wires them) ---
EARTH_RADIUS_M = 6371008.8                  # local equirectangular projection (as A11)
IN = 0.0254
FT = 12 * IN
PATHWAY_M = 36 * IN                         # ROOF-06, IFC 1205.2.1.1
RIDGE_SETBACK_LOW_SHARE_M = 18 * IN         # ROOF-06, 1205.2.1.2: arrays <= 33 % of plan roof
RIDGE_SETBACK_HIGH_SHARE_M = 36 * IN        # ROOF-06, 1205.2.1.2: arrays > 33 %
RIDGE_SHARE_LIMIT = 0.33                    # ROOF-06, 1205.2.1.2
RIDGE_SHARE_LIMIT_SPRINKLERED = 0.66        # ROOF-06, 1205.2.1.3
SLOPE_EXEMPT_DEG = math.degrees(math.atan(2 / 12))   # ROOF-06, 2 in 12 (9.46 deg): no R-3 setbacks
PERIMETER_SMALL_M = 4 * FT                  # ROOF-06, 1205.3.1: either axis <= 250 ft
PERIMETER_LARGE_M = 6 * FT                  # ROOF-06, 1205.3.1
PERIMETER_AXIS_LIMIT_M = 250 * FT           # 76.2 m
INTERIOR_INTERVAL_M = 150 * FT              # ROOF-06, 1205.3.2: 45.72 m
INTERIOR_PATHWAY_M = 4 * FT                 # ROOF-06, 1205.3.2: 1.2192 m
FLAT_TILT_MAX_DEG = 9.5                     # ROOF-03 / LAY-03: below this a plane is flat
# Clearance around a located obstruction (ROOF-04 allowance table, [U] judgment).
# Labels as SAM 3 / Vexcel name them; a tree mask is removed with no clearance.
OBSTRUCTION_CLEARANCE_M = {
    "roof vent": 0.3, "roof-vent": 0.3, "vent": 0.3,
    "skylight": 0.3,
    "chimney": 0.5,
    "ac unit": 1.0, "ac-unit": 1.0, "hvac": 1.0,
    "tree": 0.0, "tree overhang": 0.0,
}

BuildingGroup = Literal["R-3", "commercial"]


def is_flat(plane: RoofPlane) -> bool:
    return plane.tilt_deg.expected < FLAT_TILT_MAX_DEG


def _load_polygon(w: str) -> Optional[BaseGeometry]:
    try:
        g = shapely_wkt.loads(w)
    except Exception:
        return None
    if g.is_empty or g.area <= 0 or g.geom_type not in ("Polygon", "MultiPolygon"):
        return None
    return g if g.is_valid else g.buffer(0)


@dataclass(frozen=True)
class PlaneFrame:
    """Map (lon, lat) <-> plane coordinates (u along the eave, v up the slope, metres).

    ``cosb`` is cos(tilt); 1 for flat planes, whose v is a plan distance away from the
    rack azimuth. Downslope faces ``azimuth_deg``.
    """
    lon0: float
    lat0: float
    azimuth_deg: float
    cosb: float

    def _k(self) -> tuple[float, float]:
        kx = math.radians(1) * EARTH_RADIUS_M * math.cos(math.radians(self.lat0))
        return kx, math.radians(1) * EARTH_RADIUS_M

    def _axes(self):
        g = math.radians(self.azimuth_deg)
        return (math.cos(g), -math.sin(g)), (math.sin(g), math.cos(g))   # eave e, downslope d

    def to_uv(self, geom: BaseGeometry) -> BaseGeometry:
        kx, ky = self._k()
        (ex, ey), (dx, dy) = self._axes()
        cosb = self.cosb

        def f(xy):
            x = (xy[:, 0] - self.lon0) * kx
            y = (xy[:, 1] - self.lat0) * ky
            u = x * ex + y * ey
            v = -(x * dx + y * dy) / cosb
            return np.column_stack([u, v])
        return shapely.transform(geom, f)

    def plan_m(self, geom_uv: BaseGeometry) -> BaseGeometry:
        """Plane coordinates to local plan metres (x east, y north)."""
        (ex, ey), (dx, dy) = self._axes()
        cosb = self.cosb

        def f(uv):
            u, w = uv[:, 0], uv[:, 1] * cosb
            return np.column_stack([u * ex - w * dx, u * ey - w * dy])
        return shapely.transform(geom_uv, f)

    def m_to_uv(self, geom_m: BaseGeometry) -> BaseGeometry:
        (ex, ey), (dx, dy) = self._axes()
        cosb = self.cosb

        def f(xy):
            x, y = xy[:, 0], xy[:, 1]
            return np.column_stack([x * ex + y * ey, -(x * dx + y * dy) / cosb])
        return shapely.transform(geom_m, f)

    def lonlat_to_m(self, geom: BaseGeometry) -> BaseGeometry:
        kx, ky = self._k()
        return shapely.transform(geom, lambda xy: (xy - (self.lon0, self.lat0)) * (kx, ky))

    def m_to_lonlat(self, geom_m: BaseGeometry) -> BaseGeometry:
        kx, ky = self._k()
        return shapely.transform(geom_m, lambda xy: xy / (kx, ky) + (self.lon0, self.lat0))

    def to_lonlat(self, geom_uv: BaseGeometry) -> BaseGeometry:
        return self.m_to_lonlat(self.plan_m(geom_uv))


@dataclass
class PlaneRegion:
    """Setback region and usable region of one plane in plane coordinates."""
    frame: Optional[PlaneFrame]      # None on the area method (no map polygon)
    setback_uv: BaseGeometry         # after fire-code setbacks only: A_rect of ROOF-04
    usable_uv: BaseGeometry          # minus located obstructions and tree masks
    ridge_setback_m: float
    perimeter_m: float
    pathway_m: float

    @property
    def a_rect_m2(self) -> float:
        return self.setback_uv.area

    def usable_lonlat(self) -> Optional[BaseGeometry]:
        """The usable area in map coordinates (plan view); None on the area method."""
        return None if self.frame is None else self.frame.to_lonlat(self.usable_uv)


def plane_frame(plane: RoofPlane, flat: bool) -> Optional[PlaneFrame]:
    g = _load_polygon(plane.polygon_wkt)
    if g is None:
        return None
    c = g.centroid
    cosb = 1.0 if flat else math.cos(math.radians(plane.tilt_deg.expected))
    return PlaneFrame(c.x, c.y, plane.azimuth_deg % 360.0, cosb)


def base_polygon_uv(plane: RoofPlane, frame: Optional[PlaneFrame], flat: bool) -> BaseGeometry:
    """The whole plane in plane coordinates."""
    if frame is not None:
        return frame.to_uv(_load_polygon(plane.polygon_wkt))
    # area method: eave length by slope length when known, else a square of the plane area
    if plane.eave_length_m and plane.slope_length_m:
        return box(0.0, 0.0, plane.eave_length_m, plane.slope_length_m)
    side = math.sqrt(max(plane.area_m2, 0.0))
    return box(0.0, 0.0, side, side)


def _interior_strips(poly: BaseGeometry, axis: int) -> BaseGeometry:
    """1205.3.2: one 4 ft pathway per 150 ft along an axis, evenly spaced."""
    minx, miny, maxx, maxy = poly.bounds
    lo, hi = (minx, maxx) if axis == 0 else (miny, maxy)
    n = max(0, math.ceil((hi - lo) / INTERIOR_INTERVAL_M) - 1)
    strips = []
    for i in range(1, n + 1):
        c = lo + i * (hi - lo) / (n + 1)
        a, b = c - INTERIOR_PATHWAY_M / 2, c + INTERIOR_PATHWAY_M / 2
        strips.append(box(a, miny - 1, b, maxy + 1) if axis == 0 else box(minx - 1, a, maxx + 1, b))
    return unary_union(strips) if strips else Polygon()


def setback_region(base_uv: BaseGeometry, plane: RoofPlane, group: BuildingGroup,
                   ridge_setback_m: float) -> tuple[BaseGeometry, float, float, float]:
    """Apply ROOF-06 in plane coordinates. Returns (region, ridge, perimeter, pathway).

    R-3 above 2 in 12: ``ridge_setback_m`` strip below the top (ridge) edge and one 36 in
    pathway along the low-u rake edge (ROOF-04 polygon method). R-3 at or below 2 in 12:
    no setbacks. Commercial: the perimeter strip (4 ft where either axis is 250 ft or less,
    else 6 ft) and interior pathways every 150 ft.
    """
    minx, miny, maxx, maxy = base_uv.bounds
    if group == "R-3":
        if plane.tilt_deg.expected <= SLOPE_EXEMPT_DEG:
            return base_uv, 0.0, 0.0, 0.0
        clip = box(minx + PATHWAY_M, miny - 1.0, maxx + 1.0, maxy - ridge_setback_m)
        if clip.is_empty or maxx - minx <= PATHWAY_M or maxy - miny <= ridge_setback_m:
            return Polygon(), ridge_setback_m, 0.0, PATHWAY_M
        return base_uv.intersection(clip), ridge_setback_m, 0.0, PATHWAY_M
    rect = base_uv.minimum_rotated_rectangle
    pts = list(rect.exterior.coords)[:3] if rect.geom_type == "Polygon" else []
    axes = [math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2])] if len(pts) == 3 else [0.0, 0.0]
    perim = PERIMETER_SMALL_M if min(axes) <= PERIMETER_AXIS_LIMIT_M else PERIMETER_LARGE_M
    region = base_uv.buffer(-perim, join_style="mitre")
    path = 0.0
    if not region.is_empty and max(axes) > INTERIOR_INTERVAL_M:
        strips = unary_union([_interior_strips(region, 0), _interior_strips(region, 1)])
        if not strips.is_empty:
            region = region.difference(strips)
            path = INTERIOR_PATHWAY_M
    return region, 0.0, perim, path


def _obstruction_geoms_m(plane: RoofPlane, frame: PlaneFrame) -> list[BaseGeometry]:
    out = []
    for det in plane.obstructions:
        label = det.label.strip().lower()
        if label not in OBSTRUCTION_CLEARANCE_M:
            continue
        g = _load_polygon(det.mask_wkt) if det.mask_wkt else None
        g = g if g is not None else _load_polygon(det.bbox_wkt)
        if g is None:
            continue
        out.append(frame.lonlat_to_m(g).buffer(OBSTRUCTION_CLEARANCE_M[label], join_style="mitre"))
    return out


def plane_region(plane: RoofPlane, group: BuildingGroup, ridge_setback_m: float) -> PlaneRegion:
    flat = is_flat(plane)
    frame = plane_frame(plane, flat)
    base = base_polygon_uv(plane, frame, flat)
    region, ridge, perim, path = setback_region(base, plane, group, ridge_setback_m)
    usable = region
    if frame is not None and not region.is_empty:
        obs = _obstruction_geoms_m(plane, frame)
        if obs:
            usable = region.difference(frame.m_to_uv(unary_union(obs)))
    return PlaneRegion(frame, region, usable, ridge, perim, path)
