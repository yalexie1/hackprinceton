"""The roof view: exact image bounds from the detections, the parcel box as the fallback, and the route."""
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agent import api
from backend.agent.roof import roof_view
from backend.agent.roof.roof import Bounds, fit_bounds, png_size
from backend.agent.server.app import create_app
from backend.schema import PropertyBundle, RunResult, VexcelDetection

EX = Path(__file__).resolve().parents[4] / "specs" / "examples"
W, H = 1000, 800
WEST, NORTH, DLON, DLAT = -118.40, 34.05, 0.00001, 0.000009        # footprint of a synthetic image


def png(w=W, h=H) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x06\x00\x00\x00"


def detection(x, y, w, h, shift=0.0):
    lon0, lon1 = WEST + x * DLON, WEST + (x + w) * DLON
    lat1, lat0 = NORTH - y * DLAT, NORTH - (y + h) * DLAT
    ring = [(lon0 + shift, lat0), (lon0 + shift, lat1), (lon1 + shift, lat1), (lon1 + shift, lat0), (lon0 + shift, lat0)]
    wkt = "POLYGON((" + ", ".join(f"{a:.9f} {b:.9f}" for a, b in ring) + "))"
    return VexcelDetection(label="roof", confidence=0.9, image_id="ortho-1", bbox_wkt=wkt, pixel_bbox=(x, y, w, h))


def test_png_size_reads_the_header_and_refuses_other_bytes():
    assert png_size(png(640, 480)) == (640, 480)
    assert png_size(b"not a png at all, just text...") is None and png_size(b"") is None


def test_bounds_are_recovered_from_the_detection_boxes():
    got = fit_bounds([detection(100, 50, 300, 200), detection(600, 400, 50, 60)], W, H)
    want = Bounds(west=WEST, east=WEST + W * DLON, north=NORTH, south=NORTH - H * DLAT)
    for field in ("west", "east", "north", "south"):
        assert getattr(got, field) == pytest.approx(getattr(want, field), abs=1e-9)


def test_a_box_that_starts_outside_the_image_still_fits():
    assert fit_bounds([detection(-20, 10, 200, 100)], W, H) is not None


def test_boxes_that_disagree_are_not_a_fit():
    assert fit_bounds([detection(100, 50, 300, 200), detection(600, 400, 50, 60, shift=0.0003)], W, H) is None
    assert fit_bounds([], W, H) is None


def bundle(flavor="house", detections=None):
    b = PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())
    if detections is not None:
        b.vexcel.detections = detections
    return b


def result(flavor="house"):
    return RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())


def test_the_view_uses_the_fit_when_the_image_is_readable():
    v = roof_view(bundle(detections=[detection(100, 50, 300, 200)]), result(), lambda path: png())
    assert v.ortho.bounds_source == "detection_fit" and (v.ortho.width_px, v.ortho.height_px) == (W, H)
    assert v.ortho.image_available and v.ortho.bounds.west == pytest.approx(WEST, abs=1e-9)


def test_the_view_falls_back_to_the_parcel_box_and_says_the_image_is_missing():
    def missing(path):
        raise FileNotFoundError(path)
    v = roof_view(bundle(), result(), missing)
    o = v.ortho
    assert o.bounds_source == "parcel_bbox" and not o.image_available and o.width_px is None
    assert o.bounds.west < o.bounds.east and o.bounds.south < o.bounds.north
    assert o.path == bundle().vexcel.ortho_path


def test_planes_detections_and_panels_come_from_the_run():
    r = result()
    v = roof_view(bundle(), r, lambda p: png())
    assert [p.id for p in v.planes] == [p.id for p in r.building_model.roof_planes]
    assert len(v.detections) == len(bundle().vexcel.detections) and v.srid == 4326
    pv = next((i.measure for i in r.plan.selected if i.measure.measure_id == "PV_ROOF"), None)
    assert v.panels_selected is (pv is not None) and len(v.panels) == (len(pv.solar.panels) if pv else len(v.panels))


def test_a_run_without_vexcel_has_no_ortho_and_does_not_fail():
    b = bundle()
    b.vexcel = None
    v = roof_view(b, result(), lambda p: png())
    assert v.ortho is None and v.detections == []


def test_the_route_serves_the_view_for_a_run_and_404s_an_unknown_run():
    client = TestClient(create_app())
    run_id = client.post("/api/runs", json=result().request.model_dump(mode="json")).json()["run_id"]
    r = client.get(f"/api/runs/{run_id}/roof")
    assert r.status_code == 200
    body = r.json()
    assert body["srid"] == 4326 and body["ortho"]["bounds_source"] in ("detection_fit", "parcel_bbox")
    assert body["planes"] and "image_available" in body["ortho"]
    missing = client.get("/api/runs/run_nope/roof")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "run_not_found"


def test_the_route_also_serves_a_recorded_run(monkeypatch, tmp_path):
    import json
    import os
    r = result()
    demo = Path(os.environ["AGENT_DEMO_DIR"]) / r.property.sid
    demo.mkdir(parents=True, exist_ok=True)
    for target, source in (("result.json", "run_result.json"), ("events.json", "run_events.json"),
                           ("bundle.json", "property_bundle.json")):
        (demo / target).write_text((EX / "house" / source).read_text())
    client = TestClient(create_app())
    run_id = client.post("/api/runs", json=r.request.model_dump(mode="json")).json()["run_id"]
    assert run_id.startswith("run_demo_")
    body = client.get(f"/api/runs/{run_id}/roof").json()
    assert body["planes"] and body["ortho"]["path"] == bundle().vexcel.ortho_path
