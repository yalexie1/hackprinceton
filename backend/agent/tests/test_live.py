"""Live run door, offline: a scripted model drives the real graph, tools, runtime and server
door against the fixture-backed doors. No network, no API key."""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from backend.agent import api, live
from backend.agent.runtime.replan import PatchError
from backend.agent.fixtures import EXAMPLES, flavors
from backend.schema import DocumentRequest, RunRequest, RunResult


def stub_doors():
    """Data and legal from their lanes, analysis from the agent lane's fixture-backed stub: these tests
    are about the agent's plumbing, not about the physics, and run offline in a moment."""
    from backend.agent import analysis_stub
    from backend.agent.tools import Doors
    from backend.data_layer import api as data
    from backend.legal import api as legal
    return Doors(data=data, analysis=analysis_stub, legal=legal)


class Scripted(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs: Any):
        return self


def call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"{name}-{len(args)}"}])


def task(agent):
    return call("task", description=f"do the {agent} part", subagent_type=agent)


def request(flavor="house") -> RunRequest:
    return RunRequest.model_validate_json((EXAMPLES / flavor / "run_request.json").read_text())


def script(sid, ask=True, plan=True, bad_tool=False, final=("The audit is complete.",)):
    orchestrator = [call("write_todos", todos=[{"content": "audit", "status": "in_progress"}]),
                    task("scout"), task("surveyor"), task("physicist"), task("financier")]
    if ask:
        orchestrator.append(call("ask_user"))
    orchestrator.extend(AIMessage(content=text) for text in final)
    subagents = [
        call("get_property_bundle", sid=sid), AIMessage(content="ingested"),
        call("observe_interior"), call("build_building_model"), AIMessage(content="modelled"),
        call("run_baseline"), call("evaluate_measure", measure_id="LGT_LED"),
        AIMessage(content="evaluated"),
        *([call("price_measure", measure_id="HVAC_ECON")] if bad_tool else []),     # a valid id, never evaluated
        call("price_measure", measure_id="LGT_LED"), call("sensitivity"),
        *([call("build_plan")] if plan else []),
        AIMessage(content="planned"),
    ]
    return Scripted(messages=iter(orchestrator)), Scripted(messages=iter(subagents))


@pytest.fixture(autouse=True)
def no_tracing_or_dotenv(monkeypatch):
    """Tests never read the developer's .env and never send a trace."""
    monkeypatch.setattr(live, "_load_env", lambda: None)
    for name in ("LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_PROJECT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def live_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "live")
    monkeypatch.setattr(live, "SETTINGS", None)

    def configure(req, **script_kwargs):
        model, sub = script(req.sid, **script_kwargs)
        monkeypatch.setattr(live, "SETTINGS", live.LiveSettings(model=model, subagent_model=sub, doors=stub_doors(),
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
        doors=stub_doors(), model=Scripted(messages=iter([])), subagent_model=Scripted(messages=iter([])), runs_dir=tmp_path))
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
    run = live.LiveRun("run_lock", req, live.LiveSettings(model=model, subagent_model=sub, doors=stub_doors(),
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


# ---- memoized tool calls ----

class Counting:
    """Wraps a door module and counts calls per function."""
    def __init__(self, inner):
        self._inner, self.calls = inner, {}

    def __getattr__(self, name):
        fn = getattr(self._inner, name)

        def counted(*a, **k):
            self.calls[name] = self.calls.get(name, 0) + 1
            return fn(*a, **k)
        return counted


def memo_run(tmp_path):
    from backend.agent import analysis_stub
    from backend.agent.tools import Doors
    from backend.data_layer import api as data
    from backend.legal import api as legal
    req = request()
    model, sub = script(req.sid)
    analysis = Counting(analysis_stub)
    run = live.LiveRun("run_memo", req, live.LiveSettings(
        model=model, subagent_model=sub, runs_dir=tmp_path,
        doors=Doors(data=data, analysis=analysis, legal=legal)))
    t = run.tools
    t["get_property_bundle"](req.sid)
    t["observe_interior"]()
    t["build_building_model"]()
    return run, t, analysis


def test_identical_call_is_answered_from_the_memo(tmp_path):
    run, t, analysis = memo_run(tmp_path)
    first = t["run_baseline"]()
    assert t["run_baseline"]() == first and analysis.calls["run_baseline"] == 1
    a = t["evaluate_measure"]("LGT_LED")
    assert t["evaluate_measure"]("LGT_LED") == a and analysis.calls["evaluate_measure"] == 1
    t["evaluate_measure"]("PV_ROOF")                       # other arguments: a real call
    assert analysis.calls["evaluate_measure"] == 2
    t["price_measure"]("LGT_LED")
    t["evaluate_measure"]("LGT_LED")                       # must not overwrite the priced row
    assert analysis.calls["evaluate_measure"] == 2
    row = next(m for m in run.files.read_json("measures.json") if m["measure_id"] == "LGT_LED")
    assert row["finance"] is not None
    t["price_measure"]("LGT_LED")
    assert analysis.calls["price_measure"] == 1 and run.memo_hits == 4


def test_a_changed_model_misses_the_memo(tmp_path):
    run, t, analysis = memo_run(tmp_path)
    t["run_baseline"]()
    t["set_assumption"]("occupancy.count", 5.0)
    t["run_baseline"]()                                    # same arguments, new model
    assert analysis.calls["run_baseline"] == 2
    t["set_assumption"]("occupancy.count", 5.0)            # idempotent repeat: answered from memo
    assert analysis.calls["set_assumption"] == 1


def test_a_failed_call_is_retried_and_fill_template_is_never_memoized(tmp_path):
    run, t, analysis = memo_run(tmp_path)
    assert "error" in t["evaluate_measure"]("NOT_A_MEASURE")
    assert "error" in t["evaluate_measure"]("NOT_A_MEASURE")
    assert analysis.calls["evaluate_measure"] == 2
    t["evaluate_measure"]("LGT_LED")
    args = ("retrofit_contract_residential", "CA", ["LGT_LED"], {})
    t["fill_template"](*args)
    t["fill_template"](*args)
    assert run.memo_hits == 0


def test_a_finished_live_run_is_adjusted_and_replanned(live_mode):
    req = request()
    live_mode(req)
    run_id = api.start_run(req)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    with pytest.raises(PatchError) as early:                       # paused, not finished
        api.update_run(run_id, budget_usd=500.0)
    assert early.value.code == "run_not_done"
    api.answer(run_id, "q_service_amps", 100.0)
    assert drain(run_id)[-1].type == "done"
    before = api.get_run(run_id)
    api.update_run(run_id, budget_usd=500.0, overrides={"occupancy.count": 5.0})
    events = drain(run_id)
    assert events[-1].type == "done" and events[-1].message == "Re-run complete"
    after = api.get_run(run_id)
    assert after.status == "done" and after.plan.budget_usd == 500.0 and after.request.overrides["occupancy.count"] == 5.0
    assert next(a for a in after.building_model.assumptions if a.key == "occupancy.count").value.expected == 5.0
    assert after.narrative_md == before.narrative_md
    assert [q.id for q in after.questions] == [q.id for q in before.questions]            # the answered question is kept
    with pytest.raises(PatchError) as bad:
        api.update_run(run_id, overrides={"nope": 1.0})
    assert bad.value.code == "unknown_assumption"
    assert api.get_run(run_id).plan.budget_usd == 500.0                                    # a refused patch changes nothing


# ---- tracing ----

def test_tracing_is_off_without_a_key_and_on_with_one():
    env = {}
    assert live.configure_tracing(env) is False and env["LANGSMITH_TRACING"] == "false"
    env = {"LANGSMITH_TRACING": "true"}                                   # asked for, but no key: off, no failure
    assert live.configure_tracing(env) is False and env["LANGCHAIN_TRACING_V2"] == "false"
    env = {"LANGSMITH_API_KEY": "k"}
    assert live.configure_tracing(env) is True and env["LANGSMITH_TRACING"] == "true"
    assert env["LANGSMITH_PROJECT"] == live.DEFAULT_PROJECT
    env = {"LANGSMITH_API_KEY": "k", "LANGSMITH_PROJECT": "mine"}
    assert live.configure_tracing(env) and env["LANGSMITH_PROJECT"] == "mine"
    env = {"LANGSMITH_API_KEY": "k", "LANGSMITH_TRACING": "false"}
    assert live.configure_tracing(env) is False


def test_a_traced_run_names_itself_and_asks_for_its_first_trace_id_only(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGSMITH_API_KEY", "k")
    live.configure_tracing()
    req = request()
    model, sub = script(req.sid)
    run = live.LiveRun("run_traced", req, live.LiveSettings(model=model, subagent_model=sub, doors=stub_doors(),
                                                            runs_dir=tmp_path))
    assert run.tracing and run.config["run_name"] == "energy-audit"
    assert run.config["metadata"]["sid"] == req.sid and f"sid:{req.sid}" in run.config["tags"]
    first, second = run._segment_config(), run._segment_config()
    assert first["run_id"] == run.trace_id and "run_id" not in second          # a resumed segment is its own trace
    monkeypatch.setenv("LANGSMITH_API_KEY", "")


def test_without_tracing_there_is_no_run_id_and_no_link(tmp_path):
    req = request()
    model, sub = script(req.sid)
    run = live.LiveRun("run_plain", req, live.LiveSettings(model=model, subagent_model=sub, doors=stub_doors(),
                                                           runs_dir=tmp_path))
    assert not run.tracing and "run_id" not in run._segment_config() and run.trace_url() is None


def test_a_live_run_completes_with_tracing_switched_off_and_keys_missing(live_mode):
    req = request()
    live_mode(req)
    run_id = api.start_run(req)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    api.answer(run_id, "q_service_amps", 100.0)
    assert drain(run_id)[-1].type == "done" and not run.tracing and os.environ["LANGSMITH_TRACING"] == "false"


# ---- a failing tool and a plan the agent never built ----

def test_a_failing_tool_becomes_a_run_event(live_mode):
    req = request()
    live_mode(req, bad_tool=True)
    run_id = api.start_run(req)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    api.answer(run_id, "q_service_amps", 100.0)
    events = drain(run_id)
    errors = [e for e in events if e.type == "error"]
    assert any("price_measure failed" in e.message and "call evaluate_measure" in e.message and e.stage == "S7"
               for e in errors)
    assert events[-1].type == "done" and any("price_measure failed" in w for w in api.get_run(run_id).warnings)


def test_the_runtime_builds_the_plan_the_agent_did_not(live_mode):
    req = request()
    live_mode(req, plan=False)
    run_id = api.start_run(req)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    api.answer(run_id, "q_service_amps", 100.0)
    events = drain(run_id)
    assert events[-1].type == "done"
    fallback = [e for e in events if e.type == "fallback" and e.payload.get("fallback") == "plan_built_by_runtime"]
    assert len(fallback) == 1 and fallback[0].stage == "S7"
    result = api.get_run(run_id)
    assert result.plan is not None and result.plan.selected and "plan.json" not in " ".join(result.warnings)
    assert result.measures and run.files.missing() == []


def test_a_traced_run_keeps_the_ids_that_find_its_trace(monkeypatch, tmp_path):
    monkeypatch.setenv("LANGSMITH_API_KEY", "k")
    monkeypatch.setenv("LANGSMITH_PROJECT", "proj")
    live.configure_tracing()
    req = request()
    model, sub = script(req.sid)
    run = live.LiveRun("run_ids", req, live.LiveSettings(model=model, subagent_model=sub, doors=stub_doors(),
                                                         runs_dir=tmp_path))
    monkeypatch.setattr(run, "_thread", type("T", (), {"start": lambda self: None})())      # no run, no network
    run.start()
    saved = json.loads((run.files.root / "trace.json").read_text())
    assert saved["trace_id"] == str(run.trace_id) and saved["project"] == "proj" and saved["run_id"] == "run_ids"
    assert "LANGSMITH_API_KEY" not in json.dumps(saved) and "k" != saved.get("key")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")


# ---- the summary may not state a number no tool returned ----

def _drive(live_mode, **script_kwargs):
    req = request()
    live_mode(req, **script_kwargs)
    run_id = api.start_run(req)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    api.answer(run_id, "q_service_amps", 100.0)
    return run_id, run, drain(run_id)


def test_a_summary_with_an_invented_number_is_sent_back_once_and_then_passes(live_mode):
    run_id, run, events = _drive(live_mode, final=("Savings are 98,765 dollars a year.", "Savings come from the plan."))
    repair = [e for e in events if e.type == "fallback" and e.payload.get("fallback") == "narrative_repair"]
    assert len(repair) == 1 and any("98,765" in p for p in repair[0].payload["problems"])

    assert (run.files.root / "report.md").read_text() == "Savings come from the plan."
    assert not any("check_narrative" in e.message for e in events if e.type == "error") and events[-1].type == "done"


def test_a_summary_that_is_still_wrong_loses_the_offending_lines(live_mode):
    run_id, run, events = _drive(live_mode, final=("Intro.\nSavings are 98,765 dollars a year.", "Intro.\nStill 98,765 dollars."))
    text = (run.files.root / "report.md").read_text()
    assert "98,765" not in text and "Intro." in text
    assert any("check_narrative: removed 1 line" in e.message for e in events if e.type == "error")
    assert any("removed 1 line" in w for w in api.get_run(run_id).warnings)


def test_a_clean_summary_costs_no_extra_turn(live_mode):
    run_id, run, events = _drive(live_mode, final=("The audit is complete.",))
    assert not [e for e in events if e.payload.get("fallback") == "narrative_repair"]


# ---- successful runs are kept for demo replay ----

def test_a_successful_live_run_is_recorded_and_replayed_offline(live_mode, monkeypatch):
    req = request()
    live_mode(req)
    run_id = api.start_run(req)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    api.answer(run_id, "q_service_amps", 100.0)
    live_events = drain(run_id)
    run._thread.join(timeout=30)
    saved = live.demo_dir() / req.sid
    assert {"result.json", "events.json", "bundle.json", "plan.json", "report.md"} <= {p.name for p in saved.iterdir()}
    assert not (saved / "assets").exists()

    monkeypatch.delenv("AGENT_MODE")                                  # replay mode now
    replay_id = api.start_run(req)
    assert replay_id.startswith("run_demo_")
    replayed = drain(replay_id)
    assert [e.model_dump(mode="json") for e in replayed] == [e.model_dump(mode="json") for e in live_events]
    result = api.get_run(replay_id)
    assert result.run_id == replay_id and result.status == "done" and result.plan is not None
    dreq = DocumentRequest.model_validate_json((EXAMPLES / "house" / "document_request.json").read_text())
    dreq.run_id = replay_id
    draft = api.draft_document(dreq)                                   # the legal door, no model
    assert api.get_document(replay_id, draft.doc_id) == draft and draft.doc_type == dreq.doc_type


def test_a_run_that_ends_in_error_is_not_recorded(live_mode, tmp_path, monkeypatch):
    req = request()
    monkeypatch.setattr(live, "SETTINGS", live.LiveSettings(
        doors=stub_doors(), model=Scripted(messages=iter([])), subagent_model=Scripted(messages=iter([])),
        runs_dir=tmp_path))
    run_id = api.start_run(req)
    assert drain(run_id)[-1].type == "error"
    live._RUNS[run_id]._thread.join(timeout=30)
    assert not (live.demo_dir() / req.sid).exists()


def test_with_nothing_recorded_replay_serves_the_example(monkeypatch):
    monkeypatch.delenv("AGENT_MODE", raising=False)
    run_id = api.start_run(request())
    assert run_id.startswith("run_house_") and drain(run_id)[-1].type == "done"


# ---------- a degraded door is reported, not swallowed (#274) ----------

def test_a_missing_analysis_dependency_is_recorded_rather_than_swallowed(monkeypatch):
    """`default_doors` falls back to `analysis_stub` on ImportError. The analysis door is
    on main, so that now means a broken environment - a missing numpy or shapely - and
    it replaces every analysis figure with the example's. Silently, before this: someone
    would have been left debugging why live numbers matched the fixtures."""
    import builtins

    real_import = builtins.__import__

    def without_analysis(name, *args, **kwargs):
        # `from backend.analysis import api` calls __import__ with the *package* name
        # and the attribute in fromlist, not with "backend.analysis.api". Matching the
        # dotted name silently never fires, and the test then passes against the real
        # door while claiming to have broken it.
        fromlist = args[2] if len(args) > 2 else kwargs.get("fromlist") or ()
        if name == "backend.analysis" and "api" in fromlist:
            raise ImportError("no module named 'shapely'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_analysis)
    doors = live.default_doors()

    assert doors.analysis.__name__.endswith("analysis_stub")
    assert doors.degraded and "shapely" in doors.degraded
    assert "replays the example" in doors.degraded


def test_a_healthy_environment_records_no_degradation():
    doors = live.default_doors()
    assert doors.analysis.__name__ == "backend.analysis.api"
    assert doors.degraded is None


def test_a_degraded_door_becomes_a_run_warning(tmp_path):
    """It has to reach `RunResult.warnings`, because that is what the frontend shows."""
    from backend.agent.tools import Doors

    settings = live.LiveSettings(runs_dir=tmp_path,
                                 doors=Doors(data=object(), analysis=object(),
                                             legal=object(), degraded="analysis is a stub"))
    run = live.LiveRun("run_degraded", request(), settings)
    assert "analysis is a stub" in run._warnings


# ---- answering inside the publish/check window (the flake Yale handed over) ----

def test_an_answer_that_lands_in_the_window_still_resumes_the_run(live_mode, monkeypatch):
    """A client that answers the moment it sees the question event must not end the run.

    `_main` publishes the question event, writes `usage.json`, and *then* reads
    `self.pending` to decide whether to wait for an answer. But `answer()` sets
    `self.pending = None`. So a client that answers inside that window makes `_main` read
    "no question was asked", return, and close the run - with `question` as the last
    event and the answer sitting unconsumed in `_inbox`.

    `self.pending` was doing two jobs: "a question is open", which `answer()` clears, and
    "this segment paused", which is a fact about the segment that `answer()` must not be
    able to change.

    The window is a few statements wide and `_write_usage` puts a **disk write** in the
    middle of it, which is why this surfaced only in multi-lane runs: under I/O
    contention the write takes long enough for a fast client to get in. Observed three
    times across three different tests of this file, each of which answers as soon as it
    sees the event.

    Here the window is hit deterministically by answering from inside `_write_usage`.
    """
    real_write_usage = live.LiveRun._write_usage
    answered: list[str] = []

    def answer_inside_the_window(self):
        real_write_usage(self)
        if self.pending is not None and not answered:      # the client is this quick
            answered.append(self.pending[1].id)
            self.answer(self.pending[1].id, 100.0)

    monkeypatch.setattr(live.LiveRun, "_write_usage", answer_inside_the_window)

    req = request()
    live_mode(req)
    run_id = api.start_run(req)
    events = drain(run_id)

    assert answered == ["q_service_amps"], "the test did not actually hit the window"
    assert events[-1].type == "done", (
        f"the run ended on {events[-1].type!r}: the answer was dropped and the run closed "
        f"instead of resuming")
    assert api.get_run(run_id).status == "done"


def test_an_answer_to_a_closed_run_is_an_error_not_a_silent_queue(live_mode):
    req = request()
    live_mode(req)
    run_id = api.start_run(req)
    run = live._RUNS[run_id]
    wait_for(lambda: any(e.type == "question" for e in run.events), "the question event")
    pending = run.pending
    run.closed = True                       # the run ended while the client still held the question
    assert pending is not None
    with pytest.raises(LookupError, match="closed"):
        api.answer(run_id, pending[1].id, None)
    assert run._inbox.empty()               # nothing was queued for a reader that is gone
    run.closed = False                      # let the run finish, so its worker thread is not left waiting
    api.answer(run_id, pending[1].id, None)
    assert drain(run_id)[-1].type == "done"


# ---------- the data lane's provenance reaches the run (issue #319) ----------

def test_a_bundle_fallback_becomes_a_run_event_and_a_warning(tmp_path):
    """A live run used to say nothing when the tariff was a state average or an oblique 429ed:
    the records were in the bundle and nothing read them. They must reach both the stream (so the
    stage log shows them as they happen) and `RunResult.warnings` (so the frontend shows them)."""
    from backend.schema import FetchRecord, PropertyBundle

    run = live.LiveRun("run_prov", request(), live.LiveSettings(runs_dir=tmp_path))
    bundle = PropertyBundle.model_validate_json(
        (EXAMPLES / "house" / "property_bundle.json").read_text()).model_copy(update={"provenance": [
            FetchRecord(layer="tariff", what="electricity price", status="fallback",
                        detail="EIA state average, not a looked-up tariff"),
            FetchRecord(layer="costar", what="listing", status="missing"),
        ]})
    run.files.write("bundle.json", bundle.model_dump(mode="json"))

    emitted: list = []
    run._emit = emitted.append          # `_emit` hands chunks to a loop that only exists mid-run
    tool = run._instrument("get_property_bundle", lambda sid: {"sid": sid})
    tool(sid=bundle.summary.sid)

    reported = [e for e in emitted if getattr(e, "type", None) == "fallback"
                and e.payload.get("status") == "fallback"]
    assert len(reported) == 1 and "EIA state average" in reported[0].message
    assert reported[0].payload["layer"] == "tariff" and reported[0].stage == "ingest"
    assert any("EIA state average" in w for w in run._warnings)
    assert not any(getattr(e, "payload", {}).get("what") == "listing" for e in emitted), \
        "a missing record is not a degraded run"


def test_the_same_bundle_read_twice_does_not_warn_twice(tmp_path):
    """`get_property_bundle` is called again by later subagents and its result is memoised; the
    warning must not be repeated once per call."""
    run = live.LiveRun("run_prov2", request(), live.LiveSettings(runs_dir=tmp_path))
    raw = json.loads((EXAMPLES / "office" / "property_bundle.json").read_text())
    run.files.write("bundle.json", raw)
    tool = run._instrument("get_property_bundle", lambda sid: {"sid": sid})
    tool(sid=raw["summary"]["sid"])
    once = list(run._warnings)
    tool(sid=raw["summary"]["sid"])
    assert run._warnings == once and once, "warnings are deduplicated, and there were some"


# ---------- the substituted weather year is a run fallback (issue #328) ----------

def test_a_substituted_weather_year_becomes_a_run_event_and_a_warning(tmp_path):
    """The analysis door substitutes the committed example year when the site's own cached weather
    file is absent, which moves every energy figure in the run. It is a fallback like any other."""
    from backend.schema import PropertyBundle

    run = live.LiveRun("run_weather", request(), live.LiveSettings(runs_dir=tmp_path))
    bundle = PropertyBundle.model_validate_json(
        (EXAMPLES / "house" / "property_bundle.json").read_text())
    absent = bundle.model_copy(update={"climate": bundle.climate.model_copy(
        update={"weather_path": "data/cache/__not_a_cached_site__/weather/typical_year_hourly.csv"})})
    run.files.write("bundle.json", absent.model_dump(mode="json"))

    emitted: list = []
    run._emit = emitted.append
    run._instrument("run_baseline", lambda: {"annual": {}})()

    said = [e for e in emitted if getattr(e, "type", None) == "fallback"
            and e.payload.get("fallback") == "weather:example_year"]
    assert len(said) == 1 and "not on this machine" in said[0].message
    assert any("not on this machine" in w for w in run._warnings)


def test_a_door_that_cannot_report_its_weather_does_not_fail_the_run(tmp_path, monkeypatch):
    """A missing warning must never be the thing that ends a run. The stub door offers
    `climate_notes`; an older or broken one may not, and that is survivable."""
    run = live.LiveRun("run_weather2", request(), live.LiveSettings(runs_dir=tmp_path))
    raw = json.loads((EXAMPLES / "house" / "property_bundle.json").read_text())
    run.files.write("bundle.json", raw)

    class Mute:
        def climate_notes(self, bundle):
            raise RuntimeError("this door cannot say")

    monkeypatch.setattr(run.doors, "analysis", Mute(), raising=False)
    assert run._climate_notes(raw) == []
    monkeypatch.setattr(run.doors, "analysis", object(), raising=False)
    assert run._climate_notes(raw) == []


def test_a_live_run_with_the_real_doors_uses_live_data_and_a_test_with_fake_doors_does_not(tmp_path, monkeypatch):
    """Without DATA_LAYER_LIVE the data layer returns the example bundle, so a 'live' recording would be of the
    fixtures. Real doors turn it on; fake doors (every test) leave the environment alone."""
    monkeypatch.delenv("DATA_LAYER_LIVE", raising=False)
    live.LiveRun("run_fake", request(), live.LiveSettings(runs_dir=tmp_path, doors=stub_doors()))
    assert "DATA_LAYER_LIVE" not in os.environ
    live.LiveRun("run_real", request(), live.LiveSettings(runs_dir=tmp_path))
    assert os.environ["DATA_LAYER_LIVE"] == "1"
    os.environ["DATA_LAYER_LIVE"] = "0"       # an explicit choice is kept (the conftest restores the variable)
    live.LiveRun("run_real2", request(), live.LiveSettings(runs_dir=tmp_path))
    assert os.environ["DATA_LAYER_LIVE"] == "0"


def test_the_environment_keys_a_live_run_needs_are_picked_up_from_dotenv():
    for key in ("ANTHROPIC_API_KEY", "EIA_API_KEY", "MATTERPORT_API_KEY", "MATTERPORT_API_TOKEN", "VEXCEL_API_KEY"):
        assert key in live._ENV_KEYS
