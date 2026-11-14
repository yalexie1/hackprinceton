import json
import os
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from backend.agent import api
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


# ---- G9: routes on the run door ----

def _waiting_run(monkeypatch):
    request = _body("house", "run_request.json")
    run_id = client.post("/api/runs", json=request).json()["run_id"]
    run = api.get_run(run_id)
    monkeypatch.setattr(run, "status", "waiting_for_user")
    return run_id, run.questions[0]


def test_event_stream_ends_with_done():
    run_id = client.post("/api/runs", json=_body("house", "run_request.json")).json()["run_id"]
    with client.stream("GET", f"/api/runs/{run_id}/events") as s:
        events = [RunEvent.model_validate_json(l[6:]) for l in s.iter_lines() if l.startswith("data: ")]
    assert events and events[-1].type == "done"


def test_answer_to_waiting_run_reaches_the_door(monkeypatch):
    run_id, q = _waiting_run(monkeypatch)
    seen = []
    monkeypatch.setattr(api, "answer", lambda *a: seen.append(a))
    value = next(c.value for c in q.choices if c.value is not None)
    assert client.post(f"/api/runs/{run_id}/answers",
                       json={"question_id": q.id, "value": value}).json() == {"ok": True}
    # "I don't know" is a null value and still reaches the door
    assert client.post(f"/api/runs/{run_id}/answers", json={"question_id": q.id}).json() == {"ok": True}
    assert seen == [(run_id, q.id, value), (run_id, q.id, None)]


def test_bad_answers_are_refused(monkeypatch):
    run_id, q = _waiting_run(monkeypatch)
    seen = []
    monkeypatch.setattr(api, "answer", lambda *a: seen.append(a))
    r = client.post(f"/api/runs/{run_id}/answers", json={"question_id": "nope", "value": 1})
    assert r.status_code == 404 and r.json()["error"]["code"] == "question_not_found"
    r = client.post(f"/api/runs/{run_id}/answers", json={"question_id": q.id, "value": "banana"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_answer"
    assert seen == []


def test_answer_to_a_run_that_is_not_waiting_is_409():
    run_id = client.post("/api/runs", json=_body("house", "run_request.json")).json()["run_id"]
    r = client.post(f"/api/runs/{run_id}/answers", json={"question_id": "q_service_amps", "value": 100.0})
    assert r.status_code == 409 and r.json()["error"]["code"] == "run_not_waiting"


def test_invalid_run_request_is_422_envelope():
    r = client.post("/api/runs", json={"sid": "x", "budget_usd": "lots"})
    assert r.status_code == 422 and set(r.json()["error"]) == {"code", "message"}


# ---- G10: document routes ----

def test_document_roundtrip_and_refusals(monkeypatch):
    run_id = client.post("/api/runs", json=_body("house", "run_request.json")).json()["run_id"]
    dreq = {**_body("house", "document_request.json"), "run_id": run_id}
    post = client.post(f"/api/runs/{run_id}/documents", json=dreq)
    draft = DocumentDraft.model_validate(post.json())
    assert client.get(f"/api/runs/{run_id}/documents/{draft.doc_id}").json() == post.json()
    r = client.post(f"/api/runs/{run_id}/documents", json={**dreq, "run_id": "other"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "run_id_mismatch"
    monkeypatch.setattr(api.get_run(run_id), "status", "waiting_for_user")
    r = client.post(f"/api/runs/{run_id}/documents", json=dreq)
    assert r.status_code == 409 and r.json()["error"]["code"] == "run_not_done"
    assert client.post("/api/runs/zzz/documents", json=dreq).status_code == 404


# ---- G11: adjust and re-run ----

def _events_of(run_id):
    with client.stream("GET", f"/api/runs/{run_id}/events") as s:
        return [RunEvent.model_validate_json(l[6:]) for l in s.iter_lines() if l.startswith("data: ")]


def test_a_lower_budget_gives_new_events_ending_in_done_and_a_plan_with_that_budget():
    run_id = client.post("/api/runs", json=_body("house", "run_request.json")).json()["run_id"]
    before = _events_of(run_id)
    assert client.patch(f"/api/runs/{run_id}", json={"budget_usd": 500}).json() == {"ok": True}
    after = _events_of(run_id)
    assert len(after) > len(before) and after[-1].type == "done" and after[-1].message == "Re-run complete"
    assert any(e.type == "tool_call" and e.payload.get("name") == "set_budget" for e in after)
    run = RunResult.model_validate(client.get(f"/api/runs/{run_id}").json())
    assert run.plan.budget_usd == 500 and run.request.budget_usd == 500 and run.status == "done"


def test_an_override_key_that_is_not_an_assumption_is_refused_with_the_envelope():
    run_id = client.post("/api/runs", json=_body("house", "run_request.json")).json()["run_id"]
    r = client.patch(f"/api/runs/{run_id}", json={"overrides": {"not.an.assumption": 1.0}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_assumption"
    assert client.get(f"/api/runs/{run_id}").json()["request"]["overrides"].get("not.an.assumption") is None
    ok = client.patch(f"/api/runs/{run_id}", json={"overrides": {"occupancy.count": 6}})
    assert ok.status_code == 200
    assert client.get(f"/api/runs/{run_id}").json()["request"]["overrides"]["occupancy.count"] == 6


def test_bad_patches_and_runs_that_are_not_done():
    run_id = client.post("/api/runs", json=_body("house", "run_request.json")).json()["run_id"]
    assert client.patch(f"/api/runs/{run_id}", json={"budget_usd": -1}).status_code == 422
    r = client.patch(f"/api/runs/{run_id}", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "empty_patch"
    r = client.patch(f"/api/runs/{run_id}", json={"overrides": {"geometry.ceiling_height_m": 3.0}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_editable"
    api.get_run(run_id).status = "waiting_for_user"
    r = client.patch(f"/api/runs/{run_id}", json={"budget_usd": 100})
    assert r.status_code == 409 and r.json()["error"]["code"] == "run_not_done"


# ---------- documents from a recorded run, and an un-templated request (#274) ----------

@pytest.fixture
def recorded_run():
    """A run served from a recorded live run, the path the demo uses.

    `backend/agent/conftest.py` points `AGENT_DEMO_DIR` at an empty directory for every
    agent test, so a recording has to be built here rather than relying on whatever the
    developer happens to have in `data/runs/_demo/`. The three files are the ones
    `api._recorded` reads, and the example's own payloads stand in for a live run's.
    """
    demo = Path(os.environ["AGENT_DEMO_DIR"]) / _body("house", "property_summary.json")["sid"]
    demo.mkdir(parents=True, exist_ok=True)
    for target, source in (("result.json", "run_result.json"),
                           ("events.json", "run_events.json"),
                           ("bundle.json", "property_bundle.json")):
        (demo / target).write_text(json.dumps(_body("house", source)))

    run_id = client.post("/api/runs", json=_body("house", "run_request.json")).json()["run_id"]
    assert run_id.startswith("run_demo_"), "the recording was not picked up"
    return run_id


def test_a_document_from_a_recorded_run_carries_its_statutory_checklist(recorded_run):
    """`engine.fill_template` always returns an empty checklist - running the predicates
    is the caller's job. `LiveRun.draft` did it; the recorded-run path in `agent/api.py`
    did not, so a document drafted from a recording came back with no checklist at all.
    The demo serves recordings, and the checklist is what SPEC 15 step 7 shows."""
    body = {"run_id": recorded_run, "doc_type": "retrofit_contract_residential",
            "state": "CA", "measure_ids": ["ENV_ATTIC"], "fields": {}}
    r = client.post(f"/api/runs/{recorded_run}/documents", json=body)
    assert r.status_code == 200, r.text
    draft = r.json()
    assert len(draft["statutory_checks"]) >= 30, "the CA-R-* predicates did not run"
    assert any(not c["satisfied"] for c in draft["statutory_checks"]), \
        "unfilled statutory text must be reported unsatisfied"
    assert draft["unfilled_placeholders"], "a real fill leaves visible blanks"


def test_a_document_type_with_no_template_is_a_404_not_a_500(recorded_run):
    """The legal door raises LookupError rather than relabelling another document. The
    route had no handler for it, so it surfaced as an Internal Server Error."""
    # The set of templated documents grows: L4 added the commercial contract and L6 the
    # C-PACE package, so this names three that still have none rather than three that
    # happen not to today.
    for doc_type in ("bid_package_rfp", "solar_installation_agreement",
                     "energy_savings_guarantee"):
        body = {"run_id": recorded_run, "doc_type": doc_type, "state": "CA",
                "measure_ids": ["ENV_ATTIC"], "fields": {}}
        r = client.post(f"/api/runs/{recorded_run}/documents", json=body)
        assert r.status_code == 404, f"{doc_type}: {r.status_code} {r.text[:120]}"
        assert r.json()["error"]["code"] == "template_not_available"
        assert doc_type in r.json()["error"]["message"]


def test_an_answer_for_a_run_that_closed_meanwhile_is_a_409(monkeypatch):
    run_id = client.post("/api/runs", json=_body("house", "run_request.json")).json()["run_id"]
    api.get_run(run_id).status = "waiting_for_user"
    q = api.get_run(run_id).questions[0]

    def closed(*a, **k):
        raise LookupError("run is closed; it cannot take an answer")
    monkeypatch.setattr(api, "answer", closed)
    value = next(c.value for c in q.choices if c.value is not None)
    r = client.post(f"/api/runs/{run_id}/answers", json={"question_id": q.id, "value": value})
    assert r.status_code == 409 and r.json()["error"]["code"] == "run_not_waiting"
