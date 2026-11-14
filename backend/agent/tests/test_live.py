"""Live run door, offline: a scripted model drives the real graph, tools, runtime and server
door against the fixture-backed doors. No network, no API key."""
import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from backend.agent import api, live
from backend.agent.fixtures import EXAMPLES, flavors
from backend.schema import RunRequest, RunResult


class Scripted(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs: Any):
        return self


def call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"{name}-{len(args)}"}])


def task(agent):
    return call("task", description=f"do the {agent} part", subagent_type=agent)


def request(flavor="house") -> RunRequest:
    return RunRequest.model_validate_json((EXAMPLES / flavor / "run_request.json").read_text())


def script(sid, ask=True):
    orchestrator = [call("write_todos", todos=[{"content": "audit", "status": "in_progress"}]),
                    task("scout"), task("surveyor"), task("physicist"), task("financier")]
    if ask:
        orchestrator.append(call("ask_user"))
    orchestrator.append(AIMessage(content="The audit is complete."))
    subagents = [
        call("get_property_bundle", sid=sid), AIMessage(content="ingested"),
        call("observe_interior"), call("build_building_model"), AIMessage(content="modelled"),
        call("run_baseline"), call("evaluate_measure", measure_id="LGT_LED"), AIMessage(content="evaluated"),
        call("price_measure", measure_id="LGT_LED"), call("sensitivity"), call("build_plan"),
        AIMessage(content="planned"),
    ]
    return Scripted(messages=iter(orchestrator)), Scripted(messages=iter(subagents))


@pytest.fixture
def live_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "live")
    monkeypatch.setattr(live, "SETTINGS", None)

    def configure(req):
        model, sub = script(req.sid)
        monkeypatch.setattr(live, "SETTINGS", live.LiveSettings(model=model, subagent_model=sub,
                                                                runs_dir=tmp_path))
    return configure


def wait_for(cond, what, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def drain(run_id):
    async def go():
        return [e async for e in api.stream_events(run_id)]
    return asyncio.run(go())


def assumption(result: RunResult, key):
    return next(a for a in result.building_model.assumptions if a.key == key)


def test_live_run_pauses_for_the_question_and_resumes_with_the_answer(live_mode):
    req = request()
    live_mode(req)
    run_id = api.start_run(req)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    paused = api.get_run(run_id)
    assert paused.status == "waiting_for_user" and [q.id for q in paused.questions] == ["q_service_amps"]
    api.answer(run_id, "q_service_amps", 200.0)
    events = drain(run_id)
    assert events[-1].type == "done"
    assert {"stage_started", "stage_done", "todo", "tool_call", "question", "done"} <= {e.type for e in events}
    tools = [e.payload["name"] for e in events if e.type == "tool_call"]
    assert tools[0] == "get_property_bundle" and "set_assumption" in tools and "build_plan" in tools
    result = api.get_run(run_id)
    assert result.status == "done" and result.plan is not None and result.baseline is not None
    assert assumption(result, "electrical.service_amps").value.expected == 200.0
    RunResult.model_validate(result.model_dump(mode="json"))
    assert (run.files.root / "report.md").read_text() == "The audit is complete."


def test_resume_with_none_keeps_the_range(live_mode):
    req = request()
    live_mode(req)
    run_id = api.start_run(req)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    before = json.loads((EXAMPLES / "house" / "building_model.json").read_text())
    api.answer(run_id, "q_service_amps", None)          # "I don't know": Command(resume={"value": None})
    assert drain(run_id)[-1].type == "done"
    result = api.get_run(run_id)
    key = next(q for q in result.questions).assumption_key      # the asked question is kept
    old = next(a for a in before["assumptions"] if a["key"] == key)
    assert assumption(result, key).model_dump(mode="json")["value"] == old["value"]
    assert "set_assumption" not in [e.payload["name"] for e in run.events if e.type == "tool_call"]


def test_answer_without_an_open_question_is_refused(live_mode):
    req = request()
    live_mode(req)
    run_id = api.start_run(req)
    with pytest.raises(LookupError):
        api.answer(run_id, "q_service_amps", 100.0)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    with pytest.raises(LookupError):
        api.answer(run_id, "other", 100.0)
    api.answer(run_id, "q_service_amps", 100.0)
    drain(run_id)


def test_server_drives_a_live_run_and_a_document(live_mode):
    from backend.server import app
    client = TestClient(app)
    req = request()
    live_mode(req)
    run_id = client.post("/api/runs", json=req.model_dump(mode="json")).json()["run_id"]
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "waiting_for_user"
    assert client.post(f"/api/runs/{run_id}/answers",
                       json={"question_id": "q_service_amps", "value": 150.0}).json() == {"ok": True}
    with client.stream("GET", f"/api/runs/{run_id}/events") as s:
        lines = [l for l in s.iter_lines() if l.startswith("data: ")]
    assert json.loads(lines[-1][6:])["type"] == "done"
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "done"
    dreq = json.loads((EXAMPLES / "house" / "document_request.json").read_text())
    dreq["run_id"] = run_id
    draft = client.post(f"/api/runs/{run_id}/documents", json=dreq)
    assert draft.status_code == 200
    assert client.get(f"/api/runs/{run_id}/documents/{draft.json()['doc_id']}").json() == draft.json()


def test_an_agent_failure_becomes_an_error_event(live_mode, tmp_path, monkeypatch):
    req = request()
    monkeypatch.setattr(live, "SETTINGS", live.LiveSettings(
        model=Scripted(messages=iter([])), subagent_model=Scripted(messages=iter([])), runs_dir=tmp_path))
    run_id = api.start_run(req)
    events = drain(run_id)
    assert events[-1].type == "error"
    assert api.get_run(run_id).status == "error"


# ---- mode switch and replay ----

def test_replay_is_the_default_and_the_mode_is_validated(monkeypatch):
    monkeypatch.delenv("AGENT_MODE", raising=False)
    assert api.mode() == "replay"
    monkeypatch.setenv("AGENT_MODE", "bogus")
    with pytest.raises(ValueError):
        api.mode()


@pytest.mark.parametrize("flavor", flavors())
def test_replay_recognises_every_example_folder(flavor, monkeypatch):
    monkeypatch.delenv("AGENT_MODE", raising=False)
    req = request(flavor)
    run_id = api.start_run(req)
    assert flavor in run_id and api.get_run(run_id).property.sid == req.sid
    assert drain(run_id)[-1].type == "done"


def test_houston_office_is_an_example_folder():
    assert "office_houston" in flavors()


def test_parallel_tool_calls_do_not_lose_measures(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    req = request()
    model, sub = script(req.sid)
    run = live.LiveRun("run_lock", req, live.LiveSettings(model=model, subagent_model=sub,
                                                          runs_dir=tmp_path))
    t = run.tools
    t["get_property_bundle"](req.sid)
    t["observe_interior"]()
    t["build_building_model"]()
    t["run_baseline"]()
    ids = ["LGT_LED", "PV_ROOF", "ENV_ATTIC", "HVAC_HP", "WIN_SHADE", "ROOF_COOL", "DHW_HPWH", "CTRL_TSTAT"]
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda m: t["evaluate_measure"](m), ids))
    saved = {m["measure_id"] for m in run.files.read_json("measures.json")}
    assert saved == set(ids)
