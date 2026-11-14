"""D8: Vexcel imagery and SAM 3 detection.

The numbers asserted here were measured live on the golden house parcel on
2026-11-14 and are recorded in `specs/data-integration.md` 4.4. Nothing here touches
the network: the payload fixture is a reduced copy of a real response with the real
metadata and small synthetic masks, and every test injects its transport.
"""
from __future__ import annotations

import base64
import io
import json
import pathlib
import zlib

import pytest

from backend.data_layer import cache, imagery
from backend.schema import VexcelDetection

#: The real `images[].metadata` for the golden house ortho crop. Verified values: the
#: footprint and the pixel dimensions imply 0.06182 by 0.06140 m per pixel, while the
#: service reports min-gsd 0.05623 and max-gsd 0.07821 - which is why the gsd fields
#: are not the scale.
HOUSE_META = {
    "geometry": ("POLYGON ((-118.31716686487198 34.09326283447764, "
                 "-118.31716686487198 34.093675978101366, "
                 "-118.31699788570404 34.093675978101366, "
                 "-118.31699788570404 34.09326283447764, "
                 "-118.31716686487198 34.09326283447764))"),
    "srid": 4326, "product-type": "spherical-ortho",
    "min-gsd": 0.05622858, "max-gsd": 0.07820945,
    "collection": "us-ca-losangeles-2025", "layer": "urban",
    "last-capture-date": 1765400614000,
    "width": 252, "height": 744,
}


def _png(width: int, height: int, white: int) -> bytes:
    """A minimal greyscale PNG with `white` white pixels, the rest black.

    Hand-built rather than copied from a real response: a mask is image bytes, and
    `specs/data-integration.md` 6.4 forbids committing any API response bytes.
    """
    rows = b""
    remaining = white
    for _ in range(height):
        row = bytearray(width)
        for x in range(width):
            if remaining > 0:
                row[x] = 255
                remaining -= 1
        rows += b"\x00" + bytes(row)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (len(data).to_bytes(4, "big") + tag + data
                + zlib.crc32(tag + data).to_bytes(4, "big"))

    header = (width.to_bytes(4, "big") + height.to_bytes(4, "big")
              + bytes([8, 0, 0, 0, 0]))     # 8-bit greyscale
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def _response(detections: list[dict]) -> dict:
    """One feature per detection, which is the real shape - 13 features meant 13
    detections, not one feature holding 13."""
    return {
        "type": "FeatureCollection",
        "images": [{"image-id": "ortho-1", "endpoint": "ortho/extract",
                    "metadata": HOUSE_META}],
        "features": [
            {"type": "Feature", "properties": {"label": "roof", "detections": [d]}}
            for d in detections
        ],
    }


def _detection(conf: float, box: tuple[int, int, int, int], white: int) -> dict:
    x, y, w, h = box
    return {
        "imageId": "ortho-1",
        "confidence": conf,
        "pixel-bbox": [x, y, w, h],
        "bbox": "POLYGON ((-118.3171 34.0933, -118.3170 34.0933, "
                "-118.3170 34.0936, -118.3171 34.0936, -118.3171 34.0933))",
        "pixel-mask": base64.b64encode(_png(max(w, 1), max(h, 1), white)).decode(),
    }


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path / "cache"


def _poster(response, calls=None):
    def post(path, body):
        if calls is not None:
            calls.append((path, body))
        return 200, response
    return post


# ---------- the request shape ----------

def test_every_images_entry_carries_its_own_endpoint():
    """Omitting it fails with "Parameter 'endpoint' is mandatory for this service",
    a message that points at the top level and is misleading."""
    body = imagery.detect_request("POLYGON ((0 0, 1 0, 1 1, 0 0))",
                                  directions=("oblique-north", "oblique-south"))
    assert len(body["images"]) == 3
    assert all("endpoint" in image for image in body["images"])
    assert body["images"][0]["endpoint"] == "ortho/extract"
    assert {i["endpoint"] for i in body["images"][1:]} == {"oriented/extract"}


def test_pixel_bbox_accompanies_pixel_mask_and_the_defaults_are_the_measured_ones():
    body = imagery.detect_request("POLYGON ((0 0, 1 0, 1 1, 0 0))")
    include = body["model-input"]["include"]
    assert "pixel-mask" in include and "pixel-bbox" in include, "the service requires both"
    assert body["buffer-meter"] == 0, "detection must not spill onto the neighbours"
    element = body["model-input"]["elements"][0]
    assert element["model"] == "sam3"
    # 0.5 (the quickstart default) discards most real roof detections: 0.309-0.695.
    assert element["detection-threshold"] == 0.3
    assert imagery.DEFAULT_LABELS == ("roof",), '"roof plane" and "roof facet" return nothing'


# ---------- the transform ----------

def test_row_zero_is_north():
    """Verified against the service's own `bbox` for all 13 detections: north-up gives
    a 0.024 m mean corner error, south-up gives 17.1 m."""
    frame = imagery.ImageFrame("ortho-1", HOUSE_META)
    _, top_lat = frame.to_lonlat(0, 0)
    _, bottom_lat = frame.to_lonlat(0, frame.height)
    assert top_lat > bottom_lat, "row 0 must be the northern edge"
    assert top_lat == pytest.approx(frame.north)
    assert bottom_lat == pytest.approx(frame.south)


def test_the_corners_map_to_the_footprint_corners():
    frame = imagery.ImageFrame("ortho-1", HOUSE_META)
    assert frame.to_lonlat(0, 0) == pytest.approx((frame.west, frame.north))
    assert frame.to_lonlat(frame.width, frame.height) == pytest.approx(
        (frame.east, frame.south))


def test_scale_comes_from_the_footprint_not_the_gsd():
    """The reported gsd brackets the truth without matching it. Using `min-gsd` would
    under-state ground area by about 17 %."""
    frame = imagery.ImageFrame("ortho-1", HOUSE_META)
    per_pixel = frame.pixel_area_m2()
    assert per_pixel == pytest.approx(0.06182 * 0.06140, rel=0.01)
    from_min_gsd = HOUSE_META["min-gsd"] ** 2
    assert from_min_gsd < per_pixel * 0.9, "min-gsd is not the scale and must not be used"


def test_an_unusable_frame_is_reported_not_guessed():
    assert not imagery.ImageFrame("x", {}).usable
    assert not imagery.ImageFrame("x", {"width": 10, "height": 0,
                                        "geometry": HOUSE_META["geometry"]}).usable


# ---------- masks ----------

def test_mask_area_counts_white_pixels_and_scales_them():
    frame = imagery.ImageFrame("ortho-1", HOUSE_META)
    png = _png(10, 10, 40)
    assert imagery.mask_pixel_count(png) == 40
    assert imagery.mask_area_m2(png, frame) == pytest.approx(40 * frame.pixel_area_m2())


def test_an_undecodable_mask_is_none_rather_than_zero():
    """Zero area would read as "this roof has no surface", which is a wrong answer
    rather than a missing one."""
    frame = imagery.ImageFrame("ortho-1", HOUSE_META)
    assert imagery.mask_pixel_count(b"not a png") is None
    assert imagery.mask_area_m2(b"not a png", frame) is None


def test_mask_area_is_none_when_the_frame_is_unusable():
    assert imagery.mask_area_m2(_png(4, 4, 4), imagery.ImageFrame("x", {})) is None


# ---------- detection ----------

def test_the_label_comes_from_the_feature_not_the_detection():
    response = _response([_detection(0.5, (0, 0, 4, 4), 8)])
    found, _ = imagery.detect("POLYGON ((0 0, 1 0, 1 1, 0 0))", post=_poster(response))
    assert [d.label for d in found] == ["roof"]


def test_a_negative_pixel_bbox_origin_is_carried_and_clamped():
    """The first detection on the golden house has `x = -1`: the box starts outside
    the image."""
    response = _response([_detection(0.309, (-1, 134, 44, 49), 100)])
    found, _ = imagery.detect("POLYGON ((0 0, 1 0, 1 1, 0 0))", post=_poster(response))
    assert found[0].pixel_bbox == (-1, 134, 44, 49)

    frame = imagery.ImageFrame("ortho-1", HOUSE_META)
    wkt = imagery._mask_bbox_wkt({"pixel-bbox": [-1, 134, 44, 49]}, frame)
    lons = [float(v) for v in imagery._NUM.findall(wkt)][0::2]
    assert min(lons) >= frame.west, "a clamped box must stay inside the footprint"


def test_masks_are_cached_as_bytes_that_get_asset_can_serve():
    response = _response([_detection(0.5, (0, 0, 4, 4), 8)])
    found, _ = imagery.detect("POLYGON ((0 0, 1 0, 1 1, 0 0))", sid="SID",
                              post=_poster(response))
    path = found[0].mask_png_path
    assert path
    assert (cache._ROOT / path).read_bytes()[:4] == b"\x89PNG", "not a PNG on disk"


def test_a_cache_path_inside_the_repo_becomes_repo_relative():
    """`mask_png_path` and `ortho_path` are resolved against the repo root by
    `get_asset`, so an absolute path from the cache has to be converted. A cache
    pointed outside the repo (as these tests do) has no relative form, and saying so
    beats inventing one."""
    inside = cache._ROOT / "data" / "cache" / "vexcel-mask" / "x.png"
    assert cache.relative(inside) == "data/cache/vexcel-mask/x.png"
    outside = pathlib.Path("/tmp/elsewhere/x.png")
    assert cache.relative(outside) == "/tmp/elsewhere/x.png"


def test_mask_wkt_is_left_unset_on_purpose():
    """A convex hull would be a valid polygon whose area is silently wrong for a
    concave fragment, and a consumer would reasonably take its area."""
    response = _response([_detection(0.5, (0, 0, 4, 4), 8)])
    found, _ = imagery.detect("POLYGON ((0 0, 1 0, 1 1, 0 0))", post=_poster(response))
    assert found[0].mask_wkt is None
    assert "silently wrong" in imagery.MASK_WKT_NOTE


def test_every_detection_validates_against_the_contract():
    response = _response([_detection(0.31, (0, 0, 4, 4), 5),
                          _detection(0.69, (5, 5, 6, 6), 9)])
    found, _ = imagery.detect("POLYGON ((0 0, 1 0, 1 1, 0 0))", post=_poster(response))
    assert len(found) == 2
    for detection in found:
        VexcelDetection.model_validate(detection.model_dump(mode="json"))


def test_finding_nothing_is_a_note_and_names_the_label_trap():
    found, notes = imagery.detect("POLYGON ((0 0, 1 0, 1 1, 0 0))",
                                  post=_poster(_response([])))
    assert found == []
    note = next(n for n in notes if n.what.endswith("no-detections"))
    assert note.status == "missing"
    assert "roof plane" in note.detail


def test_a_bare_point_404_is_a_normal_outcome():
    """4.4: a `POINT` makes `elements/detect` return 404. The caller must pass the
    parcel polygon, and the record has to say so rather than raising."""
    found, notes = imagery.detect("POINT(0 0)", post=lambda p, b: (404, None))
    assert found == []
    assert notes[0].status == "missing" and "no parcel" in notes[0].detail


def test_an_undecodable_mask_is_dropped_with_a_record():
    bad = _detection(0.5, (0, 0, 4, 4), 8)
    bad["pixel-mask"] = "!!!not base64!!!"
    found, notes = imagery.detect("POLYGON ((0 0, 1 0, 1 1, 0 0))",
                                  post=_poster(_response([bad])))
    assert len(found) == 1 and found[0].mask_png_path is None
    assert any(n.what.endswith("pixel-mask") and n.status == "error" for n in notes)


def test_an_injected_transport_is_not_cached():
    calls = []
    response = _response([_detection(0.5, (0, 0, 4, 4), 8)])
    imagery.detect("POLYGON ((0 0, 1 0, 1 1, 0 0))", post=_poster(response, calls))
    imagery.detect("POLYGON ((0 0, 1 0, 1 1, 0 0))", post=_poster(response, calls))
    assert len(calls) == 2, "an injected transport was cached"


# ---------- the area rule ----------

def test_roof_area_takes_the_largest_mask_not_the_sum():
    """The masks are nested: 8 of the other 12 detections are 100 % inside the largest
    one's box. Summing gives 485.8 m2 against a 190.4 m2 footprint - 2.6x over."""
    frame = imagery.ImageFrame("ortho-1", HOUSE_META)
    big, small = 4000, 500
    response = _response([
        _detection(0.484, (0, 0, 100, 100), big),      # largest mask, mid confidence
        _detection(0.695, (0, 0, 40, 40), small),      # most confident, small
    ])
    area, notes = imagery.roof_area_m2("POLYGON ((0 0, 1 0, 1 1, 0 0))", sid="SID",
                                       post=_poster(response))
    assert area == pytest.approx(big * frame.pixel_area_m2())
    assert area != pytest.approx((big + small) * frame.pixel_area_m2()), "masks were summed"
    note = next(n for n in notes if n.what.endswith("roof-area"))
    assert "never summed" in note.detail


def test_roof_area_does_not_rank_by_confidence():
    """On the golden house the most confident detection (0.695) was 38.8 m2 and sat
    0 % inside the largest - the parcel has two structures and that is the secondary.
    Ranking by confidence hands back the garage."""
    response = _response([
        _detection(0.484, (0, 0, 100, 100), 4000),
        _detection(0.695, (0, 0, 40, 40), 500),
    ])
    pairs, _ = imagery.detect_with_areas("POLYGON ((0 0, 1 0, 1 1, 0 0))", sid="SID",
                                         post=_poster(response))
    by_area = max(pairs, key=lambda pair: pair[1])
    by_confidence = max(pairs, key=lambda pair: pair[0].confidence)
    assert by_area[0].confidence == 0.484
    assert by_confidence is not by_area, "the fixture must reproduce the real conflict"


def test_roof_area_is_none_when_no_mask_decodes():
    bad = _detection(0.5, (0, 0, 4, 4), 8)
    bad["pixel-mask"] = "!!!"
    area, notes = imagery.roof_area_m2("POLYGON ((0 0, 1 0, 1 1, 0 0))", sid="SID",
                                       post=_poster(_response([bad])))
    assert area is None
    assert any("do not substitute the bbox area" in (n.detail or "") for n in notes)


def test_mask_fill_is_well_below_its_bounding_box():
    """Measured fill ran 43-93 % of the box, so box area over-states a fragment by up
    to a factor of two. This is why area comes from the mask."""
    frame = imagery.ImageFrame("ortho-1", HOUSE_META)
    png = _png(100, 100, 4300)
    mask_area = imagery.mask_area_m2(png, frame)
    box_area = 100 * 100 * frame.pixel_area_m2()
    assert mask_area < box_area * 0.5


# ---------- the door ----------

def test_the_door_stays_offline_by_default(monkeypatch):
    """SPEC 14: the analysis lane must run with no network, so live detection is
    opt-in on the same flag as the bundle."""
    from backend.data_layer import api

    monkeypatch.delenv("DATA_LAYER_LIVE", raising=False)
    assert api.roof_area_m2("zvKHR9DHNjJ") is None
    found = api.detect_roof_elements("zvKHR9DHNjJ")
    assert isinstance(found, list)        # the fixture path, whatever it holds
