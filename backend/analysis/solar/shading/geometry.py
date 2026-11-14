"""Scene geometry for SHD ray casting: local ENU frame, roof planes in 3D, extruded prisms.

Frame: east-north-up metres about an origin (lon0, lat0) on a local equirectangular
projection (the same projection A11 and A14 use for map polygons; error far below a
centimetre over a building). Map polygons are WGS84 lon/lat, so azimuths measured in
this frame are true azimuths (ROOF-05). z = 0 is the ground.

A roof plane's map polygon is its horizontal projection. It is lifted onto the plane
z(p) = z_low + tan(beta) * (p . u - min over vertices of v . u), u the horizontal
up-slope unit vector (opposite the azimuth the plane faces), so the lowest edge (the
eave) sits at ``z_low``.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np
import shapely
import shapely.affinity
from shapely import wkt as shapely_wkt
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

# --- constants destined for backend/config.py (kept local, workplan 2.6) ---
EARTH_RADIUS_M = 6371008.8          # mean Earth radius; local equirectangular projection (as A11, A14)

Origin = tuple[float, float]        # (lon0, lat0) in degrees


def lonlat_to_enu(lon, lat, origin: Origin) -> np.ndarray:
    """Equirectangular east and north (m) of lon/lat about ``origin``; shape (..., 2)."""
    lon0, lat0 = origin
    k = math.pi / 180.0 * EARTH_RADIUS_M
    x = (np.asarray(lon, float) - lon0) * k * math.cos(math.radians(lat0))
    y = (np.asarray(lat, float) - lat0) * k
    return np.stack([x, y], axis=-1)


def geometry_to_enu(geom: BaseGeometry, origin: Origin) -> BaseGeometry:
    """Map geometry (lon/lat) to the ENU plane (x east, y north, metres)."""
    return shapely.transform(geom, lambda c: lonlat_to_enu(c[:, 0], c[:, 1], origin))


def load_polygon(polygon_wkt: Optional[str]) -> Optional[BaseGeometry]:
    """Parse WKT; None for missing, empty or non-areal geometry."""
    if not polygon_wkt:
        return None
    g = shapely_wkt.loads(polygon_wkt)
    if g.is_empty or g.area <= 0.0:
        return None
    return g


def _polygons(geom: BaseGeometry) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def sun_vectors(zenith_deg, azimuth_deg) -> np.ndarray:
    """SOL-06. s = (sin z sin A, sin z cos A, cos z) in ENU; shape (n, 3)."""
    z = np.radians(np.asarray(zenith_deg, float))
    a = np.radians(np.asarray(azimuth_deg, float))
    return np.stack([np.sin(z) * np.sin(a), np.sin(z) * np.cos(a), np.cos(z)], axis=-1)


def plane_normal(tilt_deg: float, azimuth_deg: float) -> np.ndarray:
    """ROOF-01 inverted: unit normal of a plane with tilt beta facing azimuth gamma."""
    b, g = math.radians(tilt_deg), math.radians(azimuth_deg)
    return np.array([math.sin(b) * math.sin(g), math.sin(b) * math.cos(g), math.cos(b)])


class PlaneSurface:
    """A roof plane lifted into ENU: z as a function of (x, y)."""

    def __init__(self, footprint_enu: BaseGeometry, tilt_deg: float, azimuth_deg: float,
                 z_low_m: float):
        self.footprint = footprint_enu
        self.tilt_deg = float(tilt_deg)
        self.azimuth_deg = float(azimuth_deg)
        self.z_low = float(z_low_m)
        g = math.radians(azimuth_deg)
        self._u = np.array([-math.sin(g), -math.cos(g)])   # horizontal up-slope direction
        self._slope = math.tan(math.radians(tilt_deg))
        xy = np.vstack([np.asarray(p.exterior.coords) for p in _polygons(footprint_enu)])
        self._s0 = float((xy[:, :2] @ self._u).min())
        self.normal = plane_normal(tilt_deg, azimuth_deg)

    def z(self, xy) -> np.ndarray:
        xy = np.asarray(xy, float)
        return self.z_low + self._slope * (xy @ self._u - self._s0)

    def lift(self, xy) -> np.ndarray:
        xy = np.asarray(xy, float)
        return np.concatenate([xy, self.z(xy)[..., None]], axis=-1)

    def triangles(self) -> np.ndarray:
        """Constrained triangulation of the footprint, lifted onto the plane; (T, 3, 3)."""
        return np.asarray([self.lift(t) for t in _triangulate_xy(self.footprint)]).reshape(-1, 3, 3)


def _triangulate_xy(geom: BaseGeometry) -> list[np.ndarray]:
    out = []
    for poly in _polygons(geom):
        for tri in shapely.constrained_delaunay_triangles(poly).geoms:
            out.append(np.asarray(tri.exterior.coords)[:3, :2])
    return out


def extrude_polygon_enu(polygon_enu: BaseGeometry, base_z_m: float, height_m: float) -> np.ndarray:
    """SHD-04. Opaque prism from ``base_z_m`` to ``base_z_m + height_m``; triangles (T, 3, 3)."""
    if height_m <= 0.0:
        return np.zeros((0, 3, 3))
    z0, z1 = float(base_z_m), float(base_z_m) + float(height_m)
    tris: list[np.ndarray] = []
    for poly in _polygons(polygon_enu):
        rings = [poly.exterior, *poly.interiors]
        for ring in rings:
            c = np.asarray(ring.coords)[:, :2]
            for a, b in zip(c[:-1], c[1:]):
                a0, b0 = np.r_[a, z0], np.r_[b, z0]
                a1, b1 = np.r_[a, z1], np.r_[b, z1]
                tris.append(np.array([a0, b0, b1]))
                tris.append(np.array([a0, b1, a1]))
        for t in _triangulate_xy(poly):
            tris.append(np.c_[t, np.full(3, z1)])     # roof cap
            tris.append(np.c_[t, np.full(3, z0)])     # floor cap
    return np.asarray(tris).reshape(-1, 3, 3)


def extrude_mask(polygon_wkt: str, base_z_m: float, height_m: float, *, origin: Origin) -> np.ndarray:
    """SHD-04 tool function. Map polygon (lon/lat WKT) extruded into an ENU prism.

    ``origin`` (lon0, lat0) is the scene's ENU origin; it is an addition to the printed
    signature because a map polygon has no metric frame of its own.
    """
    g = load_polygon(polygon_wkt)
    if g is None:
        return np.zeros((0, 3, 3))
    return extrude_polygon_enu(geometry_to_enu(g, origin), base_z_m, height_m)


def sample_grid(footprint_enu: BaseGeometry, n: int = 3) -> np.ndarray:
    """SHD-01 sample points: centres of an n by n grid of equal cells of the module.

    The module's horizontal outline is taken as its minimum rotated rectangle; on a
    plane the vertical lift is affine, so equal horizontal cells are equal on the plane.
    Points outside a non-rectangular outline are dropped (the centroid is used if none
    remains). Returns (K, 2) in ENU metres.
    """
    rect = footprint_enu.minimum_rotated_rectangle
    c = np.asarray(rect.exterior.coords)[:4, :2]
    e1, e2 = c[1] - c[0], c[3] - c[0]
    f = (np.arange(n) + 0.5) / n
    pts = np.array([c[0] + i * e1 + j * e2 for i in f for j in f])
    inside = shapely.contains_xy(footprint_enu, pts[:, 0], pts[:, 1])
    if not inside.all() and footprint_enu.area < 0.999 * rect.area:
        pts = pts[inside]
    if len(pts) == 0:
        cen = footprint_enu.representative_point()
        pts = np.array([[cen.x, cen.y]])
    return pts


def scale_about_centroid(geom: BaseGeometry, area_m2: float) -> BaseGeometry:
    """Shrink ``geom`` about its centroid so its area becomes ``area_m2`` (never grows it)."""
    if area_m2 is None or area_m2 <= 0.0 or geom.area <= area_m2:
        return geom
    k = math.sqrt(area_m2 / geom.area)
    c = geom.centroid
    return shapely.affinity.scale(geom, xfact=k, yfact=k, origin=c)


def merge_triangles(parts: Sequence[np.ndarray]) -> np.ndarray:
    parts = [np.asarray(p, float).reshape(-1, 3, 3) for p in parts if p is not None and len(p)]
    return np.concatenate(parts, axis=0) if parts else np.zeros((0, 3, 3))
