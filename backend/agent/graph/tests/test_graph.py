import json
from pathlib import Path
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from backend.agent.graph import SUBAGENT_TOOLS, build_auditor, detect_fallbacks, subagent_specs
from backend.schema import PropertyBundle

EX = Path(__file__).resolve().parents[4] / "specs" / "examples"
ALL = {n for names in SUBAGENT_TOOLS.values() for n in names}


def fake_tools():
    return {n: (lambda *a, **k: {"ok": True}) for n in ALL}


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs: Any):
        return self


def scripted(*messages):
    return ScriptedModel(messages=iter(messages))


def test_each_subagent_gets_only_its_tools():
    specs = {s["name"]: s for s in subagent_specs(fake_tools())}
    assert set(specs) == {"scout", "surveyor", "physicist", "financier", "reviewer"}
    for name, names in SUBAGENT_TOOLS.items():
        assert [t.name for t in specs[name]["tools"]] == list(names)
    # no tool is shared between subagents, so none can reach another's tools
    flat = [n for names in SUBAGENT_TOOLS.values() for n in names]
    assert len(flat) == len(set(flat)) == 19


def test_todo_list_changes_during_a_scripted_run():
    todo1 = [{"content": "ingest", "status": "in_progress"}, {"content": "model", "status": "pending"}]
    todo2 = [{"content": "ingest", "status": "completed"}, {"content": "model", "status": "in_progress"}]
    model = scripted(
        AIMessage(content="", tool_calls=[{"name": "write_todos", "args": {"todos": todo1}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "write_todos", "args": {"todos": todo2}, "id": "2"}]),
        AIMessage(content="done"))
    agent = build_auditor(fake_tools(), model=model, subagent_model=scripted(AIMessage(content="x")),
                          checkpointer=InMemorySaver())
    seen = []
    cfg = {"configurable": {"thread_id": "t"}}
    for chunk in agent.stream({"messages": [("user", "audit")]}, cfg, stream_mode="values"):
        if chunk.get("todos"):
            seen.append(json.dumps(chunk["todos"], sort_keys=True))
    assert len(set(seen)) >= 2


def _bundle(flavor):
    return PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())


def test_no_splat_logs_fallback():
    b = _bundle("house")
    b.matterport.splat_path = None
    keys = [e.payload["fallback"] for e in detect_fallbacks(b)]
    assert "no_splat" in keys and all(e.type == "fallback" for e in detect_fallbacks(b))


def test_no_georeference_logs_fallback():
    b = _bundle("house")
    b.matterport.georeference = None
    assert "no_georeference" in [e.payload["fallback"] for e in detect_fallbacks(b)]


def test_other_rules():
    b = _bundle("office")
    b.costar = None
    b.matterport.matterpak_available = False
    for f in b.matterport.floors:                       # the rule, whatever the example holds
        for e in f.edges:
            e.openings = [o for o in e.openings if o.type != "window"]
    keys = {e.payload["fallback"] for e in detect_fallbacks(b)}
    assert {"no_costar", "matterpak_locked", "no_window_openings"} <= keys   # no window left in the wall graph


# ---- the prompts ----

def test_the_prompts_state_the_order_and_the_measure_ids():
    from backend.agent.graph.graph import (AUDITOR_PROMPT, HOME_MEASURES, OFFICE_MEASURES, _JOBS)
    order = [AUDITOR_PROMPT.index(w) for w in ("scout:", "surveyor:", "physicist:", "financier:", "report.md")]
    assert order == sorted(order)
    assert "build_plan is required" in AUDITOR_PROMPT and "ask_user" in AUDITOR_PROMPT and "arithmetic" in AUDITOR_PROMPT
    assert all(m in _JOBS["physicist"] for m in HOME_MEASURES + OFFICE_MEASURES)
    assert "build_plan is required" in _JOBS["financier"] and "never before the model exists" in _JOBS["surveyor"]
    assert set(_JOBS) == {"scout", "surveyor", "physicist", "financier", "reviewer"}


def test_the_measure_lists_are_the_engines_flows():
    """The prompt lists must not drift from the analysis lane's catalogue (SPEC 6.2)."""
    from backend.agent.graph.graph import HOME_MEASURES, OFFICE_MEASURES
    from backend.analysis.measures import engine
    home = {m for m, e in engine.CATALOGUE.items() if "home" in e.flows}
    office = {m for m, e in engine.CATALOGUE.items() if "office" in e.flows}
    assert set(HOME_MEASURES) == home and set(OFFICE_MEASURES) == office


def test_the_run_prompt_names_the_task_and_what_finishes_it():
    from pathlib import Path as P
    from backend.agent import live
    from backend.schema import RunRequest
    req = RunRequest.model_validate_json((EX / "house" / "run_request.json").read_text())
    run = live.LiveRun.__new__(live.LiveRun)
    run.request = req
    text = live.LiveRun._prompt(run)
    assert req.sid in text and "build_plan has returned" in text and "report.md" in text


def test_the_auditor_writes_the_report_from_the_run_files():
    from backend.agent.graph.graph import AUDITOR_PROMPT, AUDITOR_TOOLS
    tail = AUDITOR_PROMPT[AUDITOR_PROMPT.index("6. You"):]
    for name in ("read_run_file", "check_report", "/run/plan.json", "/run/measures.json", "/run/baseline.json"):
        assert name in tail
    assert AUDITOR_TOOLS == ("ask_user", "read_run_file", "check_report")


def test_the_reviewer_runs_last_reads_the_files_and_cannot_write():
    from backend.agent.graph.graph import AUDITOR_PROMPT, _JOBS
    assert SUBAGENT_TOOLS["reviewer"] == ("read_run_file", "check_report")
    assert AUDITOR_PROMPT.index("7. reviewer") > AUDITOR_PROMPT.index("6. You")
    job = _JOBS["reviewer"]
    for needle in ("/run/plan.json", "read_file", "check_report", "Never do arithmetic", "never edit report.md", "OK"):
        assert needle in job, needle
    tail = AUDITOR_PROMPT[AUDITOR_PROMPT.index("7. reviewer"):]
    assert "apply each one to report.md yourself" in tail and "no more reviews" in tail


def test_the_reviewer_gets_only_the_read_tools():
    specs = {s["name"]: s for s in subagent_specs(fake_tools())}
    assert [t.name for t in specs["reviewer"]["tools"]] == ["read_run_file", "check_report"]
