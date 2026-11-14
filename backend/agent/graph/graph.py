"""The deep agent (G2): `auditor` orchestrator with `scout`, `surveyor`, `physicist` and
`financier` (SPEC 8). `counsel` is added by G6. Tools are passed in (G1 builds them)."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from langchain_core.tools import StructuredTool

try:                                    # A0 owns backend/config.py; until it lands use SPEC 8
    from backend import config as _cfg
    ORCHESTRATOR_MODEL = _cfg.ORCHESTRATOR_MODEL
    SUBAGENT_MODEL = _cfg.SUBAGENT_MODEL
except (ImportError, AttributeError):
    ORCHESTRATOR_MODEL = "claude-opus-5-5"
    SUBAGENT_MODEL = "claude-sonnet-5-5"

# SPEC 8 table: the only tools each subagent receives (plus the file tools deepagents adds).
SUBAGENT_TOOLS: dict[str, tuple[str, ...]] = {
    "scout": ("search_properties", "get_property_bundle", "get_asset"),
    "surveyor": ("observe_interior", "detect_roof_elements", "build_building_model",
                 "set_assumption"),
    "physicist": ("run_baseline", "evaluate_measure", "design_pv", "score_desk_positions"),
    "financier": ("price_measure", "lookup_incentives", "build_plan", "cpace_scenario",
                  "sensitivity"),
}
AUDITOR_TOOLS = ("ask_user",)

_JOBS = {
    "scout": "Find and ingest the property. Write the bundle to the run files.",
    "surveyor": "Read imagery and build the building model. Log a fallback when a layer is missing.",
    "physicist": "Run the baseline and evaluate measures. Never do arithmetic yourself.",
    "financier": "Price measures, look up incentives and build the plan. Never do arithmetic yourself.",
}

AUDITOR_PROMPT = """You are the auditor, orchestrator of an energy retrofit audit.
Keep a todo list with write_todos and update it as each step starts and finishes.
Delegate with the task tool: scout (ingest), surveyor (model), physicist (baseline and
measures), financier (plan). You never do arithmetic: every number you write comes from a
tool result. Decide fallbacks when a layer is missing and say which you chose. Ask the user
(ask_user) only for the question the sensitivity tool returns. Write report.md last."""


def as_langchain_tool(name: str, fn: Callable) -> StructuredTool:
    return StructuredTool.from_function(
        func=fn, name=name, description=(fn.__doc__ or _DESC.get(name, name)).strip(),
        infer_schema=True)


_DESC = {n: n.replace("_", " ") for names in SUBAGENT_TOOLS.values() for n in names}


def make_ask_user() -> Callable:
    from langgraph.types import interrupt

    def ask_user(question: dict):
        """Pause the run and ask the user one Question; returns the chosen Choice.value."""
        return interrupt({"question": question})
    return ask_user


def subagent_specs(tools: Mapping[str, Callable], model: Any = None) -> list[dict]:
    """One spec per subagent, holding exactly the tools of SUBAGENT_TOOLS."""
    specs = []
    for name, names in SUBAGENT_TOOLS.items():
        spec = {"name": name, "description": _JOBS[name], "system_prompt": _JOBS[name],
                "tools": [as_langchain_tool(n, tools[n]) for n in names]}
        spec["model"] = model if model is not None else SUBAGENT_MODEL
        specs.append(spec)
    return specs


def build_auditor(tools: Mapping[str, Callable], model: Any = None, subagent_model: Any = None,
                  checkpointer: Any = None, ask_user: Optional[Callable] = None,
                  with_counsel: bool = False, approve: Optional[Callable] = None):
    from deepagents import create_deep_agent
    from langchain.agents.middleware import TodoListMiddleware   # SPEC 8 [U]: add explicitly

    ask = ask_user or make_ask_user()
    specs = subagent_specs(tools, subagent_model)
    if with_counsel:                     # G6: needs list_templates, fill_template, check_document
        from backend.agent.graph.counsel import counsel_spec
        specs.append(counsel_spec(tools, subagent_model, approve))
    return create_deep_agent(
        model=model if model is not None else ORCHESTRATOR_MODEL,
        tools=[as_langchain_tool("ask_user", ask)],
        system_prompt=AUDITOR_PROMPT,
        middleware=[TodoListMiddleware()],
        subagents=specs,
        checkpointer=checkpointer,
        name="auditor")
