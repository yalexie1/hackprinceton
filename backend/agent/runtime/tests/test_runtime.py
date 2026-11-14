import asyncio
import json
from pathlib import Path

import pytest

from backend.agent.runtime import RUN_FILES, RunStore, execute_run
from backend.schema import RunEvent, RunRequest, RunResult

EX = Path(__file__).resolve().parents[4] / "specs" / "examples"


def _fixture(flavor):
    run = json.loads((EX / flavor / "run_result.json").read_text())
    events = json.loads((EX / flavor / "run_events.json").read_text())
    return run, events


def fake_agent_for(flavor, fail_after=None):
    run, events = _fixture(flavor)
    bundle = json.loads((EX / flavor / "property_bundle.json").read_text())

    async def agent(request, files):
        for i, ev in enumerate(events):
            if ev["type"] == "done":
                continue
            if fail_after is not None and i == fail_after:
                raise RuntimeError("boom")
            if ev["type"] == "error":
                continue            # source events carry a recoverable error; keep the run clean
            yield ev
        files.write("bundle.json", bundle)
        files.write("model.json", run["building_model"])
        files.write("baseline.json", run["baseline"])
        files.write("measures.json", run["measures"])
        files.write("plan.json", run["plan"])
        files.write("report.md", run["narrative_md"])
        yield {"type": "done"}
    return agent


def collect(request, agent, store):
    async def go():
        return [e async for e in execute_run(request, agent, store, run_id="r1")]
    return asyncio.run(go())


@pytest.mark.parametrize("flavor", ["house", "office"])
def test_events_files_and_reload(tmp_path, flavor):
    run, events = _fixture(flavor)
    request = RunRequest.model_validate(run["request"])
    store = RunStore(tmp_path)
    got = collect(request, fake_agent_for(flavor), store)
    expected_types = {e["type"] for e in events} - {"error"}
    assert expected_types <= {e.type for e in got}
    assert got[-1].type == "done"
    for name in RUN_FILES:
        assert (tmp_path / "r1" / name).exists()
    saved = store.load("r1")
    RunResult.model_validate(json.loads(saved.model_dump_json()))
    assert saved.status == "done" and saved.plan == RunResult.model_validate(run).plan
    assert saved.narrative_md == run["narrative_md"] and saved.warnings == []


def test_agent_exception_becomes_error(tmp_path):
    run, _ = _fixture("house")
    request = RunRequest.model_validate(run["request"])
    store = RunStore(tmp_path)
    # fails before bundle.json exists -> still an error event; no result can be built
    got = collect(request, fake_agent_for("house", fail_after=3), store)
    assert got[-1].type == "error" and "boom" in got[-1].message


def test_error_status_saved_when_bundle_exists(tmp_path):
    run, _ = _fixture("house")
    request = RunRequest.model_validate(run["request"])
    bundle = json.loads((EX / "house" / "property_bundle.json").read_text())

    async def agent(req, files):
        files.write("bundle.json", bundle)
        yield {"stage_started": "ingest"}
        raise ValueError("bad")

    store = RunStore(tmp_path)
    got = collect(request, agent, store)
    assert [e.type for e in got] == ["stage_started", "error"]
    saved = store.load("r1")
    assert saved.status == "error" and "bad" in saved.warnings[0]


def test_question_sets_waiting(tmp_path):
    run, _ = _fixture("house")
    request = RunRequest.model_validate(run["request"])
    q = run["questions"][0]
    bundle = json.loads((EX / "house" / "property_bundle.json").read_text())

    async def agent(req, files):
        files.write("bundle.json", bundle)
        yield {"question": q}

    store = RunStore(tmp_path)
    got = collect(request, agent, store)
    assert got[0].type == "question"
    assert store.load("r1").status == "waiting_for_user"


def test_unknown_run_and_bad_file_name(tmp_path):
    store = RunStore(tmp_path)
    with pytest.raises(KeyError):
        store.load("nope")
    with pytest.raises(ValueError):
        store.files("x").path("../evil")


# ---- event shapes the frontend shows (todo, question, approval) ----

def test_a_todo_update_is_one_event_with_counts_and_the_current_item():
    from backend.agent.runtime.runtime import map_chunk
    todos = [{"content": "Fetch the property", "status": "completed"},
             {"content": "Build the model", "status": "in_progress"},
             {"content": "Simulate", "status": "pending", "extra": 1}]
    (ev,) = map_chunk({"todos": todos})
    assert ev.type == "todo" and ev.message == "1 of 3 done: Build the model"
    assert ev.payload == {"todos": [{"content": t["content"], "status": t["status"]} for t in todos],
                          "total": 3, "done": 1, "current": "Build the model"}
    (last,) = map_chunk({"todos": [dict(t, status="completed") for t in todos]})
    assert last.payload["current"] is None and last.message == "3 of 3 done"


def test_a_question_and_an_approval_are_both_question_events_told_apart_by_kind():
    from backend.agent.runtime.runtime import map_chunk
    q = {"id": "q_x", "prompt": "How big?", "choices": []}
    (ask,) = map_chunk({"question": q, "stage": "ask"})
    assert ask.type == "question" and ask.payload == {"question": q, "kind": "question"}
    proposal = {"doc_type": "retrofit_contract_residential", "state": "CA", "measure_ids": ["PV_ROOF"]}
    (gate,) = map_chunk({"question": q, "kind": "approval", "approval": proposal})
    assert gate.payload["kind"] == "approval" and gate.payload["approval"] == proposal


def test_the_counsel_gate_reaches_the_stream_as_an_approval_event():
    from backend.agent import live
    run = live.LiveRun.__new__(live.LiveRun)
    run._stage, run.pending, run._last_text = "S9", None, ""
    proposal = {"doc_type": "retrofit_contract_residential", "state": "CA", "measure_ids": ["PV_ROOF"]}

    class Interrupt:
        value = {"approval": proposal}
    (out,) = run._map_update({"__interrupt__": [Interrupt()]})
    assert out["kind"] == "approval" and out["approval"] == proposal
    assert out["question"]["id"] == "approve_retrofit_contract_residential"
    assert [c["value"] for c in out["question"]["choices"]] == [True, False]
    assert run.pending[0] == "approval"
