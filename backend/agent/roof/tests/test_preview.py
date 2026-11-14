"""The property preview: only what is held, null otherwise, never the example coordinates."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agent import api
from backend.agent.roof import PropertyPreview, property_preview
from backend.agent.server.app import create_app
from backend.data_layer import api as data
from backend.schema import PropertyBundle

EX = Path(__file__).resolve().parents[4] / "specs" / "examples"


def bundle(flavor="house") -> PropertyBundle:
    return PropertyBundle.model_validate(json.loads((EX / flavor / "property_bundle.json").read_text()))


def test_no_bundle_is_all_null():
    p = property_preview("S1", None, None, lambda path: b"")
    assert p == PropertyPreview(sid="S1") and p.available is False
    assert p.georeference is None and p.ortho is None and p.oblique_paths == {}


def test_a_held_bundle_gives_georeference_footprint_parcel():
    b = bundle()
    p = property_preview("S1", b, "recorded_run", lambda path: b"\xff\xd8")
    assert p.available and p.origin == "recorded_run"
    assert p.georeference.latitude == b.matterport.georeference.latitude
    assert p.parcel_wkt == b.vexcel.parcel_wkt
    assert p.footprint_wkt == next(s.footprint_wkt for s in b.vexcel.structures if s.primary)


def test_oblique_paths_keep_only_files_that_are_held():
    b = bundle()
    b.vexcel.oblique_paths = {"north": "data/cache/x/n.jpg", "south": "data/cache/x/s.jpg"}

    def read(path):
        if path.endswith("s.jpg"):
            raise FileNotFoundError(path)
        return b"\xff\xd8"
    assert property_preview("S1", b, "cached_bundle", read).oblique_paths == {"north": "data/cache/x/n.jpg"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DEMO_DIR", str(tmp_path / "demo"))
    monkeypatch.setattr(data, "_bundle_cache_path", lambda sid: tmp_path / "cache" / sid / "bundle.json")
    return TestClient(create_app())


def sid_of_example(client):
    return client.get("/api/properties/search").json()[0]["sid"]


def test_route_is_empty_without_a_recording_or_cache(client):
    sid = sid_of_example(client)
    body = client.get(f"/api/properties/{sid}/preview").json()
    assert body["available"] is False and body["georeference"] is None and body["ortho"] is None


def test_route_serves_a_recording_and_the_cache_in_that_order(client, tmp_path):
    sid = sid_of_example(client)
    b = json.loads((EX / "house" / "property_bundle.json").read_text())
    rec = tmp_path / "demo" / sid
    rec.mkdir(parents=True)
    (rec / "bundle.json").write_text(json.dumps(b))
    (rec / "result.json").write_text(json.dumps({"data_source": "live"}))
    body = client.get(f"/api/properties/{sid}/preview").json()
    assert body["available"] and body["origin"] == "recorded_run"
    (rec / "bundle.json").unlink()
    cache = tmp_path / "cache" / sid
    cache.mkdir(parents=True)
    (cache / "bundle.json").write_text(json.dumps({"rule": data.BUNDLE_RULE_VERSION, "bundle": b}))
    assert client.get(f"/api/properties/{sid}/preview").json()["origin"] == "cached_bundle"


def test_unknown_sid_is_404(client):
    r = client.get("/api/properties/nope/preview")
    assert r.status_code == 404 and r.json()["error"]["code"] == "property_not_found"


def test_a_recording_made_from_example_data_is_not_served(client, tmp_path):
    sid = sid_of_example(client)
    rec = tmp_path / "demo" / sid
    rec.mkdir(parents=True)
    (rec / "bundle.json").write_text((EX / "house" / "property_bundle.json").read_text())
    (rec / "result.json").write_text(json.dumps({"data_source": "example"}))
    body = client.get(f"/api/properties/{sid}/preview").json()
    assert body["available"] is False and body["georeference"] is None


def test_a_cached_bundle_of_an_older_rule_is_not_served(client, tmp_path):
    sid = sid_of_example(client)
    cache = tmp_path / "cache" / sid
    cache.mkdir(parents=True)
    b = json.loads((EX / "house" / "property_bundle.json").read_text())
    (cache / "bundle.json").write_text(json.dumps({"rule": -1, "bundle": b}))
    assert client.get(f"/api/properties/{sid}/preview").json()["available"] is False


def test_cached_obliques_come_from_the_data_layer_without_a_fetch(client, tmp_path, monkeypatch):
    sid = sid_of_example(client)
    held = {"oblique-north": "data/cache/x/n.jpg", "oblique-south": "data/cache/x/s.jpg"}
    calls = []
    monkeypatch.setattr(data, "get_obliques", lambda s, live=True: calls.append(live) or (held, []), raising=False)
    monkeypatch.setattr(data, "get_asset", lambda path: b"" if path.endswith("n.jpg") else (_ for _ in ()).throw(FileNotFoundError(path)))
    body = client.get(f"/api/properties/{sid}/preview").json()
    assert body["oblique_paths"] == {"oblique-north": "data/cache/x/n.jpg"} and calls == [False]


def test_without_get_obliques_the_preview_still_answers(client, monkeypatch):
    monkeypatch.delattr(data, "get_obliques", raising=False)
    assert client.get(f"/api/properties/{sid_of_example(client)}/preview").json()["oblique_paths"] == {}
