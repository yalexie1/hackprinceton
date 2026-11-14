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
    assert set(specs) == {"scout", "surveyor", "physicist", "financier"}
    for name, names in SUBAGENT_TOOLS.items():
        assert [t.name for t in specs[name]["tools"]] == list(names)
    # no tool is shared between subagents, so none can reach another's tools
    flat = [n for names in SUBAGENT_TOOLS.values() for n in names]
    assert len(flat) == len(set(flat)) == 16


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
    keys = {e.payload["fallback"] for e in detect_fallbacks(b)}
    assert {"no_costar", "matterpak_locked", "no_window_openings"} <= keys   # office has doorways only
