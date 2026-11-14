"""True north for the building model (SPEC 6.3 step 2, SPEC 16; physics 01 ROOF-02).

Order of sources:

1. ``MatterportData.georeference``: psi from the rotation quaternion (ROOF-02), cross-checked
   against the orientation of the Vexcel footprint. ``north_source = "georeference"``.
2. Footprint registration: the dominant edge direction of the floor outline turned onto the
   dominant edge direction of the Vexcel footprint. Used when the georeference is absent or
   disagrees with the footprint. ``north_source = "footprint_registration"``, wider range.
3. Neither: model +y is taken as north with the full circle as the range. ``"assumed"``.

Convention (physics.md section 3): ``north_offset_deg`` is the azimuth of the model +y axis,
clockwise from true north, so ``azimuth_true = azimuth_in_model + north_offset_deg``.

Open item, physics.md section 8 / ROOF-02 "Pending": which way the Matterport quaternion
rotates (model -> ENU, or the inverse) is not confirmed by the Data lane. This module does not
assume it silently: the footprint cross-check tests both readings on every model, the
assumption's evidence says which one the footprint supports, and a georeference that cannot
be cross-checked carries a wider range.

Registration uses orientation only. ``GeoReference.translation`` is not populated on the
golden models, so the outline cannot be placed on the footprint; the footprint therefore fixes
the angle modulo 90 degrees and the georeference (or, without one, the long axes) picks the
quadrant.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

from backend.schema import (Assumption, EvidenceRef, GeoReference, MatterportData, Quaternion,
                            Ranged, VexcelData)

NorthSource = Literal["georeference", "footprint_registration", "assumed"]

# Constants destined for backend/config.py (SPEC 12); kept local until the lane owner moves them.
NORTH_AGREEMENT_TOL_DEG = 5.0       # georeference and footprint agree when within this (mod 90)
NORTH_MIN_HALF_WIDTH_DEG = 1.0      # floor on +/- for a cross-checked georeference (examples README)
NORTH_UNCHECKED_HALF_WIDTH_DEG = 5.0  # georeference with no footprint to check it against
NORTH_FOOTPRINT_HALF_WIDTH_DEG = 10.0  # floor on +/- for footprint registration
NORTH_LONG_AXIS_MIN_ASPECT = 1.2    # below this a rectangle's long axis does not pick a quadrant
EARTH_RADIUS_M = 6371008.8          # mean Earth radius, for the local metric frame

_EPS = 1e-12


@dataclass(frozen=True)
class NorthResult:
    offset: Ranged                      # BuildingModel.north_offset_deg
    source: NorthSource                 # BuildingModel.north_source
    assumption: Assumption              # key "geometry.north_offset_deg"
    georeference_deg: Optional[float] = None     # psi from the quaternion, ROOF-02 reading
    footprint_deg: Optional[float] = None        # the registration candidate that was compared
    delta_deg: Optional[float] = None            # |georeference - footprint|, when both exist
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- angles

def wrap180(a: float) -> float:
    """Angle in (-180, 180]."""
    r = (a + 180.0) % 360.0 - 180.0
    return 180.0 if r == -180.0 else r


def _mod360(a: float) -> float:
    r = a % 360.0
    return 0.0 if abs(r - 360.0) < 1e-9 else r


def bearing_deg(x0: float, y0: float, x1: float, y1: float) -> float:
    """Direction of a segment, degrees clockwise from the frame's +y axis, in [0, 360)."""
    return _mod360(math.degrees(math.atan2(x1 - x0, y1 - y0)))


def axis_mod90(segments: Iterable[tuple[float, float]]) -> Optional[tuple[float, float]]:
    """Length-weighted dominant direction of (bearing_deg, length) segments, modulo 90.

    Returns (axis in [0, 90), resultant in [0, 1]) or None when there is nothing to measure.
    The resultant is 1 for a perfectly rectilinear set and falls as directions scatter.
    """
    s = c = total = 0.0
    for b, length in segments:
        if length <= 0:
            continue
        t = math.radians(4.0 * b)
        s += length * math.sin(t)
        c += length * math.cos(t)
        total += length
    if total <= 0 or math.hypot(s, c) <= _EPS * total:
        return None
    axis = (math.degrees(math.atan2(s, c)) / 4.0) % 90.0
    return axis, min(1.0, math.hypot(s, c) / total)


def _spread_deg(resultant: float) -> float:
    """Circular standard deviation of the mod-90 axis, degrees."""
    r = max(min(resultant, 1.0), 1e-9)
    return math.degrees(math.sqrt(max(0.0, -2.0 * math.log(r)))) / 4.0


# ---------------------------------------------------------------- quaternion (ROOF-02)

def rotation_matrix(q: Quaternion) -> Optional[list[list[float]]]:
    """ROOF-02 matrix of the normalised quaternion, or None for a zero quaternion."""
    n = math.sqrt(q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z)
    if n < 1e-9:
        return None
    w, x, y, z = q.w / n, q.x / n, q.y / n, q.z / n
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]]


def quaternion_north_offset(q: Quaternion) -> Optional[float]:
    """psi = atan2(R[0][1], R[1][1]) mod 360 (ROOF-02), reading q as model -> ENU."""
    r = rotation_matrix(q)
    if r is None:
        return None
    return _mod360(math.degrees(math.atan2(r[0][1], r[1][1])))


def inverse_north_offset(q: Quaternion) -> Optional[float]:
    """psi under the other reading (q as ENU -> model): the same formula on the conjugate."""
    return quaternion_north_offset(Quaternion(x=-q.x, y=-q.y, z=-q.z, w=q.w))


# ---------------------------------------------------------------- footprint and outline

def _parse_polygon_wkt(wkt: str) -> Optional[list[tuple[float, float]]]:
    try:
        from shapely import wkt as shapely_wkt
        geom = shapely_wkt.loads(wkt)
    except Exception:
        return None
    if geom.is_empty:
        return None
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    if geom.geom_type != "Polygon":
        return None
    return [(float(x), float(y)) for x, y in geom.exterior.coords]


def footprint_wkt(vexcel: Optional[VexcelData]) -> Optional[str]:
    """The primary structure's footprint, else the first structure that has one."""
    if vexcel is None:
        return None
    structures = sorted(vexcel.structures, key=lambda s: not s.primary)
    for s in structures:
        if s.footprint_wkt:
            return s.footprint_wkt
    return None


def footprint_local_xy(wkt: str) -> Optional[list[tuple[float, float]]]:
    """Footprint ring (WKT is longitude first, data spec 4.1) in metres east and north."""
    ring = _parse_polygon_wkt(wkt)
    if not ring or len(ring) < 4:
        return None
    lon0 = sum(p[0] for p in ring[:-1]) / (len(ring) - 1)
    lat0 = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
    k = math.radians(1.0) * EARTH_RADIUS_M
    cl = math.cos(math.radians(lat0))
    return [((lon - lon0) * k * cl, (lat - lat0) * k) for lon, lat in ring]


def _ring_segments(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = []
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        out.append((bearing_deg(x0, y0, x1, y1), math.hypot(x1 - x0, y1 - y0)))
    return out


def outline_segments(matterport: MatterportData) -> list[tuple[float, float]]:
    """(bearing in the model frame, length) of every wall edge (invisible edges excluded)."""
    out = []
    for fl in matterport.floors:
        xy = {v.id: (v.x, v.y) for v in fl.vertices}
        for e in fl.edges:
            if e.type == "invisible" or e.vertex_ids[0] not in xy or e.vertex_ids[1] not in xy:
                continue
            (x0, y0), (x1, y1) = xy[e.vertex_ids[0]], xy[e.vertex_ids[1]]
            out.append((bearing_deg(x0, y0, x1, y1), math.hypot(x1 - x0, y1 - y0)))
    return out


def _long_axis(points: list[tuple[float, float]]) -> Optional[tuple[float, float]]:
    """(bearing of the long side mod 180, aspect ratio) of the minimum rotated rectangle."""
    from shapely.geometry import MultiPoint
    if len(points) < 3:
        return None
    rect = MultiPoint(points).minimum_rotated_rectangle
    if rect.geom_type != "Polygon":
        return None
    c = list(rect.exterior.coords)
    sides = [(bearing_deg(*c[i], *c[i + 1]) % 180.0, math.dist(c[i], c[i + 1])) for i in (0, 1)]
    (b_long, l_long), (_, l_short) = sorted(sides, key=lambda s: -s[1])
    if l_short <= 0:
        return None
    return b_long, l_long / l_short


def _model_points(matterport: MatterportData) -> list[tuple[float, float]]:
    return [(v.x, v.y) for fl in matterport.floors for v in fl.vertices]


# ---------------------------------------------------------------- resolution

def _ranged(expected: float, half_width: float) -> Ranged:
    return Ranged(low=round(expected - half_width, 6), expected=round(expected, 6),
                  high=round(expected + half_width, 6), unit="deg")


def _nearest_candidate(base: float, target: float) -> float:
    """The member of {base + 90 k} nearest to target, in [0, 360)."""
    k = round(wrap180(target - base) / 90.0)
    return _mod360(base + 90.0 * k)


def resolve_north(matterport: MatterportData, vexcel: Optional[VexcelData]) -> NorthResult:
    """North offset, its range and its source for one model (SPEC 6.3 step 2, ROOF-02)."""
    warnings: list[str] = []
    geo: Optional[GeoReference] = matterport.georeference
    psi_geo = psi_inv = None
    if geo is not None:
        psi_geo = quaternion_north_offset(geo.rotation)
        psi_inv = inverse_north_offset(geo.rotation)
        if psi_geo is None:
            warnings.append("georeference rotation is a zero quaternion; treated as absent")

    # footprint registration: psi = footprint axis - model axis (mod 90)
    fp_axis = model_axis = None
    fp_ring = None
    wkt = footprint_wkt(vexcel)
    if wkt:
        fp_ring = footprint_local_xy(wkt)
        if fp_ring is None:
            warnings.append("Vexcel footprint WKT could not be read; no footprint registration")
        else:
            fp_axis = axis_mod90(_ring_segments(fp_ring))
    model_axis = axis_mod90(outline_segments(matterport))
    reg_base = None
    reg_spread = 0.0
    if fp_axis is not None and model_axis is not None:
        reg_base = (fp_axis[0] - model_axis[0]) % 90.0
        reg_spread = math.hypot(_spread_deg(fp_axis[1]), _spread_deg(model_axis[1]))

    geo_ev = EvidenceRef(kind="matterport_field", ref="geocoordinates.rotation",
                         note=f"source {geo.source!r}" if geo is not None else None)
    fp_ev = EvidenceRef(kind="vexcel_attr", ref="footprint.wkt",
                        note="orientation of the primary structure's footprint")

    # 1. georeference, cross-checked
    if psi_geo is not None:
        if reg_base is None:
            hw = NORTH_UNCHECKED_HALF_WIDTH_DEG
            note = (f"physics 01 ROOF-02, psi {psi_geo:.2f}. No footprint to cross-check it, so "
                    f"the quaternion's sense is unconfirmed on this model (the inverse reading "
                    f"gives {psi_inv:.2f}); range widened to +/-{hw:g} degrees")
            warnings.append("north offset from the georeference without a footprint cross-check")
            return NorthResult(
                offset=_ranged(psi_geo, hw), source="georeference",
                assumption=_assumption(psi_geo, hw, "measured", 0.7, [geo_ev], note),
                georeference_deg=psi_geo, warnings=warnings)
        cand = _nearest_candidate(reg_base, psi_geo)
        delta = abs(wrap180(psi_geo - cand))
        cand_inv = _nearest_candidate(reg_base, psi_inv)
        delta_inv = abs(wrap180(psi_inv - cand_inv))
        if delta <= NORTH_AGREEMENT_TOL_DEG:
            hw = max(delta, NORTH_MIN_HALF_WIDTH_DEG)
            if delta_inv <= NORTH_AGREEMENT_TOL_DEG and abs(wrap180(psi_geo - psi_inv)) > 2 * hw:
                sense = (f"the footprint cannot tell the quaternion's sense here: the inverse "
                         f"reading {psi_inv:.2f} fits it as well")
                warnings.append("quaternion sense not decidable from the footprint on this model")
                conf = 0.7
            else:
                sense = (f"the footprint supports the ROOF-02 reading (model -> ENU); the "
                         f"inverse reading {psi_inv:.2f} is off by {delta_inv:.1f} degrees")
                conf = 0.9
            note = (f"physics 01 ROOF-02, psi {psi_geo:.2f}; Vexcel footprint registration gives "
                    f"{cand:.2f} (Delta {delta:.2f} degrees); {sense}")
            return NorthResult(
                offset=_ranged(psi_geo, hw), source="georeference",
                assumption=_assumption(psi_geo, hw, "measured", conf, [geo_ev, fp_ev], note),
                georeference_deg=psi_geo, footprint_deg=cand, delta_deg=delta, warnings=warnings)
        # disagreement: register to the footprint, quadrant from the closer reading
        if delta_inv < delta:
            expected = cand_inv
            why = (f"the inverse quaternion reading {psi_inv:.2f} matches the footprint "
                   f"(off by {delta_inv:.1f}); the ROOF-02 reading {psi_geo:.2f} is off by "
                   f"{delta:.1f}, so the quaternion may rotate ENU -> model on this model")
        else:
            expected = cand
            why = (f"georeference psi {psi_geo:.2f} is {delta:.1f} degrees from the footprint, "
                   f"beyond the {NORTH_AGREEMENT_TOL_DEG:g} degree tolerance; the georeference "
                   f"only picks the quadrant")
        hw = max(NORTH_FOOTPRINT_HALF_WIDTH_DEG, delta if delta_inv >= delta else delta_inv,
                 2.0 * reg_spread)
        warnings.append("georeference disagrees with the Vexcel footprint; registered to the "
                        "footprint with a wider range")
        return NorthResult(
            offset=_ranged(expected, hw), source="footprint_registration",
            assumption=_assumption(expected, hw, "vexcel", 0.5, [fp_ev, geo_ev],
                                   f"SPEC 16 fallback: {why}"),
            georeference_deg=psi_geo, footprint_deg=expected, delta_deg=delta, warnings=warnings)

    # 2. footprint registration alone
    if reg_base is not None:
        expected = reg_base
        quadrant = "the quadrant is not determined (a 90-degree ambiguity remains)"
        fp_long = _long_axis([p for p in fp_ring[:-1]]) if fp_ring else None
        m_long = _long_axis(_model_points(matterport))
        if (fp_long and m_long and fp_long[1] >= NORTH_LONG_AXIS_MIN_ASPECT
                and m_long[1] >= NORTH_LONG_AXIS_MIN_ASPECT):
            # long sides aligned: psi = fp_long - m_long (mod 180); keep the 90-step candidate
            want = (fp_long[0] - m_long[0]) % 180.0
            expected = min((_mod360(reg_base + 90.0 * k) for k in range(4)),
                           key=lambda c: (abs(wrap180(2 * (c - want)) / 2), c))
            quadrant = ("the quadrant comes from aligning the long sides of the outline and the "
                        "footprint, which leaves a 180-degree ambiguity")
        hw = max(NORTH_FOOTPRINT_HALF_WIDTH_DEG, 2.0 * reg_spread)
        warnings.append(f"no georeference: north registered to the Vexcel footprint; {quadrant}")
        return NorthResult(
            offset=_ranged(expected, hw), source="footprint_registration",
            assumption=_assumption(expected, hw, "vexcel", 0.3, [fp_ev],
                                   f"SPEC 16 fallback, no georeference; {quadrant}"),
            footprint_deg=expected, warnings=warnings)

    # 3. assumed
    warnings.append("no georeference and no footprint: north assumed along model +y, full range")
    return NorthResult(
        offset=Ranged(low=-180.0, expected=0.0, high=180.0, unit="deg"), source="assumed",
        assumption=_assumption(0.0, 180.0, "published_default", 0.0, [],
                               "no georeference and no Vexcel footprint; model +y taken as north "
                               "with the whole circle as the range"),
        warnings=warnings)


def _assumption(expected: float, hw: float, source, confidence: float,
                evidence: list[EvidenceRef], note: str) -> Assumption:
    ev = list(evidence) or [EvidenceRef(kind="default_table", ref="ROOF-02", note=note)]
    if evidence:
        ev[0] = ev[0].model_copy(update={"note": note if ev[0].note is None
                                         else f"{ev[0].note}; {note}"})
    return Assumption(key="geometry.north_offset_deg",
                      label="Azimuth of model +y, clockwise from true north",
                      value=_ranged(expected, hw), source=source, confidence=confidence,
                      evidence=ev, user_editable=source != "measured")
