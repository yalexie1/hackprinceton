"""Parametric roof planes from the Vexcel footprint and roof shape class.

SPEC 6.3 step 2 (sources 2 and 3), step 3 (precomputed obstructions and existing
solar) and step 4 (tilt and azimuth); physics 01 ROOF-03 to ROOF-06.

Pure: no network, no file access, same output for the same input.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Union

import shapely
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from backend.schema import (Assumption, EvidenceRef, Ranged, RoofPlane, VexcelData,
                            VexcelStructure)

from .pitch import SMALL_FOOTPRINT_M2, is_known_shape, normalise_shape, roof_pitch_range
from .setbacks import BuildingGroup, Setbacks, fire_setbacks
from .usable import obstruction_allowance_m2, setback_area_m2, usable_area_parametric

# --- constants destined for backend/config.py (kept local until A0 wires them) ---
EARTH_RADIUS_M = 6371008.8          # mean radius, local equirectangular projection
FLAT_RACK_AZIMUTH_DEG = 180.0       # ROOF-05: a flat plane carries the rack azimuth
WKT_DECIMALS = 7

SHAPE_KEY = "roof-characteristics.shape.value"
MATERIAL_KEY = "roof-characteristics.material.class"
BUILDING_TYPE_KEY = "building-type.class"
SOLAR_KEY = "roof-objects.solar.value"
SOLAR_COUNT_KEY = "roof-objects.solar-panel-photovoltaic.count"
SOLAR_AREA_KEY = "roof-objects.solar-panel-photovoltaic.area"
ROOF_OBJECT_PREFIX = "roof-objects."
COUNT_SUFFIX = ".count"

NorthOffset = Union[Ranged, float, None]


@dataclass
class ParametricRoof:
    """Result of the parametric path.

    ``existing_solar`` is True when Vexcel's precomputed solar attribute says the
    roof already carries PV, so ``PV_ROOF`` can be skipped as already done; None
    means the attribute was absent.
    """
    planes: list[RoofPlane]
    existing_solar: Optional[bool] = None
    existing_solar_area_m2: Optional[float] = None
    shape_class: Optional[str] = None
    building_group: Optional[BuildingGroup] = None
    setbacks: Optional[Setbacks] = None
    assumptions: list[Assumption] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Frame:
    """Local metric frame around a footprint (x east, y north, metres)."""
    lon0: float
    lat0: float

    def to_m(self, geom: BaseGeometry) -> BaseGeometry:
        kx = math.radians(1) * EARTH_RADIUS_M * math.cos(math.radians(self.lat0))
        ky = math.radians(1) * EARTH_RADIUS_M
        return shapely.transform(geom, lambda xy: (xy - (self.lon0, self.lat0)) * (kx, ky))

    def to_lonlat(self, geom: BaseGeometry) -> BaseGeometry:
        kx = math.radians(1) * EARTH_RADIUS_M * math.cos(math.radians(self.lat0))
        ky = math.radians(1) * EARTH_RADIUS_M
        return shapely.transform(geom, lambda xy: xy / (kx, ky) + (self.lon0, self.lat0))


@dataclass(frozen=True)
class _Rect:
    """Minimum rotated rectangle: centre, long side L, short side W, bearing a_L in [0, 180)."""
    cx: float
    cy: float
    length: float
    width: float
    bearing_deg: float

    def to_world(self, u: float, v: float) -> tuple[float, float]:
        """(u along the long axis, v along bearing + 90) to local metres."""
        a = math.radians(self.bearing_deg)
        eu = (math.sin(a), math.cos(a))
        ev = (math.sin(a + math.pi / 2), math.cos(a + math.pi / 2))
        return (self.cx + u * eu[0] + v * ev[0], self.cy + u * eu[1] + v * ev[1])

    def polygon(self, uv: list[tuple[float, float]]) -> Polygon:
        return Polygon([self.to_world(u, v) for u, v in uv])


def _min_rect(poly_m: BaseGeometry) -> _Rect:
    rect = poly_m.minimum_rotated_rectangle
    if rect.geom_type != "Polygon" or rect.area <= 0:
        raise ValueError("degenerate footprint")
    pts = list(rect.exterior.coords)[:4]
    sides = [(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(2)]
    lens = [math.hypot(dx, dy) for dx, dy in sides]
    i_long = 0 if lens[0] >= lens[1] else 1
    dx, dy = sides[i_long]
    bearing = math.degrees(math.atan2(dx, dy)) % 180.0
    c = rect.centroid
    return _Rect(c.x, c.y, max(lens), min(lens), bearing)


def _compass(az: float) -> str:
    names = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
    return names[int(((az % 360) + 22.5) // 45) % 8]


def _primary(vexcel: VexcelData) -> Optional[VexcelStructure]:
    if not vexcel.structures:
        return None
    for s in vexcel.structures:
        if s.primary:
            return s
    return max(vexcel.structures, key=lambda s: s.footprint_area_m2 or 0.0)


def obstruction_counts(attributes: dict) -> dict[str, int]:
    """Vexcel ``roof-objects.<type>.count`` keys as {type: count}; solar is not an obstruction here."""
    out: dict[str, int] = {}
    for key, val in attributes.items():
        if not (key.startswith(ROOF_OBJECT_PREFIX) and key.endswith(COUNT_SUFFIX)):
            continue
        kind = key[len(ROOF_OBJECT_PREFIX):-len(COUNT_SUFFIX)]
        if kind.startswith("solar") or isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        out[kind] = max(0, int(round(val)))
    return out


def existing_solar(attributes: dict) -> tuple[Optional[bool], Optional[float]]:
    """Existing PV from the precomputed solar attribute (SPEC 6.3 step 3)."""
    flag = attributes.get(SOLAR_KEY)
    count = attributes.get(SOLAR_COUNT_KEY)
    area = attributes.get(SOLAR_AREA_KEY)
    area = float(area) if isinstance(area, (int, float)) and not isinstance(area, bool) else None
    if isinstance(flag, str):
        flag = {"true": True, "false": False}.get(flag.strip().lower())
    has = flag if isinstance(flag, bool) else None
    if isinstance(count, (int, float)) and not isinstance(count, bool) and count > 0:
        has = True
    if area is not None and area > 0:
        has = True
    return has, area


def _infer_group(attributes: dict, footprint_m2: Optional[float]) -> BuildingGroup:
    btype = normalise_shape(attributes.get(BUILDING_TYPE_KEY))
    if btype == "residential":
        return "R-3"
    if btype == "commercial":
        return "commercial"
    return "R-3" if (footprint_m2 or 0.0) < SMALL_FOOTPRINT_M2 else "commercial"


def _wkt(geom: BaseGeometry) -> str:
    return shapely_wkt.dumps(geom, rounding_precision=WKT_DECIMALS)


def build_parametric_roof(vexcel: VexcelData, north_offset_deg: NorthOffset = None, *,
                          roof_plan_area_m2: Optional[float] = None,
                          building_group: Optional[BuildingGroup] = None,
                          state: Optional[str] = None) -> ParametricRoof:
    """Roof planes for the primary structure, the P0 path of SPEC 6.3.

    - shape class flat, gable or hip with a footprint polygon: ``vexcel_parametric``;
    - anything else (no shape class, an unknown class, no polygon): ``assumed``,
      one plane over the footprint with the widest tilt range.

    ``north_offset_deg`` is accepted as the workplan input but not applied: the
    Vexcel footprint is already in map coordinates, so ROOF-05 azimuths are true
    bearings. ``roof_plan_area_m2`` is the tower override of ROOF-03 (gross
    building area over storeys); the footprint area stays the upper bound.
    Vexcel's calculated roof height is never read.
    """
    del north_offset_deg  # map-coordinate footprint: azimuths are already true (ROOF-05)
    notes: list[str] = []
    s = _primary(vexcel)
    if s is None:
        return ParametricRoof(planes=[], notes=["no Vexcel structure: no roof planes"])
    attrs = dict(s.attributes)
    shape = normalise_shape(attrs.get(SHAPE_KEY))
    material = attrs.get(MATERIAL_KEY)
    counts = obstruction_counts(attrs)
    solar, solar_area = existing_solar(attrs)

    poly_m = None
    frame = None
    if s.footprint_wkt:
        try:
            geom = shapely_wkt.loads(s.footprint_wkt)
            c = geom.centroid
            frame = _Frame(c.x, c.y)
            poly_m = frame.to_m(geom)
            if poly_m.is_empty or poly_m.area <= 0:
                poly_m = None
        except Exception:  # malformed WKT: fall back to the area alone
            poly_m = None
            notes.append("footprint WKT unreadable; plane built from the footprint area")

    fp_area = s.footprint_area_m2
    if fp_area is None and isinstance(attrs.get("footprint.area"), (int, float)):
        fp_area = float(attrs["footprint.area"])
    if fp_area is None and poly_m is not None:
        fp_area = poly_m.area
    if not fp_area or fp_area <= 0:
        return ParametricRoof(planes=[], existing_solar=solar, existing_solar_area_m2=solar_area,
                              shape_class=shape, notes=notes + ["no footprint: no roof planes"])

    plan_area = fp_area
    if roof_plan_area_m2 is not None and 0 < roof_plan_area_m2 < fp_area:
        plan_area = roof_plan_area_m2
        notes.append("roof plan area from the tower floor plate, footprint used as upper bound (ROOF-03)")

    parametric = poly_m is not None and is_known_shape(shape)
    source = "vexcel_parametric" if parametric else "assumed"
    tilt = roof_pitch_range(shape if parametric else None, fp_area, material)
    beta = math.radians(tilt.expected)
    cosb = math.cos(beta)

    if poly_m is not None:
        rect = _min_rect(poly_m)
    else:
        side = math.sqrt(fp_area)
        rect = _Rect(0.0, 0.0, side, side, 90.0)
    k = plan_area / (rect.length * rect.width)
    # Rectangle sides scaled to the plan area, used for eave and slope lengths
    scale = math.sqrt(plan_area / fp_area)
    L, W = rect.length * scale, rect.width * scale
    hl, hw = rect.length / 2, rect.width / 2
    a_l = rect.bearing_deg

    group = building_group or _infer_group(attrs, fp_area)
    sb = fire_setbacks(state, group, tilt.expected, building_axes_m=(L, W))

    # (id stem, azimuth, plan area, eave length, slope length, plan polygon in u, v)
    specs: list[tuple[str, float, float, float, float, Optional[list]]] = []
    if parametric and shape == "gable":
        s_len = (W / 2) / cosb
        specs += [
            ("", (a_l + 90) % 360, k * rect.length * rect.width / 2, L, s_len,
             [(-hl, 0), (hl, 0), (hl, hw), (-hl, hw)]),
            ("", (a_l + 270) % 360, k * rect.length * rect.width / 2, L, s_len,
             [(-hl, 0), (hl, 0), (hl, -hw), (-hl, -hw)]),
        ]
    elif parametric and shape == "hip":
        s_len = (W / 2) / cosb
        trap = k * (rect.length * rect.width / 2 - rect.width ** 2 / 4)
        tri = k * rect.width ** 2 / 4
        r = hl - hw
        specs += [
            ("", (a_l + 90) % 360, trap, L, s_len, [(-hl, hw), (hl, hw), (r, 0), (-r, 0)]),
            ("", (a_l + 270) % 360, trap, L, s_len, [(-hl, -hw), (hl, -hw), (r, 0), (-r, 0)]),
            ("", a_l % 360, tri, W, s_len, [(hl, hw), (hl, -hw), (r, 0)]),
            ("", (a_l + 180) % 360, tri, W, s_len, [(-hl, hw), (-hl, -hw), (-r, 0)]),
        ]
    elif parametric and shape == "flat":
        specs.append(("roof", FLAT_RACK_AZIMUTH_DEG, plan_area, L, W / cosb, None))
    else:
        # assumed: one plane over the footprint; of the two faces across the long
        # axis, the one closer to south (the primary PV hypothesis)
        cands = [(a_l + 90) % 360, (a_l + 270) % 360]
        az = min(cands, key=lambda g: abs(((g - 180) + 180) % 360 - 180)) if poly_m is not None \
            else FLAT_RACK_AZIMUTH_DEG
        specs.append(("", az, plan_area, L, W / cosb, None))
        reason = "no footprint polygon" if poly_m is None else f"roof shape class {shape!r} not flat, gable or hip"
        notes.append(f"assumed roof geometry: {reason}; widest tilt range (ROOF-03)")

    total_plan = sum(p[2] for p in specs)
    planes: list[RoofPlane] = []
    used_ids: set[str] = set()
    for stem, az, a_plan, le, s_len, uv in specs:
        stem = stem or _compass(az)
        pid = f"plane_{stem}"
        n = 2
        while pid in used_ids:
            pid = f"plane_{stem}_{n}"
            n += 1
        used_ids.add(pid)
        if poly_m is None:
            poly_wkt = "POLYGON EMPTY"
        elif uv is None:
            poly_wkt = _wkt(frame.to_lonlat(poly_m))
        else:
            clip = poly_m.intersection(rect.polygon(uv))
            poly_wkt = _wkt(frame.to_lonlat(clip)) if not clip.is_empty else "POLYGON EMPTY"
        area = a_plan / cosb
        usable = usable_area_parametric(area, le, s_len, sb, counts, a_plan / total_plan)
        planes.append(RoofPlane(
            id=pid, polygon_wkt=poly_wkt, area_m2=round(area, 2), tilt_deg=tilt,
            azimuth_deg=round(az, 1), usable_area_m2=round(min(usable, area), 2),
            obstruction_counts=dict(counts), ridge_confirmed=False,
            eave_length_m=round(le, 3), slope_length_m=round(s_len, 3),
            geometry_source=source,
        ))

    assumptions = _assumptions(planes, tilt, source, shape, counts, sb, group, specs)
    return ParametricRoof(planes=planes, existing_solar=solar, existing_solar_area_m2=solar_area,
                          shape_class=shape, building_group=group, setbacks=sb,
                          assumptions=assumptions, notes=notes)


def _assumptions(planes, tilt, source, shape, counts, sb, group, specs) -> list[Assumption]:
    """Unverified inputs, each carried as an assumption with its range (physics 01 section 8)."""
    vex = EvidenceRef(kind="vexcel_attr", ref=SHAPE_KEY, note=f"shape class {shape!r}")
    out = [Assumption(
        key="roof.tilt_deg",
        label="Roof pitch by roof shape class (ROOF-03); one lidar study, gable and hip share a range [U]",
        value=tilt, source="published_default",
        confidence=0.5 if source == "vexcel_parametric" else 0.2,
        evidence=[vex, EvidenceRef(kind="default_table", ref="ROOF-03")],
    )]
    if len(planes) > 1:
        out.append(Assumption(
            key="roof.ridge_direction",
            label="Ridge along the long side of the footprint (ROOF-05), unconfirmed [U]; "
                  "the alternative turns every plane by 90 degrees",
            value="long_side", source="published_default", confidence=0.5,
            evidence=[EvidenceRef(kind="default_table", ref="ROOF-05")],
        ))
    if counts:
        allow = obstruction_allowance_m2(counts)
        out.append(Assumption(
            key="roof.obstruction_allowance_m2",
            label="Area allowance per counted roof object, engineering judgment (ROOF-04) [U]",
            value=allow, source="published_default", confidence=0.3,
            evidence=[EvidenceRef(kind="vexcel_attr", ref=f"{ROOF_OBJECT_PREFIX}{k}{COUNT_SUFFIX}",
                                  note=str(v)) for k, v in sorted(counts.items())]
                     + [EvidenceRef(kind="default_table", ref="ROOF-04")],
        ))
    out.append(Assumption(
        key="roof.fire_setbacks",
        label=f"Fire-code setbacks for {group}: {sb.basis}; status {sb.status} (ROOF-06); "
              "the authority having jurisdiction decides",
        value=(f"ridge {sb.ridge_setback_m:.4f} m, pathway {sb.pathway_width_m:.4f} m, "
               f"perimeter {sb.perimeter_m:.4f} m"),
        source="published_default", confidence=0.6 if sb.status == "V-repro" else 0.4,
        evidence=[EvidenceRef(kind="default_table", ref="ROOF-06")],
    ))
    # Usable roof area over the whole roof: the obstruction allowance at its high
    # and low ends; how it is split between planes does not change the total.
    if planes:
        allow = obstruction_allowance_m2(counts)
        rect_total = sum(setback_area_m2(p.area_m2, sp[3], sp[4], sb) for p, sp in zip(planes, specs))
        exp = sum(p.usable_area_m2 for p in planes)
        low = min(exp, max(0.0, rect_total - allow.high))
        high = max(exp, max(0.0, rect_total - allow.low))
        out.append(Assumption(
            key="roof.usable_area_m2",
            label="Usable roof area after setbacks and obstruction allowances (ROOF-04, area method)",
            value=Ranged(low=round(low, 2), expected=round(exp, 2), high=round(high, 2), unit="m2"),
            source="published_default", confidence=0.4,
            evidence=[EvidenceRef(kind="default_table", ref="ROOF-04")],
        ))
    return out
