"""Roof view (agent lane): everything the frontend needs to draw the roof on the aerial image.

Built from the run's saved bundle and result, so it works for a live run, a recording and an example.
All coordinates are lon/lat (SRID 4326), as in the bundle. The bundle keeps the ortho image but not its
footprint, so the image bounds are recovered in two steps, best first:

- `detection_fit`: every roof detection carries its box twice, in image pixels (`pixel_bbox`) and in
  map coordinates (`bbox_wkt`), and the image's pixel size is in its PNG header. An affine fit (row 0 is
  north, `imagery.ImageFrame`) from the largest box gives the footprint, and the other boxes must agree
  to two pixels or the fit is refused.
- `parcel_bbox`: the bounding box of the parcel polygon the ortho was requested for. Close, not exact.
"""
from __future__ import annotations

import re
import struct
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from backend.schema import PropertyBundle, RunResult

_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
FIT_TOLERANCE_PX = 2.0


class Bounds(BaseModel):
    west: float
    south: float
    east: float
    north: float


class OrthoView(BaseModel):
    path: str                       # for GET /api/assets/{path}
    bounds: Bounds
    bounds_source: Literal["detection_fit", "parcel_bbox"]
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    image_available: bool = False   # False: the file is not in the cache, so GET /api/assets/{path} would be a 404


class PlaneView(BaseModel):
    id: str
    polygon_wkt: str
    tilt_deg: float
    azimuth_deg: float
    usable_area_m2: float


class DetectionView(BaseModel):
    label: str
    confidence: float
    bbox_wkt: str
    mask_wkt: Optional[str] = None
    mask_area_m2: Optional[float] = None


class PanelView(BaseModel):
    plane_id: str
    polygon_wkt: Optional[str] = None
    annual_kwh: float
    shading_loss_fraction: float


class RoofView(BaseModel):
    srid: int = 4326
    ortho: Optional[OrthoView] = None
    planes: list[PlaneView] = []
    detections: list[DetectionView] = []
    panels: list[PanelView] = []
    panels_selected: bool = False   # True: PV_ROOF is in the plan; False: the array is only financeable (or absent)


def points(wkt: Optional[str]) -> list[tuple[float, float]]:
    nums = [float(v) for v in _NUM.findall(wkt or "")]
    return list(zip(nums[0::2], nums[1::2]))


def png_size(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _box(wkt: Optional[str]) -> Optional[tuple[float, float, float, float]]:
    pts = points(wkt)
    if len(pts) < 3:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def fit_bounds(detections, width: int, height: int) -> Optional[Bounds]:
    """The image footprint from the detection boxes, or None when they do not fit one affine map."""
    boxes = []
    for d in detections:
        px, geo = d.pixel_bbox, _box(d.bbox_wkt)
        if px and geo and px[2] > 0 and px[3] > 0 and geo[2] > geo[0] and geo[3] > geo[1]:
            boxes.append((px, geo))
    if not boxes:
        return None
    (x, y, w, h), (lon0, lat0, lon1, lat1) = max(boxes, key=lambda b: b[0][2] * b[0][3])
    dlon, dlat = (lon1 - lon0) / w, (lat1 - lat0) / h            # degrees per pixel
    west, north = lon0 - x * dlon, lat1 + y * dlat               # row 0 is north
    bounds = Bounds(west=west, east=west + width * dlon, north=north, south=north - height * dlat)
    for (bx, by, bw, bh), (g0, g1, g2, g3) in boxes:
        if (abs((g0 - west) / dlon - bx) > FIT_TOLERANCE_PX or abs((g2 - west) / dlon - (bx + bw)) > FIT_TOLERANCE_PX
                or abs((north - g3) / dlat - by) > FIT_TOLERANCE_PX
                or abs((north - g1) / dlat - (by + bh)) > FIT_TOLERANCE_PX):
            return None
    return bounds


def ortho_view(bundle: PropertyBundle, read_asset: Callable[[str], bytes]) -> Optional[OrthoView]:
    v = bundle.vexcel
    if v is None or not v.ortho_path:
        return None
    size, available = None, False
    try:
        size, available = png_size(read_asset(v.ortho_path)), True
    except Exception:                    # a missing file only costs the exact bounds
        pass
    if size:
        fitted = fit_bounds(v.detections, *size)
        if fitted is not None:
            return OrthoView(path=v.ortho_path, bounds=fitted, bounds_source="detection_fit",
                             width_px=size[0], height_px=size[1], image_available=True)
    box = _box(v.parcel_wkt)
    if box is None:
        return None
    return OrthoView(path=v.ortho_path, bounds=Bounds(west=box[0], south=box[1], east=box[2], north=box[3]),
                     bounds_source="parcel_bbox", width_px=size[0] if size else None,
                     height_px=size[1] if size else None, image_available=available)


def roof_view(bundle: PropertyBundle, result: RunResult, read_asset: Callable[[str], bytes]) -> RoofView:
    model = result.building_model
    planes = [PlaneView(id=p.id, polygon_wkt=p.polygon_wkt, tilt_deg=p.tilt_deg.expected,
                        azimuth_deg=p.azimuth_deg, usable_area_m2=p.usable_area_m2)
              for p in (model.roof_planes if model else [])]
    detections = [DetectionView(label=d.label, confidence=d.confidence, bbox_wkt=d.bbox_wkt,
                                mask_wkt=d.mask_wkt, mask_area_m2=d.mask_area_m2)
                  for d in (bundle.vexcel.detections if bundle.vexcel else [])]
    pv, selected = None, False
    plan = result.plan
    if plan is not None:
        pv = next((i.measure for i in plan.selected if i.measure.measure_id == "PV_ROOF"), None)
        selected = pv is not None
        pv = pv or next((m for m in plan.financeable if m.measure_id == "PV_ROOF"), None)
    pv = pv or next((m for m in result.measures if m.measure_id == "PV_ROOF" and m.solar), None)
    panels = [PanelView(plane_id=p.plane_id, polygon_wkt=p.polygon_wkt, annual_kwh=p.annual_kwh,
                        shading_loss_fraction=p.shading_loss_fraction)
              for p in (pv.solar.panels if pv is not None and pv.solar else [])]
    return RoofView(ortho=ortho_view(bundle, read_asset), planes=planes, detections=detections,
                    panels=panels, panels_selected=selected)
