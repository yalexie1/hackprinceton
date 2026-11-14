"""`counsel` subagent and approval before drafting (G6, SPEC 8 rule 4).

`fill_template` is wrapped so it cannot run until the user has approved the parties and the
measure list. A rejection produces no draft. The returned draft carries its
`unfilled_placeholders` and the `statutory_checks` of `check_document`.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

COUNSEL_TOOLS = ("list_templates", "fill_template", "check_document")
PARTY_FIELDS = ("owner_names", "owner_mailing_address", "contractor_name",
                "contractor_business_address", "contractor_license_number")

COUNSEL_PROMPT = """You are counsel. You draft documents with fill_template and verify them with
check_document. You never invent a party, licence number or address: leave it blank. Before
fill_template runs, the user must approve the parties and the measure list; if the user
declines, stop and report that no draft was made. Report the unfilled placeholders and every
failed statutory check. Every draft is for attorney review and is not legal advice."""


def default_approve(proposal: dict) -> Any:
    """Ask the user through a langgraph interrupt. Resume with
    `Command(resume={"value": {"approved": True, "fields": {...}}})` (or approved False)."""
    from langgraph.types import interrupt
    reply = interrupt({"approval": proposal})
    return reply["value"] if isinstance(reply, dict) and "value" in reply else reply


def gated_fill_template(tools: Mapping[str, Callable],
                        approve: Optional[Callable[[dict], Any]] = None) -> Callable:
    approve = approve or default_approve

    def fill_template(doc_type: str, state: str, measure_ids: list, fields: Optional[dict] = None):
        """Draft a document. Asks the user to approve the parties and measures first."""
        fields = dict(fields or {})
        if not measure_ids:
            return {"error": "fill_template needs at least one measure to draft"}
        proposal = {"doc_type": doc_type, "state": state, "measure_ids": list(measure_ids),
                    "parties": {k: fields.get(k) for k in PARTY_FIELDS}}
        decision = approve(proposal)
        approved = decision if isinstance(decision, bool) else bool(
            isinstance(decision, dict) and decision.get("approved"))
        if not approved:
            return {"error": "the user did not approve the parties and measures: no draft was made"}
        if isinstance(decision, dict):
            fields.update(decision.get("fields") or {})
        draft = tools["fill_template"](doc_type, state, measure_ids, fields)
        if not isinstance(draft, dict) or "error" in draft:
            return draft
        checks = tools["check_document"](draft["doc_id"])
        if isinstance(checks, list):
            draft = {**draft, "statutory_checks": checks}
        return draft
    return fill_template


def counsel_tools(tools: Mapping[str, Callable],
                  approve: Optional[Callable[[dict], Any]] = None) -> dict[str, Callable]:
    """The three counsel tools; fill_template is the gated one."""
    return {"list_templates": tools["list_templates"],
            "fill_template": gated_fill_template(tools, approve),
            "check_document": tools["check_document"]}


def counsel_spec(tools: Mapping[str, Callable], model: Any = None,
                 approve: Optional[Callable[[dict], Any]] = None) -> dict:
    from backend.agent.graph.graph import SUBAGENT_MODEL, as_langchain_tool
    gated = counsel_tools(tools, approve)
    return {"name": "counsel", "description": "Drafts legal documents after the user approves.",
            "system_prompt": COUNSEL_PROMPT,
            "tools": [as_langchain_tool(n, gated[n]) for n in COUNSEL_TOOLS],
            "model": model if model is not None else SUBAGENT_MODEL}
