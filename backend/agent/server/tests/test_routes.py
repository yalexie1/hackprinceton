import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.schema import (SCHEMA_VERSION, DocumentDraft, PropertySummary, RunEvent,
                            RunResult)
from backend.server import app

EX = Path(__file__).resolve().parents[4] / "specs" / "examples"
client = TestClient(app)


def _body(flavor, name):
    return json.loads((EX / flavor / name).read_text())


def test_health():
    assert client.get("/api/health").json() == {"status": "ok", "schema_version": SCHEMA_VERSION}


def test_search_and_property():
    hits = client.get("/api/properties/search").json()
    assert [PropertySummary.model_validate(h) for h in hits]
    assert client.get("/api/properties/search", params={"segment": "commercial"}).json()[0]["segment"] == "commercial"
    sid = hits[0]["sid"]
    assert client.get(f"/api/properties/{sid}").json()["sid"] == sid
    r = client.get("/api/properties/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "property_not_found"


def test_run_flow_all_routes():
    for flavor in ("house", "office"):
        r = client.post("/api/runs", json=_body(flavor, "run_request.json"))
        assert r.status_code == 200
        run_id = r.json()["run_id"]

        with client.stream("GET", f"/api/runs/{run_id}/events") as s:
            assert s.headers["content-type"].startswith("text/event-stream")
            lines = [l for l in s.iter_lines() if l.startswith("data: ")]
        events = [RunEvent.model_validate_json(l[6:]) for l in lines]
        assert len(events) == len(_body(flavor, "run_events.json")) and events[-1].type == "done"

        run = RunResult.model_validate(client.get(f"/api/runs/{run_id}").json())
        assert run.run_id == run_id

        assert client.post(f"/api/runs/{run_id}/answers", json={"question_id": "q", "value": "x"}).json() == {"ok": True}
        assert client.patch(f"/api/runs/{run_id}", json={"budget_usd": 500}).json() == {"ok": True}
        assert client.get(f"/api/runs/{run_id}").json()["request"]["budget_usd"] == 500

        dreq = {**_body(flavor, "document_request.json"), "run_id": run_id}
        d = client.post(f"/api/runs/{run_id}/documents", json=dreq)
        draft = DocumentDraft.model_validate(d.json())
        g = client.get(f"/api/runs/{run_id}/documents/{draft.doc_id}")
        assert g.json() == d.json()


def test_unknown_run_is_404_envelope():
    for method, path, kw in [("get", "/api/runs/zzz", {}), ("get", "/api/runs/zzz/events", {}),
                             ("post", "/api/runs/zzz/answers", {"json": {"question_id": "q"}}),
                             ("patch", "/api/runs/zzz", {"json": {}}),
                             ("get", "/api/runs/zzz/documents/d", {})]:
        r = getattr(client, method)(path, **kw)
        assert r.status_code == 404, path
        assert set(r.json()["error"]) == {"code", "message"}


def test_document_errors_and_validation():
    run_id = client.post("/api/runs", json=_body("house", "run_request.json")).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}/documents/missing").status_code == 404
    r = client.post("/api/runs", json={"bad": 1})
    assert r.status_code == 422 and "error" in r.json()
    assert client.get("/api/assets/x/y.jpg").status_code == 404


# ---- G8: routes on the data door ----

def test_search_passes_all_seven_parameters(monkeypatch):
    from backend.data_layer import api as data
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return []

    monkeypatch.setattr(data, "search_properties", fake)
    r = client.get("/api/properties/search", params={
        "q": "west", "segment": "commercial", "use_type": "office", "lat": 29.7,
        "lon": -95.4, "radius_m": 500, "limit": 3})
    assert r.status_code == 200 and r.json() == []
    assert seen == {"q": "west", "segment": "commercial", "use_type": "office",
                    "lat": 29.7, "lon": -95.4, "radius_m": 500.0, "limit": 3}


def test_search_rejects_unknown_enum():
    r = client.get("/api/properties/search", params={"segment": "industrial"})
    assert r.status_code == 422 and set(r.json()["error"]) == {"code", "message"}


def test_unknown_sid_is_404():
    r = client.get("/api/properties/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "property_not_found"


def test_asset_outside_cache_is_404(monkeypatch):
    from backend.data_layer import api as data
    assert client.get("/api/assets/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/assets/%2Fetc%2Fpasswd").status_code == 404
    r = client.get("/api/assets/not/cached.jpg")
    assert r.status_code == 404 and r.json()["error"]["code"] == "asset_not_found"
    monkeypatch.setattr(data, "get_asset", lambda path: b"\xff\xd8img")
    ok = client.get("/api/assets/roof/a.jpg")
    assert ok.status_code == 200 and ok.content == b"\xff\xd8img"
    assert ok.headers["content-type"] == "image/jpeg"
