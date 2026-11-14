import json
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from backend.agent.graph import COUNSEL_TOOLS, counsel_spec, counsel_tools
from backend.agent.graph.counsel import default_approve
from backend.schema import DocumentDraft, StatutoryCheck

EX = Path(__file__).resolve().parents[4] / "specs" / "examples" / "house"
DRAFT = json.loads((EX / "document_draft.json").read_text())


def stub_tools():
    calls = []

    def fill_template(doc_type, state, measure_ids, fields=None):
        calls.append(("fill", dict(fields or {})))
        return {**DRAFT, "statutory_checks": []}

    def check_document(doc_id):
        calls.append(("check", doc_id))
        return DRAFT["statutory_checks"]

    return {"list_templates": lambda state=None: ["retrofit_contract_residential"],
            "fill_template": fill_template, "check_document": check_document}, calls


ARGS = ("retrofit_contract_residential", "CA", ["ENV_ATTIC"], {"owner_names": "A. Owner"})


def test_fill_does_not_run_before_approval():
    tools, calls = stub_tools()
    seen = []
    def approve(proposal):
        seen.append(proposal)
        assert calls == []                      # nothing has been drafted at this point
        return True
    out = counsel_tools(tools, approve)["fill_template"](*ARGS)
    assert seen[0]["measure_ids"] == ["ENV_ATTIC"] and seen[0]["parties"]["owner_names"] == "A. Owner"
    assert seen[0]["parties"]["contractor_name"] is None     # never invented
    assert [c[0] for c in calls] == ["fill", "check"] and "error" not in out


def test_rejected_approval_makes_no_draft():
    tools, calls = stub_tools()
    out = counsel_tools(tools, lambda p: {"approved": False})["fill_template"](*ARGS)
    assert calls == [] and "error" in out and "no draft" in out["error"]
    assert "error" in counsel_tools(tools, lambda p: False)["fill_template"](*ARGS)


def test_no_measures_no_approval_asked():
    tools, calls = stub_tools()
    asked = []
    out = counsel_tools(tools, lambda p: asked.append(p) or True)["fill_template"](
        "retrofit_contract_residential", "CA", [], {})
    assert "error" in out and asked == [] and calls == []


def test_returned_draft_lists_unfilled_and_checks():
    tools, _ = stub_tools()
    out = counsel_tools(tools, lambda p: True)["fill_template"](*ARGS)
    draft = DocumentDraft.model_validate(out)
    assert draft.unfilled_placeholders and draft.statutory_checks
    assert all(isinstance(c, StatutoryCheck) for c in draft.statutory_checks)


def test_approval_can_add_fields():
    tools, calls = stub_tools()
    counsel_tools(tools, lambda p: {"approved": True, "fields": {"contractor_name": "Acme"}})["fill_template"](*ARGS)
    assert calls[0][1]["contractor_name"] == "Acme" and calls[0][1]["owner_names"] == "A. Owner"


def test_counsel_spec_has_only_its_three_tools():
    tools, _ = stub_tools()
    spec = counsel_spec(tools, approve=lambda p: True)
    assert spec["name"] == "counsel" and [t.name for t in spec["tools"]] == list(COUNSEL_TOOLS)


class S(TypedDict, total=False):
    out: object


@pytest.mark.parametrize("decision,drafted", [({"approved": True}, True), ({"approved": False}, False)])
def test_interrupt_gate_pauses_then_resumes(decision, drafted):
    tools, calls = stub_tools()
    fill = counsel_tools(tools, default_approve)["fill_template"]
    g = StateGraph(S)
    g.add_node("n", lambda s: {"out": fill(*ARGS)})
    g.add_edge(START, "n"); g.add_edge("n", END)
    graph = g.compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t"}}
    paused = graph.invoke({}, cfg)
    assert "approval" in paused["__interrupt__"][0].value and calls == []
    done = graph.invoke(Command(resume={"value": decision}), cfg)
    assert bool(calls) is drafted and ("error" not in done["out"]) is drafted
