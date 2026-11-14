"""Vexcel imagery and SAM 3 detection (package D8).

Lives in the data lane because it is a network call, and SPEC 14 requires the
analysis lane to run without one.

**Read section 4.4 of `specs/data-integration.md` before trusting anything this
returns.** The label quality on roofs was measured live and it is poor: the exact
label `SPEC.md` 6.3 specifies, `"roof plane"`, returns **nothing**; `"roof"` returns
13 fragments on one small house; SAM 3 missed a chimney the precomputed attributes
report, invented two skylights the precomputed attributes say do not exist, and found
one of five roof vents. So this module delivers **located, measured masks with their
confidence and provenance** - not roof-plane geometry, and not an obstruction
inventory. The precomputed `roof-objects` counts remain the primary source for
obstructions and A11's parametric planes remain the primary source for geometry.

What is verified here, live on the golden house 2026-11-14:

- **The request shape.** `elements/detect` takes an area plus a list of *extract
  requests*, each needing its own `endpoint` key inside `images[]`. The error for a
  missing one - `Parameter 'endpoint' is mandatory for this service` - points at the
  top level and is misleading. `pixel-bbox` is required whenever `pixel-mask` is.
- **`features` is one feature per detection**, each carrying `properties.label` and a
  `properties.detections` list of length one. 13 features meant 13 detections of the
  single label `roof`, not one feature holding 13.
- **The pixel-to-map transform, and its direction.** `images[].metadata` carries
  `geometry` (the image footprint as an axis-aligned polygon), `width` and `height`,
  so pixels map linearly onto the footprint. Row 0 is **north**: checked by
  transforming every detection's `pixel-bbox` and comparing against the `bbox` the
  service returns for the same detection, over all 13 detections and both corners.
  North-up gives a mean corner error of **0.024 m** and a worst case of 0.124 m -
  sub-pixel. South-up gives **17.1 m** mean and 34.8 m worst. The direction is not a
  guess.
- **Do not use `min-gsd` or `max-gsd` for scale.** They bracket the truth without
  matching it: reported 0.05623 and 0.07821 m/px where the footprint and pixel
  dimensions imply 0.06182 by 0.06140. Using `min-gsd` would under-state ground area
  by about 17 %. The footprint and the pixel dimensions are the scale.
- **`pixel-bbox` can start outside the image.** The first detection on the golden
  house has `x = -1`, so pixel coordinates are clamped before being transformed or
  used to index the mask.
"""
from __future__ import annotations

import base64
import io
import math
import os
import re
import time
from typing import Callable, Optional

from backend.schema import FetchRecord, VexcelDetection

from . import cache, vexcel

#: Metres per degree of latitude, and of longitude at the equator. Good to about
#: 0.1 % over a parcel, which is far inside the mask's own quantisation.
_M_PER_DEG_LAT = 110_574.0
_M_PER_DEG_LON = 111_320.0

#: `"roof"`, because `"roof plane"` and `"roof facet"` both return nothing (4.4).
DEFAULT_LABELS = ("roof",)

#: The quickstart's 0.5 discards most real roof detections: measured confidences run
#: 0.309 to 0.695. The confidence travels on every detection so a caller can filter
#: harder, but the floor has to be low enough to see them at all.
DEFAULT_THRESHOLD = 0.3

#: Restricts detection to the parcel itself rather than the neighbours.
BUFFER_METER = 0

_NUM = re.compile(r"-?\d+\.?\d*")

Poster = Callable[[str, dict], tuple[int, Optional[dict]]]


# ---------- transport ----------

def _default_post(path: str, body: dict) -> tuple[int, Optional[dict]]:
    """POST with the same backoff as `vexcel._default_get`.

    Detection is slow - it runs a model over freshly extracted imagery - so the
    timeout is far longer than a attribute read.
    """
    import httpx  # lazy so offline tests need no transport

    delay = vexcel.BACKOFF_BASE_S
    for attempt in range(vexcel.MAX_RETRIES):
        resp = httpx.post(
            f"{vexcel.BASE}/{path}",
            json=body,
            headers={"X-API-KEY": vexcel.api_key(os.environ.get("VEXCEL_KEY_SET", ""))},
            timeout=300.0,
        )
        if resp.status_code == 429 and attempt < vexcel.MAX_RETRIES - 1:
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code in (403, 404):
            return resp.status_code, None
        resp.raise_for_status()
        return resp.status_code, resp.json()
    return 429, None


# ---------- the image footprint ----------

class ImageFrame:
    """The pixel-to-map transform for one extracted image, from its `metadata`.

    Built from the footprint polygon and the pixel dimensions, never from the gsd
    fields - see the module docstring for the 17 % reason.
    """

    def __init__(self, image_id: str, metadata: dict):
        self.image_id = image_id
        self.width = int(metadata.get("width") or 0)
        self.height = int(metadata.get("height") or 0)
        nums = [float(v) for v in _NUM.findall(metadata.get("geometry") or "")]
        lons, lats = nums[0::2], nums[1::2]
        self.west, self.east = (min(lons), max(lons)) if lons else (0.0, 0.0)
        self.south, self.north = (min(lats), max(lats)) if lats else (0.0, 0.0)
        self.collection = metadata.get("collection")
        self.capture_date = metadata.get("last-capture-date")
        self.product_type = metadata.get("product-type")

    @property
    def usable(self) -> bool:
        return self.width > 0 and self.height > 0 and self.east > self.west and self.north > self.south

    def to_lonlat(self, x: float, y: float) -> tuple[float, float]:
        """Pixel to (lon, lat). **Row 0 is north** - verified to 0.024 m mean error
        against the `bbox` the service returns for the same detection."""
        lon = self.west + (x / self.width) * (self.east - self.west)
        lat = self.north - (y / self.height) * (self.north - self.south)
        return lon, lat

    def pixel_area_m2(self) -> float:
        """Ground area of one pixel, from the footprint and the pixel dimensions."""
        mid_lat = (self.north + self.south) / 2.0
        w_m = (self.east - self.west) * _M_PER_DEG_LON * math.cos(math.radians(mid_lat))
        h_m = (self.north - self.south) * _M_PER_DEG_LAT
        return (w_m / self.width) * (h_m / self.height)


# ---------- the request ----------

def detect_request(
    parcel_wkt: str,
    *,
    labels: tuple[str, ...] = DEFAULT_LABELS,
    threshold: float = DEFAULT_THRESHOLD,
    directions: tuple[str, ...] = (),
) -> dict:
    """The verified `elements/detect` body.

    Every `images[]` entry carries its own `endpoint`; `pixel-bbox` accompanies
    `pixel-mask` because the service requires it.
    """
    images = [{
        "endpoint": "ortho/extract",
        "request": {"layer": vexcel.OBLIQUE_LAYER, "srid": 4326,
                    "wkt": parcel_wkt, "crop": "bounding_box"},
    }]
    for direction in directions:
        images.append({
            "endpoint": "oriented/extract",
            "request": {"layer": vexcel.OBLIQUE_LAYER, "srid": 4326, "wkt": parcel_wkt,
                        "product-type": direction, "rotation": "natural", "crop": "bbox"},
        })
    return {
        "wkt": parcel_wkt,
        "srid": 4326,
        "buffer-meter": BUFFER_METER,
        "images": images,
        "model-input": {
            "elements": [
                {"label": label, "model": "sam3", "detection-threshold": threshold}
                for label in labels
            ],
            "include": ["bbox", "confidence", "pixel-mask", "pixel-bbox"],
        },
    }


# ---------- masks ----------

def mask_pixel_count(png: bytes) -> Optional[int]:
    """White pixels in a mask PNG, or `None` if it cannot be decoded.

    The mask is white where the object is and is cropped to `pixel-bbox`, so this
    count times `ImageFrame.pixel_area_m2()` is the detection's ground area.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(png)) as img:
            grey = img.convert("L")
            return sum(1 for value in grey.getdata() if value >= 128)
    except Exception:
        return None


def mask_area_m2(png: bytes, frame: ImageFrame) -> Optional[float]:
    """Ground area of a detection's mask, in square metres.

    This is the number section 4.4 concluded SAM 3 is actually good for - usable roof
    *area*, not plane geometry. It counts mask pixels rather than taking the area of
    `bbox`, because a roof fragment is not its bounding box.
    """
    count = mask_pixel_count(png)
    if count is None or not frame.usable:
        return None
    return count * frame.pixel_area_m2()


# ---------- detection ----------

def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def _mask_bbox_wkt(detection: dict, frame: ImageFrame) -> Optional[str]:
    """The detection's pixel box as a map polygon, clamped to the image.

    Used only when the service omits `bbox`; normally its own value is kept, since
    this is a reconstruction of it and there is no reason to prefer ours.
    """
    box = detection.get("pixel-bbox")
    if not box or not frame.usable:
        return None
    x, y, w, h = (float(v) for v in box)
    x0 = _clamp(x, 0, frame.width)
    y0 = _clamp(y, 0, frame.height)
    x1 = _clamp(x + w, 0, frame.width)
    y1 = _clamp(y + h, 0, frame.height)
    west, north = frame.to_lonlat(x0, y0)
    east, south = frame.to_lonlat(x1, y1)
    ring = [(west, north), (east, north), (east, south), (west, south), (west, north)]
    return "POLYGON ((" + ", ".join(f"{lon} {lat}" for lon, lat in ring) + "))"


def detect(
    parcel_wkt: str,
    *,
    sid: str = "",
    labels: tuple[str, ...] = DEFAULT_LABELS,
    threshold: float = DEFAULT_THRESHOLD,
    directions: tuple[str, ...] = (),
    post: Optional[Poster] = None,
    refresh: bool = False,
    write_masks: bool = True,
) -> tuple[list[VexcelDetection], list[FetchRecord]]:
    """SAM 3 detections over one parcel, as contract objects with their masks cached.

    Returns `([], [FetchRecord])` for every normal empty outcome, because "SAM 3 found
    no roof here" is an answer and not a fault. `mask_wkt` is deliberately left unset -
    see `MASK_WKT_NOTE`.

    Cached by D4 when the default transport is used; an injected `post` bypasses the
    cache both ways. Detection is the most expensive call in the lane, so the cache
    matters more here than anywhere else.
    """
    detections, _frames, _masks, notes = _detect(
        parcel_wkt, sid=sid, labels=labels, threshold=threshold,
        directions=directions, post=post, refresh=refresh, write_masks=write_masks)
    return detections, notes


def _detect(
    parcel_wkt: str,
    *,
    sid: str,
    labels: tuple[str, ...],
    threshold: float,
    directions: tuple[str, ...],
    post: Optional[Poster],
    refresh: bool,
    write_masks: bool,
) -> tuple[list[VexcelDetection], dict[str, "ImageFrame"], dict[int, bytes], list[FetchRecord]]:
    """`detect`, also returning the per-image frames and the decoded mask bytes.

    The frames come back from here rather than being recovered from the cache later:
    an injected transport is deliberately not cached, so anything that went back to
    the cache for the metadata would silently lose its scale in exactly the case where
    the caller is in control - tests, most of all.
    """
    body = detect_request(parcel_wkt, labels=labels, threshold=threshold,
                          directions=directions)
    shape = {"labels": sorted(labels), "threshold": threshold,
             "directions": sorted(directions), "buffer": BUFFER_METER}

    payload, from_cache = cache.cached_json(
        "vexcel-detect", parcel_wkt,
        lambda: _as_payload((post or _default_post)("elements/detect", body)),
        shape, use_cache=post is None, refresh=refresh,
    )
    status, response = payload.get("status"), payload.get("body")

    if status == 429:
        if post is None and not from_cache:
            cache.path_for("vexcel-detect", parcel_wkt, shape).unlink(missing_ok=True)
        return [], {}, {}, [cache.record("vexcel.rate_limited", "elements/detect")]
    if status == 403:
        return [], {}, {}, [cache.record("vexcel.outside_coverage", "elements/detect")]
    if status == 404:
        # 4.4: a bare POINT makes this 404. The caller should pass the parcel polygon.
        return [], {}, {}, [cache.record("vexcel.no_parcel", f"elements/detect: {parcel_wkt[:40]}")]
    if not response:
        return [], {}, {}, [cache.record("vexcel.no_features", "elements/detect")]

    frames = {
        image.get("image-id"): ImageFrame(image.get("image-id") or "", image.get("metadata") or {})
        for image in (response.get("images") or [])
    }
    notes: list[FetchRecord] = []
    if post is None:
        notes.append(cache.cache_note("vexcel", "elements/detect", hit=from_cache))

    out: list[VexcelDetection] = []
    masks: dict[int, bytes] = {}
    undecodable = 0
    for index, feature in enumerate(response.get("features") or []):
        props = feature.get("properties") or {}
        # 4.4: the label is on the feature, not on the detection.
        label = props.get("label") or ""
        for order, raw in enumerate(props.get("detections") or []):
            image_id = raw.get("imageId") or ""
            frame = frames.get(image_id)
            mask_path = None
            png = _mask_bytes(raw)
            if png and write_masks:
                written = cache.write_bytes(
                    "vexcel-mask", sid or _short(parcel_wkt),
                    png, {"image": image_id, "i": index, "j": order}, suffix=".png")
                mask_path = cache.relative(written)
            elif raw.get("pixel-mask") and png is None:
                undecodable += 1

            if png:
                masks[len(out)] = png
            bbox = raw.get("bbox") or (frame and _mask_bbox_wkt(raw, frame)) or ""
            out.append(VexcelDetection(
                label=label,
                confidence=float(raw.get("confidence") or 0.0),
                image_id=image_id,
                bbox_wkt=bbox,
                pixel_bbox=_as_pixel_bbox(raw.get("pixel-bbox")),
                mask_png_path=mask_path,
                mask_wkt=None,
            ))

    if not out:
        notes.append(FetchRecord(
            layer="vexcel", what="elements/detect:no-detections", status="missing",
            detail=f"SAM 3 found nothing for {sorted(labels)} at threshold {threshold}; "
                   f'"roof plane" and "roof facet" are known to return nothing - use "roof"',
        ))
    if undecodable:
        notes.append(FetchRecord(
            layer="vexcel", what="elements/detect:pixel-mask", status="error",
            detail=f"{undecodable} mask(s) were not valid base64 PNG and were dropped",
        ))
    return out, frames, masks, notes


def detect_with_areas(
    parcel_wkt: str, **kwargs
) -> tuple[list[tuple[VexcelDetection, Optional[float]]], list[FetchRecord]]:
    """`detect`, with each detection paired to its mask's ground area in m2.

    The area is not on `VexcelDetection` - the contract has nowhere to put it yet -
    so it is returned beside each detection rather than smuggled into another field.
    """
    detections, frames, masks, notes = _detect(
        parcel_wkt,
        sid=kwargs.get("sid", ""),
        labels=kwargs.get("labels", DEFAULT_LABELS),
        threshold=kwargs.get("threshold", DEFAULT_THRESHOLD),
        directions=kwargs.get("directions", ()),
        post=kwargs.get("post"),
        refresh=kwargs.get("refresh", False),
        write_masks=kwargs.get("write_masks", True),
    )
    out: list[tuple[VexcelDetection, Optional[float]]] = []
    for index, detection in enumerate(detections):
        frame = frames.get(detection.image_id)
        png = masks.get(index)
        area = mask_area_m2(png, frame) if (png and frame) else None
        out.append((detection, area))
    return out, notes


def roof_area_m2(
    parcel_wkt: str, **kwargs
) -> tuple[Optional[float], list[FetchRecord]]:
    """Usable roof area for the primary structure, from the **largest single mask**.

    This is the one number section 4.4 concluded SAM 3 is genuinely good for, and all
    three parts of that sentence were measured on the golden house, 13 detections at
    threshold 0.3:

    - **Largest, not summed.** The masks are *nested*, not adjacent: 8 of the other 12
      detections are 100 % inside the largest one's box and 3 more are 81-97 % inside.
      Summing gives 485.8 m2 against a precomputed footprint of 190.4 m2 - **2.6x
      over**. The largest single mask gives **180.9 m2**, within **5 %** of the
      footprint, which is the agreement that makes this usable at all.
    - **Largest, not most confident.** The highest-confidence detection (0.695) is
      38.8 m2 and sits **0 %** inside the largest - this parcel has two structures and
      that one is the secondary. Ranking by confidence would hand back the garage.
    - **Not the bounding box.** Mask fill runs 43-93 % of its own box, so box area
      over-states a roof fragment by up to a factor of two.

    Returns `(None, notes)` when nothing was detected or no mask could be decoded,
    never a guess. The note names which detection the number came from.
    """
    pairs, notes = detect_with_areas(parcel_wkt, **kwargs)
    measured = [(area, d) for d, area in pairs if area is not None]
    if not measured:
        return None, notes + [FetchRecord(
            layer="vexcel", what="elements/detect:roof-area", status="missing",
            detail="no decodable mask, so no area; do not substitute the bbox area",
        )]
    area, detection = max(measured, key=lambda pair: pair[0])
    return area, notes + [FetchRecord(
        layer="vexcel", what="elements/detect:roof-area", status="ok",
        detail=(f"largest of {len(measured)} mask(s): {area:.1f} m2 at confidence "
                f"{detection.confidence:.3f}; masks are nested, so they are never summed"),
    )]


#: Why `VexcelDetection.mask_wkt` comes back `None` from this module.
#:
#: The contract describes it as "map polygon derived from the pixel mask". The honest
#: options were a convex hull or the exact rectilinear outline, and a hull is the
#: dangerous one: it is a valid single-ring polygon that a consumer would reasonably
#: take the area of, and for a concave roof fragment that area is wrong by an amount
#: nothing in the payload reveals. `bbox_wkt` already gives the location and
#: `mask_area_m2` gives the true area from pixel counts, so a hull would add no
#: capability and one silent trap.
#:
#: Proposed to @yalexie1 as an additive `mask_area_m2` field. Until the contract has
#: somewhere to put the real number, use `mask_area_m2(png, frame)` directly.
MASK_WKT_NOTE = (
    "left unset: a convex hull would be a polygon whose area is silently wrong for a "
    "concave fragment; use mask_area_m2() for area and bbox_wkt for location"
)


def _short(wkt: str) -> str:
    return wkt[:40]


def _as_payload(pair: tuple[int, Optional[dict]]) -> dict:
    status, body = pair
    return {"status": status, "body": body}


def _mask_bytes(detection: dict) -> Optional[bytes]:
    blob = detection.get("pixel-mask")
    if not isinstance(blob, str) or not blob:
        return None
    try:
        png = base64.b64decode(blob, validate=True)
    except Exception:
        return None
    return png if png[:4] == b"\x89PNG" else None


def _as_pixel_bbox(box) -> Optional[tuple[int, int, int, int]]:
    if not box or len(box) != 4:
        return None
    try:
        return tuple(int(v) for v in box)      # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


# ---------- image bytes ----------

def fetch_ortho(parcel_wkt: str, *, sid: str = "", post: Optional[Poster] = None,
                refresh: bool = False) -> tuple[Optional[str], list[FetchRecord]]:
    """Cache the parcel's ortho crop and return its repo-relative path.

    `get_asset` serves these bytes; a URL is never stored, because an extract link is
    signed and expires while a cached PNG does not.
    """
    return _fetch_image(
        "ortho/extract",
        {"layer": vexcel.OBLIQUE_LAYER, "srid": 4326, "wkt": parcel_wkt,
         "crop": "bounding_box"},
        sid=sid, identifier=f"{sid or _short(parcel_wkt)}-ortho",
        post=post, refresh=refresh,
    )


def fetch_oblique(parcel_wkt: str, direction: str, *, sid: str = "",
                  post: Optional[Poster] = None, refresh: bool = False
                  ) -> tuple[Optional[str], list[FetchRecord]]:
    """One oblique crop. Ask `vexcel.oblique_directions` first: obliques exist only in
    the `urban` layer and not every direction exists everywhere."""
    return _fetch_image(
        "oriented/extract",
        {"layer": vexcel.OBLIQUE_LAYER, "srid": 4326, "wkt": parcel_wkt,
         "product-type": direction, "rotation": "natural", "crop": "bbox"},
        sid=sid, identifier=f"{sid or _short(parcel_wkt)}-{direction}",
        post=post, refresh=refresh,
    )


def _fetch_image(endpoint: str, request: dict, *, sid: str, identifier: str,
                 post: Optional[Poster], refresh: bool
                 ) -> tuple[Optional[str], list[FetchRecord]]:
    """Both extract endpoints return image bytes, so this goes through the bytes cache
    rather than `cached_json`."""
    target = cache.path_for("vexcel-image", identifier, request, suffix=".png")
    if target.is_file() and not refresh:
        return cache.relative(target), [
            cache.cache_note("vexcel", endpoint, hit=True)]

    data = (post or _default_post_bytes)(endpoint, request)
    if data is None:
        return None, [cache.record("vexcel.no_parcel", f"{endpoint}: {identifier}")]
    cache.write_bytes("vexcel-image", identifier, data, request, suffix=".png")
    return cache.relative(target), [cache.cache_note("vexcel", endpoint, hit=False)]


def _default_post_bytes(path: str, body: dict) -> Optional[bytes]:
    import httpx

    resp = httpx.post(
        f"{vexcel.BASE}/{path}",
        json=body,
        headers={"X-API-KEY": vexcel.api_key(os.environ.get("VEXCEL_KEY_SET", ""))},
        timeout=300.0,
    )
    if resp.status_code in (403, 404):
        return None
    resp.raise_for_status()
    return resp.content
