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
    "reviewer": ("read_run_file", "check_report"),     # read-only (tools.build_reader_tools)
}
AUDITOR_TOOLS = ("ask_user", "read_run_file", "check_report")   # the last two are read-only (tools.build_reader_tools)

# SPEC 6.2: the measures of each property type. A subagent is told which ids exist so that it does not
# have to probe the tool for them; the tool schemas also list every allowed id.
HOME_MEASURES = ("ENV_ATTIC", "ENV_WALL", "ENV_AIRSEAL", "WIN_REPLACE", "WIN_FILM", "WIN_SHADE", "ROOF_COOL",
                 "HVAC_HP", "HVAC_DUCT", "DHW_HPWH", "LGT_LED", "CTRL_TSTAT", "PV_ROOF", "LAYOUT")
OFFICE_MEASURES = ("ENV_ATTIC", "ENV_AIRSEAL", "WIN_REPLACE", "WIN_FILM", "WIN_SHADE", "ROOF_COOL", "HVAC_RTU",
                   "HVAC_ECON", "LGT_LED", "LGT_CTRL", "PLUG_MGMT", "CTRL_TSTAT", "PV_ROOF", "LAYOUT")

_MEASURES_TEXT = (f"Homes (single family, multifamily unit): {', '.join(HOME_MEASURES)}. "
                  f"Offices and other commercial: {', '.join(OFFICE_MEASURES)}.")

_JOBS = {
    "scout": ("Fetch the property. Call get_property_bundle once with the sid you are given, then stop and "
              "report in three lines at most what is missing or substituted, and give the path /run/bundle.json "
              "where the tool saved the data. Do not repeat the data. Do nothing else."),
    "surveyor": ("Build the building model. Call observe_interior once, detect_roof_elements once (label "
                 "\"roof\"), then build_building_model once, then reply with a short summary (property type, number of zones, the assumptions you "
                 "had to make) and the path /run/model.json where the model was saved; do not repeat the model. "
                 "Call set_assumption only to apply an answer the user gave, with a key from the model, and never before the model exists."),
    "physicist": ("Simulate and evaluate. Call run_baseline once. Then call evaluate_measure exactly once for each "
                  "measure id of the property's type, taken from this list and no other. " + _MEASURES_TEXT +
                  " Decide the type from the bundle summary (use_type; an office or commercial property is an "
                  "office, everything else a home). A measure that does not apply is reported as it is; never "
                  "repeat a measure and never try ids to see which exist. Never do arithmetic. The tools save "
                  "their results; finish with a short summary (which measures apply and which do not) and the "
                  "paths /run/baseline.json and /run/measures.json, not the numbers."),
    "financier": ("Price and plan. Call price_measure once for each measure that applies (evaluate_measure said "
                  "so), then sensitivity once, then build_plan once: build_plan is required, a run without a "
                  "plan has failed. If you are asked to apply an answer, call set_assumption with it and then "
                  "build_plan once more. Use cpace_scenario only for an office and only for a priced measure. "
                  "Never do arithmetic. Finish with a short summary (how many measures are selected, whether "
                  "sensitivity returned questions, and how many) and the path /run/plan.json, not the numbers."),
}

_JOBS["reviewer"] = (
    "Review report.md before the run ends, in your own context. Read /run/plan.json, /run/measures.json and "
    "/run/baseline.json with read_run_file and read report.md with read_file. Run check_report on the full text of "
    "report.md. Then compare the report with the files: every selected measure, cost, saving and total it states "
    "must be the file's value, and the report must not call a skipped or financeable measure selected, or the "
    "reverse. Never do arithmetic and never edit report.md yourself. Reply with exactly \"OK\" if there is nothing "
    "to fix; otherwise a numbered list of fixes, each naming the sentence and the value from the file that "
    "replaces it, or saying to delete it.")

AUDITOR_PROMPT = """You are the auditor, orchestrator of an energy retrofit audit of one property.
Keep a todo list with write_todos and update it as each step starts and finishes.
Delegate with the task tool, one subagent at a time, in this order, giving each the property's sid. The
subagents leave their data in files and answer with a short summary and the file path; read a file only when
you need it (read_run_file):
  1. scout: fetches the property data (once) and saves /run/bundle.json.
  2. surveyor: reads the interior and builds the building model (once); saves /run/model.json.
  3. physicist: simulates the baseline and evaluates each measure of the property's type (once each); saves
     /run/baseline.json and /run/measures.json.
  4. financier: prices the measures, runs sensitivity, and builds the plan (build_plan is required); saves
     /run/plan.json.
  5. You: if sensitivity returned questions, ask the user with ask_user, one at a time (at most three);
     then have the financier apply each answer with set_assumption and call build_plan once more.
     If it returned none, ask nothing.
  6. You: write report.md last, only from the run files. Read /run/plan.json, /run/measures.json and
     /run/baseline.json with read_run_file, then write a short plain summary of the property, the baseline,
     the selected measures with cost and saving, what is financeable, and what was skipped and why. Say the order the plan follows (operations, then load
     reduction, then equipment, then solar last), and when solar is skipped, shrunk or only financeable say why
     (not cost-effective, or no budget left). Copy each
     figure from those files with the same digits and units. Then run check_report on the draft; if it lists
     a number, replace it with the value from the file or delete the sentence, and check again.
  7. reviewer: last. It reads plan.json and report.md in its own context, runs check_report and compares the
     report with the files. If it answers OK, finish. If it lists fixes, apply each one to report.md yourself
     (one rewrite, no more reviews) and finish.
You never do arithmetic. Do not write a total, a percentage, a sum, a ratio or any figure the files do not
hold. Decide fallbacks when a layer is missing and say which you chose. The run is complete only when build_plan has returned and report.md is written."""


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
        tools=[as_langchain_tool("ask_user", ask)] + [as_langchain_tool(n, tools[n]) for n in AUDITOR_TOOLS[1:] if n in tools],
        system_prompt=AUDITOR_PROMPT,
        middleware=[TodoListMiddleware()],
        subagents=specs,
        checkpointer=checkpointer,
        name="auditor")
