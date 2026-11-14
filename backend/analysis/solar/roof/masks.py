"""SAM 3 roof and tree masks refine the parametric roof (Analysis package A12).

SPEC 6.3 step 3; physics 01 ROOF-04 (``A_tree``) and SHD-04 rule 1. What the
Data lane measured on the golden house (D8) shapes every choice here:

- SAM 3 returns roof *fragments*, and they are **nested**, not adjacent (most of
  them sit inside the largest one). Fragment areas are never summed. The roof
  cross-check takes the single largest ``roof`` mask that overlaps the target
  building's footprint; on the golden house that gave 180.9 m2 against the
  190.4 m2 Vexcel footprint.
- The highest-confidence detection can be another structure (the garage), so
  detections are never ranked by confidence.
- A mask fills 43 to 93 % of its own box, so box area is never used as roof area:
  areas come from ``mask_area_m2`` (pixel count x ground pixel area).
- ``mask_wkt`` is usually None. Tree overhang then uses the detection's box,
  scaled by its fill ``mask_area_m2 / box area`` (an assumption: the canopy is
  taken as spread evenly over its box).
- Plane geometry and obstruction counts stay as the parametric path left them;
  fragments can only lower ``usable_area_m2``, never raise it.

Pixel masks are taken as decoded arrays (rows x columns, truthy = inside), never
read from disk here: Pillow is not a dependency of the lane, so whoever reads
``mask_png_path`` decodes it and passes the array in. Pixel row 0 is north;
the ground scale comes from the box polygon and the pixel dimensions, never
from the image's ``min-gsd``/``max-gsd``.

Pure: no network, no file access, same output for the same input.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np
import shapely
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from backend.schema import Assumption, EvidenceRef, Ranged, RoofPlane, VexcelData, VexcelDetection

from .planes import _Frame, _primary, _wkt

# --- constants destined for backend/config.py (kept local until A0 wires them) ---
# Largest roof mask vs footprint: relative disagreement above which a warning is
# raised. D8 saw 5 % on the golden house; 15 % leaves room for eaves and for the
# mask missing a wing. Engineering judgment [U].
ROOF_AREA_TOLERANCE = 0.15
# A roof detection belongs to the target building when at least this share of its
# own geometry lies inside the footprint (keeps the garage out). [U]
MIN_FOOTPRINT_OVERLAP = 0.5
ROOF_LABELS = {"roof"}
TREE_LABELS = {"tree", "trees"}
ORTHO_PREFIX = "ortho"
# Simplification of the vectorised mask, in pixels (removes the staircase only).
SIMPLIFY_PX = 0.5


# --------------------------------------------------------------------------- pixel -> map

def _label(d: VexcelDetection) -> str:
    return " ".join(d.label.strip().lower().replace("_", " ").replace("-", " ").split())


def _geom(text: Optional[str]) -> Optional[BaseGeometry]:
    if not text:
        return None
    try:
        g = shapely_wkt.loads(text)
    except Exception:
        return None
    return None if g.is_empty else g


def _box_corners_m(box_m: BaseGeometry) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(NW, NE, SW) corners of the box polygon in local metres.

    A four-cornered box is used as it stands (a rotated quad stays rotated): the
    corner furthest north-west is pixel (0, 0), its eastern neighbour the end of
    row 0, its other neighbour the start of the last row. Anything else falls
    back to the box polygon's envelope.
    """
    pts = None
    if box_m.geom_type == "Polygon":
        ring = list(box_m.exterior.coords)[:-1]
        dedup = []
        for p in ring:
            if not dedup or math.dist(p, dedup[-1]) > 1e-9:
                dedup.append(p)
        if len(dedup) > 1 and math.dist(dedup[0], dedup[-1]) <= 1e-9:
            dedup.pop()
        if len(dedup) == 4:
            pts = [np.asarray(p, dtype=float) for p in dedup]
    if pts is None:
        x0, y0, x1, y1 = box_m.bounds
        return np.array([x0, y1]), np.array([x1, y1]), np.array([x0, y0])
    i = max(range(4), key=lambda k: pts[k][1] - pts[k][0])
    nw, a, b = pts[i], pts[(i + 1) % 4], pts[(i - 1) % 4]
    ne, sw = (a, b) if (a - nw)[0] - (a - nw)[1] >= (b - nw)[0] - (b - nw)[1] else (b, a)
    return nw, ne, sw


@dataclass(frozen=True)
class MaskPolygon:
    """A pixel mask placed on the map."""
    polygon_wkt: str           # lon/lat, union of the mask's pixels (simplified by half a pixel)
    area_m2: float             # pixel count x ground pixel area (not the polygon's or the box's area)
    pixel_area_m2: float
    pixel_count: int
    fill: float                # mask pixels / box pixels


def mask_to_map(mask: np.ndarray, bbox_wkt: str,
                pixel_bbox: Optional[Sequence[int]] = None) -> MaskPolygon:
    """Turn a mask cropped to its pixel box into a map polygon and a ground area.

    ``mask`` is rows x columns (row 0 north), truthy inside, covering exactly the
    box ``bbox_wkt`` (lon/lat). The grid is the mask's own shape; when
    ``pixel_bbox`` (x, y, w, h) disagrees with it the mask's shape wins, since
    the mask spans the whole box either way.
    """
    m = np.asarray(mask)
    if m.ndim == 3:                       # RGB(A) decoded PNG: any non-zero channel
        m = m.any(axis=2)
    m = m.astype(bool)
    if m.ndim != 2 or m.size == 0:
        raise ValueError("mask must be a non-empty 2-D array")
    del pixel_bbox
    rows, cols = m.shape
    box_ll = _geom(bbox_wkt)
    if box_ll is None:
        raise ValueError("bbox_wkt unreadable")
    c = box_ll.centroid
    frame = _Frame(c.x, c.y)
    nw, ne, sw = _box_corners_m(frame.to_m(box_ll))
    ex, ey = (ne - nw) / cols, (sw - nw) / rows          # one pixel along a row, down a column
    pixel_area = abs(ex[0] * ey[1] - ex[1] * ey[0])
    count = int(m.sum())

    rects = []
    for r in range(rows):
        row = np.concatenate(([0], m[r].view(np.int8), [0]))
        d = np.diff(row)
        for s, e in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
            rects.append(box(float(s), float(r), float(e), float(r + 1)))
    if rects:
        px = shapely.union_all(rects).simplify(SIMPLIFY_PX, preserve_topology=True)
        geo_m = shapely.transform(px, lambda uv: nw + uv[:, :1] * ex + uv[:, 1:2] * ey)
        poly_wkt = _wkt(frame.to_lonlat(geo_m))
    else:
        poly_wkt = "POLYGON EMPTY"
    return MaskPolygon(polygon_wkt=poly_wkt, area_m2=count * pixel_area, pixel_area_m2=pixel_area,
                       pixel_count=count, fill=count / (rows * cols))


def vectorise_detections(detections: Sequence[VexcelDetection],
                         masks: Mapping[str, np.ndarray]) -> list[VexcelDetection]:
    """Copies of the detections with ``mask_wkt`` and ``mask_area_m2`` filled from decoded masks.

    ``masks`` is keyed by ``mask_png_path``. Detections with no array keep their
    fields as they came (``mask_area_m2`` from the Data lane survives).
    """
    out = []
    for d in detections:
        arr = masks.get(d.mask_png_path) if d.mask_png_path else None
        if arr is None:
            out.append(d)
            continue
        mp = mask_to_map(arr, d.bbox_wkt, d.pixel_bbox)
        out.append(d.model_copy(update={"mask_wkt": mp.polygon_wkt,
                                        "mask_area_m2": round(mp.area_m2, 3)}))
    return out


# --------------------------------------------------------------------------- per detection

@dataclass(frozen=True)
class _Det:
    index: int
    det: VexcelDetection
    geom_m: BaseGeometry       # mask polygon if known, otherwise the box
    area_m2: float             # mask area (best available)
    fill: float                # share of geom_m actually covered by the mask
    basis: str                 # "mask_area_m2", "mask_wkt" or "bbox"


def _measure(i: int, d: VexcelDetection, frame: _Frame) -> Optional[_Det]:
    box_ll = _geom(d.bbox_wkt)
    mask_ll = _geom(d.mask_wkt)
    box_m = frame.to_m(box_ll) if box_ll is not None else None
    mask_m = frame.to_m(mask_ll) if mask_ll is not None else None
    if mask_m is not None and mask_m.area > 0:
        area = d.mask_area_m2 if d.mask_area_m2 is not None else mask_m.area
        return _Det(i, d, mask_m, float(area), 1.0,
                    "mask_area_m2" if d.mask_area_m2 is not None else "mask_wkt")
    if box_m is None or box_m.area <= 0:
        return None
    if d.mask_area_m2 is not None:
        fill = max(0.0, min(1.0, d.mask_area_m2 / box_m.area))
        return _Det(i, d, box_m, float(d.mask_area_m2), fill, "mask_area_m2")
    return _Det(i, d, box_m, box_m.area, 1.0, "bbox")


def _pick_images(dets: list[_Det]) -> list[_Det]:
    """Ortho detections when there are any: an oblique box leans with height."""
    ortho = [x for x in dets if x.det.image_id.lower().startswith(ORTHO_PREFIX)]
    return ortho or dets


# --------------------------------------------------------------------------- result

@dataclass
class RoofAreaCheck:
    """Largest roof mask on the target building against the footprint and the planes."""
    mask_area_m2: Optional[float]
    footprint_area_m2: Optional[float]
    plane_plan_area_m2: float
    ratio_to_footprint: Optional[float]
    tolerance: float = ROOF_AREA_TOLERANCE
    agrees: Optional[bool] = None
    detection_index: Optional[int] = None
    basis: Optional[str] = None


@dataclass
class MaskRefinement:
    planes: list[RoofPlane]
    detections: list[VexcelDetection]
    roof_check: RoofAreaCheck
    tree_area_m2: dict[str, float] = field(default_factory=dict)   # in-plane A_tree per plane id
    assumptions: list[Assumption] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _plan_area(p: RoofPlane, poly_m: Optional[BaseGeometry]) -> float:
    if poly_m is not None and poly_m.area > 0:
        return poly_m.area
    return p.area_m2 * math.cos(math.radians(p.tilt_deg.expected))


def refine_with_masks(planes: Sequence[RoofPlane], vexcel: VexcelData,
                      masks: Optional[Mapping[str, np.ndarray]] = None, *,
                      footprint_wkt: Optional[str] = None) -> MaskRefinement:
    """Lower each plane's ``usable_area_m2`` by the tree overhang over it and check roof area.

    ``planes`` are the parametric planes of A11. ``masks`` are decoded pixel masks
    keyed by ``mask_png_path`` (optional). ``footprint_wkt`` defaults to the
    primary structure's footprint. Returns new plane objects; the inputs are not
    mutated. With no detections the planes come back unchanged.
    """
    dets = vectorise_detections(vexcel.detections, masks) if masks else list(vexcel.detections)
    s = _primary(vexcel)
    fp_wkt = footprint_wkt or (s.footprint_wkt if s else None)
    fp_ll = _geom(fp_wkt)
    plane_ll = [_geom(p.polygon_wkt) for p in planes]
    anchor = fp_ll or next((g for g in plane_ll if g is not None), None)
    if anchor is None and dets:
        anchor = _geom(dets[0].bbox_wkt)
    plan_total = 0.0
    if anchor is None:
        plan_total = sum(_plan_area(p, None) for p in planes)
        check = RoofAreaCheck(None, s.footprint_area_m2 if s else None, round(plan_total, 2), None)
        return MaskRefinement(planes=list(planes), detections=dets, roof_check=check,
                              notes=["no footprint and no detections: planes unchanged"])
    c = anchor.centroid
    frame = _Frame(c.x, c.y)
    fp_m = frame.to_m(fp_ll) if fp_ll is not None else None
    plane_m = [frame.to_m(g) if g is not None else None for g in plane_ll]
    plan_total = sum(_plan_area(p, g) for p, g in zip(planes, plane_m))
    fp_area = (s.footprint_area_m2 if s and s.footprint_area_m2 else None) or \
        (fp_m.area if fp_m is not None else None)

    measured = [x for x in (_measure(i, d, frame) for i, d in enumerate(dets)) if x is not None]
    notes: list[str] = []
    warnings: list[str] = []

    # --- roof area cross-check: the single largest roof mask on the building ----------
    target = fp_m
    if target is None:
        valid = [g for g in plane_m if g is not None and g.area > 0]
        target = shapely.union_all(valid) if valid else None
    roofs = _pick_images([x for x in measured if _label(x.det) in ROOF_LABELS])
    on_building = []
    if target is not None:
        for x in roofs:
            g = x.geom_m
            if g.area > 0 and g.intersection(target).area / g.area >= MIN_FOOTPRINT_OVERLAP:
                on_building.append(x)
    best = max(on_building, key=lambda x: (x.basis != "bbox", x.area_m2), default=None)
    check = RoofAreaCheck(None, round(fp_area, 2) if fp_area else None, round(plan_total, 2), None)
    if best is not None:
        check.mask_area_m2 = round(best.area_m2, 2)
        check.detection_index = best.index
        check.basis = best.basis
        ref = fp_area or plan_total
        if ref and ref > 0:
            check.ratio_to_footprint = round(best.area_m2 / ref, 4)
            check.agrees = abs(best.area_m2 / ref - 1.0) <= ROOF_AREA_TOLERANCE
            if not check.agrees:
                warnings.append(
                    f"largest SAM 3 roof mask {best.area_m2:.1f} m2 vs footprint {ref:.1f} m2 "
                    f"({100 * (best.area_m2 / ref - 1):+.0f} %), beyond the "
                    f"{100 * ROOF_AREA_TOLERANCE:.0f} % tolerance: check the footprint and the roof planes")
        if best.basis == "bbox":
            warnings.append("roof mask area unknown (no mask_area_m2 or mask_wkt): box area used, "
                            "which overstates the roof by up to 2x")
        notes.append(f"roof cross-check from detection {best.index} ({best.basis}); "
                     f"{len(on_building)} roof detections on the building, never summed (SAM 3 fragments nest)")
    elif roofs:
        notes.append("no roof detection overlaps the target footprint: no roof cross-check")

    # --- tree overhang per plane (ROOF-04 A_tree, SHD-04 rule 1) -----------------------
    trees = _pick_images([x for x in measured if _label(x.det) in TREE_LABELS])
    out_planes: list[RoofPlane] = []
    tree_by_plane: dict[str, float] = {}
    for p, g in zip(planes, plane_m):
        if not trees or g is None or g.area <= 0:
            out_planes.append(p)
            continue
        hits = [(x, x.geom_m.intersection(g).area) for x in trees]
        hits = [(x, a) for x, a in hits if a > 0]
        if not hits:
            out_planes.append(p)
            continue
        # Fill-weighted sum, capped by the union so nested masks are not counted twice.
        weighted = sum(a * x.fill for x, a in hits)
        union = shapely.union_all([x.geom_m for x, _ in hits]).intersection(g).area
        plan_overlap = min(weighted, union)
        cosb = math.cos(math.radians(p.tilt_deg.expected))
        a_tree = plan_overlap / cosb if cosb > 1e-6 else plan_overlap
        tree_by_plane[p.id] = round(a_tree, 2)
        new_usable = round(max(0.0, p.usable_area_m2 - a_tree), 2)
        out_planes.append(p.model_copy(update={"usable_area_m2": min(new_usable, p.usable_area_m2)}))
        if any(x.basis != "mask_wkt" and x.fill < 1.0 for x, _ in hits):
            notes.append(f"{p.id}: tree located by its box, scaled by mask fill (mask_wkt absent)")
    unplaced = [p.id for p, g in zip(planes, plane_m) if trees and (g is None or g.area <= 0)]
    if unplaced:
        notes.append(f"no plane polygon for {', '.join(unplaced)}: tree overhang not applied")

    assumptions = []
    if tree_by_plane:
        total = sum(tree_by_plane.values())
        box_based = any(x.det.mask_wkt is None for x in trees)
        assumptions.append(Assumption(
            key="roof.tree_overhang_m2",
            label="Roof area under SAM 3 tree masks, removed from usable area (ROOF-04, SHD-04)"
                  + ("; tree located by its box scaled by mask fill [U]" if box_based else ""),
            value=Ranged(low=round(total, 2), expected=round(total, 2),
                         high=round(sum(_box_overlap(trees, g, p) for p, g in zip(planes, plane_m)), 2),
                         unit="m2"),
            source="vexcel", confidence=0.4 if box_based else 0.6,
            evidence=[EvidenceRef(kind="ortho" if x.det.image_id.lower().startswith(ORTHO_PREFIX)
                                  else "oblique", ref=x.det.mask_png_path or x.det.image_id,
                                  note=f"detections[{x.index}] {x.det.label} {x.det.confidence:.2f}")
                      for x in trees]
                     + [EvidenceRef(kind="default_table", ref="ROOF-04")],
        ))
    return MaskRefinement(planes=out_planes, detections=dets, roof_check=check,
                          tree_area_m2=tree_by_plane, assumptions=assumptions,
                          warnings=warnings, notes=notes)


def _box_overlap(trees: list[_Det], g: Optional[BaseGeometry], p: RoofPlane) -> float:
    """Upper end of the tree overhang: whole boxes, no fill scaling, in-plane."""
    if g is None or g.area <= 0:
        return 0.0
    u = shapely.union_all([x.geom_m for x in trees]).intersection(g).area
    cosb = math.cos(math.radians(p.tilt_deg.expected))
    return u / cosb if cosb > 1e-6 else u
